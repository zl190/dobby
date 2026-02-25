"""Discord adapter using Gateway WebSocket (local, no public URL needed).

Requires: pip install discord.py
"""

import asyncio
import sys
import threading
from typing import Optional

import discord

from notify.adapters.base import BaseAdapter, AnswerCallback, CommandCallback


class DiscordAdapter(BaseAdapter):
    """Discord bot adapter using the Gateway WebSocket.

    Questions are posted as embeds. The first reply to the bot's message
    is treated as the answer.
    """

    def __init__(
        self,
        answer_callback: AnswerCallback,
        bot_token: str,
        channel_id: Optional[str] = None,
        authorized_users: list[str] | None = None,
        command_callback: Optional[CommandCallback] = None,
    ):
        super().__init__(answer_callback, command_callback)
        self._bot_token = bot_token
        try:
            self._channel_id = int(channel_id) if channel_id else None
        except ValueError:
            print(f"Warning: Invalid Discord channel_id '{channel_id}'. Must be a numeric ID.", file=sys.stderr)
            self._channel_id = None
        self._authorized_users = authorized_users or []
        self._client: Optional[discord.Client] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._msg_lock = threading.Lock()
        # Maps message_id -> task_name (for HITL question replies)
        self._question_messages: dict[int, str] = {}
        # Maps task_name -> message_id (for HITL questions)
        self._task_messages: dict[str, int] = {}
        # Maps task_name -> message_id (for command launch messages, separate from HITL)
        self._command_messages: dict[str, int] = {}

    @property
    def platform_name(self) -> str:
        return "Discord"

    def connect(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)

        @self._client.event
        async def on_ready():
            self._connected = True

        @self._client.event
        async def on_message(message: discord.Message):
            if message.author == self._client.user:
                return
            if self._authorized_users and str(message.author.id) not in self._authorized_users:
                return

            # Reply to a question message → answer
            if message.reference and message.reference.message_id:
                ref_id = message.reference.message_id
                with self._msg_lock:
                    task_name = self._question_messages.get(ref_id)
                if task_name:
                    accepted = await asyncio.get_running_loop().run_in_executor(
                        None, self._answer_callback, task_name, message.content
                    )
                    if accepted:
                        await message.add_reaction("\u2705")
                return

            # Only accept commands from the configured channel
            if self._channel_id and message.channel.id != self._channel_id:
                return

            # Top-level "dobby <request>" → command
            text = message.content.strip()
            lower = text.lower()
            if (lower.startswith("dobby ") or lower.startswith("dobby, ")) and self._command_callback:
                request = text.split(None, 1)[1] if " " in text else ""
                if request:
                    user_id = str(message.author.id)
                    task_name = await asyncio.get_running_loop().run_in_executor(
                        None, self._command_callback, request, user_id, "discord"
                    )
                    if task_name:
                        embed = discord.Embed(
                            title=f"Dobby is on it: {task_name}",
                            description=f"Launched from Discord by {message.author.mention}",
                            color=0x2ECC71,
                        )
                        embed.set_footer(text="You'll be notified when it completes.")
                        msg = await message.channel.send(embed=embed)
                        with self._msg_lock:
                            self._command_messages[task_name] = msg.id
                    else:
                        embed = discord.Embed(
                            title="Launch failed",
                            description="Dobby couldn't launch that task. Too many active sessions or launch failed.",
                            color=0xE74C3C,
                        )
                        await message.channel.send(embed=embed)

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._client.start(self._bot_token))

    def disconnect(self) -> None:
        if self._client and self._loop:
            asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def send_question(self, task_name: str, question_text: str) -> bool:
        if not self._client or not self._channel_id or not self._loop:
            return False

        # Truncate to Discord's limit
        if len(question_text) > 1900:
            question_text = question_text[:1900] + "..."

        async def _send():
            channel = self._client.get_channel(self._channel_id)
            if not channel:
                return None
            embed = discord.Embed(
                title=f"Dobby needs help: {task_name}",
                description=question_text,
                color=0xF39C12,
            )
            embed.set_footer(text="Reply to this message to answer.")
            msg = await channel.send(embed=embed)
            return msg.id

        future = asyncio.run_coroutine_threadsafe(_send(), self._loop)
        try:
            msg_id = future.result(timeout=10)
            if msg_id:
                with self._msg_lock:
                    self._question_messages[msg_id] = task_name
                    self._task_messages[task_name] = msg_id
                return True
        except Exception:
            pass
        return False

    def confirm_answer(self, task_name: str) -> None:
        with self._msg_lock:
            msg_id = self._task_messages.pop(task_name, None)
            if msg_id:
                self._question_messages.pop(msg_id, None)
        if msg_id and self._client and self._loop:
            async def _confirm():
                channel = self._client.get_channel(self._channel_id)
                if channel:
                    msg = await channel.fetch_message(msg_id)
                    await msg.add_reaction("\u2705")
            asyncio.run_coroutine_threadsafe(_confirm(), self._loop)

    def send_completion(self, task_name: str, cost: float, output_dir: str, duration_secs: int = 0) -> bool:
        if not self._client or not self._channel_id or not self._loop:
            return False

        with self._msg_lock:
            msg_id = self._command_messages.get(task_name)

        async def _send():
            channel = self._client.get_channel(self._channel_id)
            if not channel:
                return
            embed = discord.Embed(
                title=f"Dobby finished: {task_name}",
                color=0x2ECC71,
            )
            embed.add_field(name="Cost", value=f"${cost:.2f}", inline=True)
            if duration_secs > 0:
                mins, secs = divmod(duration_secs, 60)
                embed.add_field(name="Time", value=f"{mins}m {secs}s" if mins else f"{secs}s", inline=True)
            embed.add_field(name="Output", value=f"`{output_dir}`", inline=True)
            if msg_id:
                try:
                    orig = await channel.fetch_message(msg_id)
                    await orig.reply(embed=embed)
                    return
                except Exception:
                    pass
            await channel.send(embed=embed)

        try:
            asyncio.run_coroutine_threadsafe(_send(), self._loop).result(timeout=10)
            # Only pop after successful send
            with self._msg_lock:
                self._command_messages.pop(task_name, None)
            return True
        except Exception:
            return False

    def send_status(self, task_name: str, status_text: str) -> bool:
        with self._msg_lock:
            msg_id = self._task_messages.get(task_name)
        if not msg_id or not self._client or not self._channel_id or not self._loop:
            return False

        async def _status():
            channel = self._client.get_channel(self._channel_id)
            if channel:
                msg = await channel.fetch_message(msg_id)
                await msg.reply(status_text)

        try:
            asyncio.run_coroutine_threadsafe(_status(), self._loop).result(timeout=10)
            return True
        except Exception:
            return False

    def cancel_question(self, task_name: str) -> None:
        with self._msg_lock:
            msg_id = self._task_messages.get(task_name)
        if msg_id and self._client and self._loop:
            async def _cancel():
                channel = self._client.get_channel(self._channel_id)
                if channel:
                    msg = await channel.fetch_message(msg_id)
                    await msg.add_reaction("\u274C")
                    await msg.reply("_This question was answered in the terminal._")
            asyncio.run_coroutine_threadsafe(_cancel(), self._loop)
        with self._msg_lock:
            if msg_id:
                self._question_messages.pop(msg_id, None)
            self._task_messages.pop(task_name, None)
