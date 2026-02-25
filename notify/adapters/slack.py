"""Slack adapter using Socket Mode (WebSocket, local, no public URL needed).

Requires: pip install slack-sdk
"""

import threading
from typing import Optional

from slack_sdk.web import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from notify.adapters.base import BaseAdapter, AnswerCallback, CommandCallback


class SlackAdapter(BaseAdapter):
    """Slack bot adapter using Socket Mode for local WebSocket communication.

    Questions are posted as messages. The first reply in the thread
    from an authorized user is treated as the answer.
    """

    def __init__(
        self,
        answer_callback: AnswerCallback,
        bot_token: str,
        app_token: str,
        channel: Optional[str] = None,
        authorized_users: list[str] | None = None,
        command_callback: Optional[CommandCallback] = None,
    ):
        super().__init__(answer_callback, command_callback)
        self._bot_token = bot_token
        self._app_token = app_token
        self._channel = channel
        self._authorized_users = authorized_users or []
        self._web_client: Optional[WebClient] = None
        self._socket_client: Optional[SocketModeClient] = None
        self._connected = False
        self._msg_lock = threading.Lock()
        # Maps message_ts -> task_name for correlating thread replies
        self._question_messages: dict[str, str] = {}
        # Maps task_name -> message_ts for updating HITL messages
        self._task_messages: dict[str, str] = {}
        # Maps task_name -> message_ts for command launch messages (separate from HITL)
        self._command_messages: dict[str, str] = {}

    @property
    def platform_name(self) -> str:
        return "Slack"

    def connect(self) -> None:
        self._web_client = WebClient(token=self._bot_token)
        self._socket_client = SocketModeClient(
            app_token=self._app_token,
            web_client=self._web_client,
        )
        self._socket_client.socket_mode_request_listeners.append(self._handle_event)
        self._socket_client.connect()
        self._connected = True

    def disconnect(self) -> None:
        if self._socket_client:
            self._socket_client.disconnect()
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def send_question(self, task_name: str, question_text: str) -> bool:
        if not self._web_client or not self._channel:
            return False
        try:
            # Truncate to Slack's limit
            if len(question_text) > 2900:
                question_text = question_text[:2900] + "..."
            response = self._web_client.chat_postMessage(
                channel=self._channel,
                text=f"*Dobby needs help with `{task_name}`*\n\n{question_text}\n\n_Reply in this thread to answer._",
                unfurl_links=False,
            )
            ts = response["ts"]
            with self._msg_lock:
                self._question_messages[ts] = task_name
                self._task_messages[task_name] = ts
            return True
        except Exception:
            return False

    def confirm_answer(self, task_name: str) -> None:
        with self._msg_lock:
            ts = self._task_messages.pop(task_name, None)
            if ts:
                self._question_messages.pop(ts, None)
        if ts and self._web_client and self._channel:
            try:
                self._web_client.reactions_add(
                    channel=self._channel, timestamp=ts, name="white_check_mark"
                )
            except Exception:
                pass

    def cancel_question(self, task_name: str) -> None:
        with self._msg_lock:
            ts = self._task_messages.get(task_name)
        if ts and self._web_client and self._channel:
            try:
                self._web_client.reactions_add(
                    channel=self._channel, timestamp=ts, name="x"
                )
                self._web_client.chat_postMessage(
                    channel=self._channel, thread_ts=ts,
                    text="_This question was answered in the terminal._",
                )
            except Exception:
                pass
        with self._msg_lock:
            if ts:
                self._question_messages.pop(ts, None)
            self._task_messages.pop(task_name, None)

    def send_completion(self, task_name: str, cost: float, output_dir: str, duration_secs: int = 0) -> bool:
        if not self._web_client or not self._channel:
            return False
        with self._msg_lock:
            ts = self._command_messages.get(task_name)
        try:
            dur = ""
            if duration_secs > 0:
                mins, secs = divmod(duration_secs, 60)
                dur = f" in {mins}m {secs}s" if mins else f" in {secs}s"
            text = f":white_check_mark: Dobby finished: `{task_name}`{dur} (${cost:.2f})\nOutput: `{output_dir}`"
            kwargs = dict(channel=self._channel, text=text, unfurl_links=False)
            if ts:
                kwargs["thread_ts"] = ts
            self._web_client.chat_postMessage(**kwargs)
            # Only pop after successful send
            with self._msg_lock:
                self._command_messages.pop(task_name, None)
            return True
        except Exception:
            return False

    def send_status(self, task_name: str, status_text: str) -> bool:
        if not self._web_client or not self._channel:
            return False
        with self._msg_lock:
            ts = self._task_messages.get(task_name)
        if not ts:
            return False
        try:
            self._web_client.chat_postMessage(
                channel=self._channel, thread_ts=ts, text=status_text,
            )
            return True
        except Exception:
            return False

    def _handle_event(self, client: SocketModeClient, req: SocketModeRequest) -> None:
        """Handle incoming Socket Mode events."""
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

        if req.type == "events_api":
            event = req.payload.get("event", {})
            if self._authorized_users and event.get("user") not in self._authorized_users:
                return  # unauthorized user
            if event.get("type") == "message":
                text = event.get("text", "").strip()
                user_id = event.get("user", "")

                # Thread reply → answer to a question
                if event.get("thread_ts"):
                    thread_ts = event["thread_ts"]
                    with self._msg_lock:
                        task_name = self._question_messages.get(thread_ts)
                    if task_name:
                        accepted = self._answer_callback(task_name, text)
                        if accepted:
                            self.confirm_answer(task_name)
                    return

                # Top-level "dobby <request>" → command
                # Only accept commands from the configured channel
                if self._channel and event.get("channel") != self._channel:
                    return

                lower = text.lower()
                if (lower.startswith("dobby ") or lower.startswith("dobby, ")) and self._command_callback:
                    request = text.split(None, 1)[1] if " " in text else ""
                    if request:
                        task_name = self._command_callback(request, user_id, "slack")
                        if task_name and self._web_client and self._channel:
                            try:
                                resp = self._web_client.chat_postMessage(
                                    channel=self._channel,
                                    text=f":zap: Dobby is on it: `{task_name}`\n_Launched from Slack by <@{user_id}>. You'll be notified when it completes._",
                                    unfurl_links=False,
                                )
                                ts = resp["ts"]
                                with self._msg_lock:
                                    self._command_messages[task_name] = ts
                            except Exception:
                                pass
                        elif not task_name and self._web_client and self._channel:
                            try:
                                self._web_client.chat_postMessage(
                                    channel=self._channel,
                                    text=f":x: Dobby couldn't launch that task. Too many active sessions or launch failed.",
                                    unfurl_links=False,
                                )
                            except Exception:
                                pass
