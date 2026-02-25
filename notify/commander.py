# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Command launcher: receives requests from Slack/Discord and launches Dobby tasks.

This is the bridge between the relay's command callback and the actual
orchestrator (claude -p). It shells out to launch a tmux session with
the Dobby skill, just like typing `/dobby "request"` in the terminal.
"""

import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

if __name__ == "__main__" or "notify" not in sys.modules:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MAX_CONCURRENT_COMMANDS = 5


def slugify(text: str) -> str:
    """Convert request text to a task slug."""
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower().strip())
    slug = slug.strip('-')[:40]
    return slug or "task"


def _count_active_command_sessions() -> int:
    """Count active dobby-cmd-* tmux sessions."""
    result = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return 0
    return sum(1 for s in result.stdout.strip().splitlines() if s.startswith("dobby-cmd-"))


def launch_task(request: str, user_id: str, platform: str) -> Optional[str]:
    """Launch a Dobby task from a chat command.

    Creates a tmux session that runs `claude -p` with the Dobby skill,
    passing the user's request. Returns the task slug on success, None on failure.
    """
    # Rate limit: reject if too many concurrent command sessions
    if _count_active_command_sessions() >= MAX_CONCURRENT_COMMANDS:
        print(f"Rate limit: {MAX_CONCURRENT_COMMANDS} command sessions already active", file=sys.stderr)
        return None

    task_name = slugify(request)

    # Avoid collisions with existing sessions
    result = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True, text=True,
    )
    existing = result.stdout.strip().splitlines() if result.returncode == 0 else []
    if f"dobby-cmd-{task_name}" in existing:
        counter = 2
        while f"dobby-cmd-{task_name}-{counter}" in existing:
            counter += 1
        task_name = f"{task_name}-{counter}"

    session_name = f"dobby-cmd-{task_name}"
    cwd = os.environ.get("DOBBY_WORK_DIR", os.getcwd())

    # Write prompt to a temp file to avoid shell injection
    prompt_text = (
        f"Use the dobby skill to work on this request: {request}. "
        f"This was launched remotely from {platform} by user {user_id}."
    )
    try:
        prompt_fd, prompt_path = tempfile.mkstemp(
            prefix=f"dobby_cmd_{task_name}_", suffix=".txt",
            dir=tempfile.gettempdir(),
        )
        os.write(prompt_fd, prompt_text.encode("utf-8"))
        os.close(prompt_fd)
    except OSError as e:
        print(f"Failed to write prompt file: {e}", file=sys.stderr)
        return None

    # Build command using shlex.quote for safety
    # Chain a tmux signal after claude exits so the relay daemon knows it's done
    signal_name = f"dobby_cmd_{task_name}_done"
    cost_file = f"/tmp/dobby_cmd_{task_name}_output.txt"
    cmd = (
        f'cd {shlex.quote(cwd)} && '
        f'claude -p --model claude-sonnet-4-6 --dangerously-skip-permissions --output-format json '
        f'"$(cat {shlex.quote(prompt_path)})" '
        f'2>&1 | tee {shlex.quote(cost_file)} ; '
        f'rm -f {shlex.quote(prompt_path)} ; '
        f'tmux wait-for -S {shlex.quote(signal_name)} ; '
        f'tmux kill-session -t {shlex.quote(session_name)} 2>/dev/null'
    )

    try:
        r = subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name],
            capture_output=True, timeout=5,
        )
        if r.returncode != 0:
            print(f"Failed to create tmux session '{session_name}': {r.stderr.strip()}", file=sys.stderr)
            os.unlink(prompt_path)
            return None
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, cmd, "Enter"],
            capture_output=True, timeout=5,
        )
        return task_name
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError) as e:
        print(f"Failed to launch task '{task_name}': {e}", file=sys.stderr)
        os.unlink(prompt_path)
        return None


def main():
    """CLI: commander.py launch --request "build an API" --user U123 --platform slack"""
    import argparse

    parser = argparse.ArgumentParser(description="Dobby command launcher")
    sub = parser.add_subparsers(dest="command")

    launch_p = sub.add_parser("launch", help="Launch a task from a chat command")
    launch_p.add_argument("--request", required=True)
    launch_p.add_argument("--user", default="unknown")
    launch_p.add_argument("--platform", default="cli")

    args = parser.parse_args()

    if args.command == "launch":
        task_name = launch_task(args.request, args.user, args.platform)
        if task_name:
            print(f"Launched: {task_name} (session: dobby-cmd-{task_name})")
        else:
            print("Launch failed", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
