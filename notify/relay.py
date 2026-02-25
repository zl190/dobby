# /// script
# requires-python = ">=3.10"
# dependencies = ["discord.py"]
# ///
"""Level 2: Two-way HITL relay. Bridges messaging platforms with Dobby's
QUESTION.md/ANSWER.md filesystem protocol.

Can run as:
  - A per-question listener (started by SKILL.md on each question event)
  - A long-running daemon (started once per dobby session, handles all tasks)
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

if __name__ == "__main__" or "notify" not in sys.modules:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from notify.config import NotifyConfig, load_config
from notify.events import question_event, command_event, completed_event
from notify.webhook import dispatch as webhook_dispatch


class RelayServer:
    """Coordinates between messaging adapters and the filesystem HITL protocol.

    Lifecycle:
        1. relay = RelayServer(config, dobby_dir)
        2. relay.start()                      # starts adapter connections
        3. relay.post_question(task, text)     # sends question to platforms
        4. ... adapter calls relay.receive_answer(task, text) when user replies ...
        5. relay.stop()                        # clean shutdown

    Command interface:
        When command_handler is set, the relay listens for "dobby <request>"
        messages in Slack/Discord and launches tasks via the handler.
    """

    def __init__(self, config: NotifyConfig, dobby_dir: Path, command_handler=None):
        self.config = config
        self.dobby_dir = dobby_dir
        self.adapters: list = []
        self._pending_questions: dict[str, str] = {}  # task_name -> question_text
        self._answered: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._command_handler = command_handler  # (request, user, platform) -> task_name
        self._completed_commands: set[str] = set()  # dedup guard

    def start(self) -> None:
        """Initialize and connect configured adapters."""
        from notify.adapters import load_adapters
        self.adapters = load_adapters(
            self.config,
            answer_callback=self.receive_answer,
            command_callback=self._handle_command if self._command_handler else None,
        )
        for adapter in self.adapters:
            try:
                adapter.connect()
            except Exception as e:
                print(f"Warning: {adapter.platform_name} connection failed: {e}", file=sys.stderr)

    def stop(self) -> None:
        """Disconnect all adapters."""
        for adapter in self.adapters:
            try:
                adapter.disconnect()
            except Exception:
                pass
        self.adapters.clear()

    def post_question(self, task_name: str, question_text: str) -> None:
        """Send a HITL question to all connected messaging platforms."""
        with self._lock:
            self._pending_questions[task_name] = question_text
            self._answered[task_name] = threading.Event()

        # Send via webhook (Level 1)
        event = question_event(task_name, question_text)
        webhook_dispatch(event, self.config)

        # Send via bot adapters (Level 2)
        adapters = list(self.adapters)
        for adapter in adapters:
            try:
                adapter.send_question(task_name, question_text)
            except Exception as e:
                print(f"Warning: {adapter.platform_name} send failed: {e}", file=sys.stderr)

    def receive_answer(self, task_name: str, answer_text: str) -> bool:
        """Called by an adapter when a user replies to a question.

        Writes ANSWER.md and signals tmux. Returns True if the answer was
        accepted (question was still pending), False if already answered.
        """
        with self._lock:
            if task_name not in self._pending_questions:
                return False
            del self._pending_questions[task_name]
            event = self._answered.get(task_name)

        # Write ANSWER.md (atomic write to avoid partial reads)
        answer_path = self.dobby_dir / task_name / "records" / "ANSWER.md"
        answer_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(answer_path.parent), suffix='.tmp')
        fd_closed = False
        try:
            os.write(tmp_fd, answer_text.encode('utf-8'))
            os.close(tmp_fd)
            fd_closed = True
            os.rename(tmp_path, str(answer_path))
        except Exception:
            if not fd_closed:
                os.close(tmp_fd)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        # Signal tmux that answer is ready
        try:
            subprocess.run(
                ["tmux", "wait-for", "-S", f"dobby_{task_name}_answer"],
                capture_output=True, timeout=5,
            )
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
            pass

        # Notify adapters that this question is resolved
        adapters = list(self.adapters)
        for adapter in adapters:
            try:
                adapter.confirm_answer(task_name)
            except Exception:
                pass

        # Set the event for any local waiters, then clean up
        if event:
            event.set()
        with self._lock:
            self._answered.pop(task_name, None)

        return True

    def wait_for_answer(self, task_name: str, timeout: float = 300.0) -> bool:
        """Block until the question for task_name is answered."""
        with self._lock:
            event = self._answered.get(task_name)
        if event is None:
            return False
        return event.wait(timeout=timeout)

    def _handle_command(self, request: str, user_id: str, platform: str):
        """Called by an adapter when a user sends a command message.

        Launches the task first, then starts the waiter thread with the
        actual task name (which may have a collision suffix). The race
        window between launch and listener start is ~100ms — safe because
        claude -p takes many seconds to initialize.
        """
        if not self._command_handler:
            return None
        try:
            task_name = self._command_handler(request, user_id, platform)
            if task_name:
                # Fire webhook notification
                event = command_event(task_name, request, user_id, platform)
                webhook_dispatch(event, self.config)
                # Start waiter thread with the actual (possibly suffixed) name
                signal_name = f"dobby_cmd_{task_name}_done"
                listening = threading.Event()
                t = threading.Thread(
                    target=self._wait_for_command_completion,
                    args=(task_name, signal_name, listening),
                    daemon=True,
                )
                t.start()
                listening.wait(timeout=5)
            return task_name
        except Exception as e:
            print(f"Warning: command handler failed: {e}", file=sys.stderr)
            return None

    def _wait_for_command_completion(
        self, task_name: str, signal_name: str, listening: threading.Event,
    ) -> None:
        """Block on tmux wait-for signal, then post completion to adapters.

        Uses periodic liveness checks: if the tmux session dies without
        signaling, we bail out instead of blocking for an hour.
        """
        session_name = f"dobby-cmd-{task_name}"

        # Start the blocking wait in a subprocess
        proc = subprocess.Popen(
            ["tmux", "wait-for", signal_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        listening.set()  # signal that we're now listening

        # Poll: check if the subprocess finished OR session died
        # Short poll interval (1s) for responsiveness; liveness check every 30 polls
        try:
            polls = 0
            while True:
                ret = proc.poll()
                if ret is not None:
                    break  # signal received (or tmux error)
                polls += 1
                if polls % 30 == 0:
                    # Check session liveness every ~30s
                    check = subprocess.run(
                        ["tmux", "has-session", "-t", session_name],
                        capture_output=True, timeout=5,
                    )
                    if check.returncode != 0:
                        # Session gone without signaling — bail out
                        proc.terminate()
                        proc.wait(timeout=5)
                        return
                time.sleep(1)
        except Exception:
            proc.terminate()
            proc.wait(timeout=5)
            return

        # Dedup guard
        with self._lock:
            if task_name in self._completed_commands:
                return
            self._completed_commands.add(task_name)

        # Read cost and duration from claude -p output file
        cost = 0.0
        duration_secs = 0
        cost_file = Path(f"/tmp/dobby_cmd_{task_name}_output.txt")
        if cost_file.exists():
            try:
                data = json.loads(cost_file.read_text())
                cost = float(data.get("total_cost_usd", 0))
                duration_secs = int(data.get("duration_ms", 0)) // 1000
            except (json.JSONDecodeError, ValueError, OSError):
                pass

        output_dir = f".dobby/{task_name}/output/"

        # Dispatch webhook (Level 1) — parity with regular task completions
        try:
            ev = completed_event(task_name, cost, output_dir)
            webhook_dispatch(ev, self.config)
        except Exception:
            pass

        # Dispatch to bot adapters (Level 2) — snapshot AFTER wait, not before
        adapters = list(self.adapters)
        for adapter in adapters:
            try:
                adapter.send_completion(task_name, cost, output_dir, duration_secs)
            except Exception as e:
                print(f"Warning: {adapter.platform_name} completion failed: {e}", file=sys.stderr)

    def send_status(self, task_name: str, status_text: str) -> None:
        """Send a status update to all adapters for a command-launched task."""
        adapters = list(self.adapters)
        for adapter in adapters:
            try:
                adapter.send_status(task_name, status_text)
            except Exception:
                pass

    def cancel_question(self, task_name: str) -> None:
        """Cancel a pending question (e.g., user answered in terminal instead)."""
        with self._lock:
            self._pending_questions.pop(task_name, None)
            event = self._answered.get(task_name)
        adapters = list(self.adapters)
        for adapter in adapters:
            try:
                adapter.cancel_question(task_name)
            except Exception:
                pass
        # Set the event so wait_for_answer unblocks, then clean up
        if event:
            event.set()
        with self._lock:
            self._answered.pop(task_name, None)


class TerminalAnswerWatcher:
    """Watches for ANSWER.md files created by the terminal HITL flow.

    When the orchestrator writes ANSWER.md from a terminal answer, this
    watcher detects it and cancels the pending bot question.
    """

    def __init__(self, relay: RelayServer, dobby_dir: Path, task_name: str):
        self.relay = relay
        self.answer_path = dobby_dir / task_name / "records" / "ANSWER.md"
        self.task_name = task_name
        self._stop = threading.Event()

    def watch(self) -> None:
        """Poll for ANSWER.md appearance. Runs in a thread."""
        while not self._stop.is_set():
            if self.answer_path.exists():
                self.relay.cancel_question(self.task_name)
                return
            self._stop.wait(0.5)

    def stop(self) -> None:
        self._stop.set()


def main():
    """CLI: relay.py listen --task NAME --timeout SECONDS
           relay.py daemon  (long-running, watches all tasks, handles commands)
    """
    import argparse

    parser = argparse.ArgumentParser(description="Dobby HITL relay")
    sub = parser.add_subparsers(dest="command")

    listen_p = sub.add_parser("listen", help="Listen for one answer to a specific task")
    listen_p.add_argument("--task", required=True)
    listen_p.add_argument("--timeout", type=int, default=300)

    daemon_p = sub.add_parser("daemon", help="Long-running relay daemon for all tasks")
    daemon_p.add_argument("--enable-commands", action="store_true",
                          help="Enable command interface (launch tasks from chat)")

    args = parser.parse_args()

    config = load_config()
    if not config.has_any_bot:
        sys.exit(0)

    dobby_dir = Path.cwd() / ".dobby"

    # Set up command handler if enabled
    command_handler = None
    if getattr(args, "enable_commands", False):
        from notify.commander import launch_task
        command_handler = launch_task

    relay = RelayServer(config, dobby_dir, command_handler=command_handler)

    def shutdown(signum, frame):
        relay.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    relay.start()

    if args.command == "listen":
        # Read the current question
        question_path = dobby_dir / args.task / "records" / "QUESTION.md"
        if question_path.exists():
            relay.post_question(args.task, question_path.read_text())

        # Start terminal answer watcher in background
        watcher = TerminalAnswerWatcher(relay, dobby_dir, args.task)
        watcher_thread = threading.Thread(target=watcher.watch, daemon=True)
        watcher_thread.start()

        # Wait for answer from either source
        answered = relay.wait_for_answer(args.task, timeout=args.timeout)
        watcher.stop()
        relay.stop()

        sys.exit(0 if answered else 1)

    elif args.command == "daemon":
        mode = "commands + relay" if command_handler else "relay only"
        print(f"Dobby relay daemon started ({mode}). Ctrl-C to stop.")
        try:
            signal.pause()
        except AttributeError:
            # signal.pause() not available on Windows
            while True:
                time.sleep(1)


if __name__ == "__main__":
    main()
