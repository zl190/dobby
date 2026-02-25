# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Dobby progress bar — watches a task folder and shows live progress."""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def cyan(t): return f"\033[36m{t}\033[0m"
def green(t): return f"\033[32m{t}\033[0m"
def yellow(t): return f"\033[1;33m{t}\033[0m"
def dim(t): return f"\033[2m{t}\033[0m"
def bright(t): return f"\033[1m{t}\033[0m"


def check_phase(task_dir: Path) -> dict:
    """Detect which phase the task is in by checking filesystem state."""
    state = {
        "claude_md": (task_dir / "CLAUDE.md").exists(),
        "todo": (task_dir / "records" / "TODO.md").exists(),
        "registry": (task_dir / "records" / "version_registry.md").exists(),
        "output_files": [],
        "todo_in_progress": [],
        "todo_done": [],
        "tmux_alive": False,
        "cost": None,
        "duration": None,
    }

    # Check output files
    output_dir = task_dir / "output"
    if output_dir.exists():
        state["output_files"] = [f.name for f in output_dir.iterdir() if f.is_file()]

    # Parse TODO.md
    todo_path = task_dir / "records" / "TODO.md"
    if todo_path.exists():
        text = todo_path.read_text()
        items = re.findall(r"- \[ \] (.+?)(?:\n|$)", text)
        state["todo_in_progress"] = [re.sub(r"\*\*(.+?)\*\*", r"\1", i).strip() for i in items]
        state["todo_done"] = re.findall(r"- \[x\] (.+?)(?:\n|$)", text)

    # Check tmux
    task_name = task_dir.name
    try:
        result = subprocess.run(
            ["tmux", "list-sessions"], capture_output=True, text=True, timeout=5
        )
        state["tmux_alive"] = f"dobby-{task_name}" in result.stdout
    except Exception:
        pass

    # Check cost
    cost_file = Path(f"/tmp/dobby_{task_name}_output.txt")
    if cost_file.exists():
        text = cost_file.read_text().strip()
        for line in reversed(text.splitlines()):
            if line.strip().startswith("{"):
                try:
                    data = json.loads(line.strip())
                    if "total_cost_usd" in data:
                        state["cost"] = data["total_cost_usd"]
                        state["duration"] = data.get("duration_ms", 0)
                        break
                except json.JSONDecodeError:
                    continue

    return state


def determine_progress(state: dict) -> tuple[int, str, list[tuple[str, str]]]:
    """Return (percent, status_text, phase_list)."""
    phases = []

    # Phase 1: CLAUDE.md exists
    if state["claude_md"]:
        phases.append(("done", "Task configured"))
    else:
        phases.append(("pending", "Task setup"))

    # Phase 2: Records initialized
    if state["todo"] or state["registry"]:
        phases.append(("done", "Records initialized"))
    elif state["claude_md"]:
        phases.append(("active", "Setting up records..."))
    else:
        phases.append(("pending", "Records"))

    # Phase 3: Work in progress
    if state["todo_done"] or state["output_files"]:
        phases.append(("done", "Work complete"))
    elif state["todo"]:
        phases.append(("active", "Working..."))
    else:
        phases.append(("pending", "Work"))

    # Phase 4: Deliverable
    if state["output_files"] and not state["tmux_alive"]:
        phases.append(("done", "Deliverable written"))
    elif state["output_files"]:
        phases.append(("active", "Refining deliverable..."))
    else:
        phases.append(("pending", "Deliverable"))

    # Calculate percentage
    done_count = sum(1 for s, _ in phases if s == "done")
    total = len(phases)
    active_bonus = 0.5 if any(s == "active" for s, _ in phases) else 0
    pct = int(((done_count + active_bonus) / total) * 100)

    if not state["tmux_alive"] and state["output_files"]:
        pct = 100
        status = "Complete"
    elif not state["tmux_alive"] and state["cost"] is not None:
        pct = 100
        status = "Complete"
    elif state["tmux_alive"]:
        status = "Working..."
    else:
        status = "Starting..."

    return pct, status, phases


def render(task_name: str, task_dir: Path, pct: int, status: str, phases: list, state: dict):
    """Render the progress display."""
    print("\033[H\033[J", end="")  # cursor home + clear below (preserves scrollback)

    # Header
    print(f"  {bright(cyan(f'⚡ Dobby: {task_name}'))}")
    print()

    # Progress bar
    bar_width = 30
    filled = int(bar_width * pct / 100)
    empty = bar_width - filled
    bar = "━" * filled + "░" * empty
    if pct == 100:
        print(f"  {green(bar)}  {bright(green(f'{pct}%'))}  {green(status)}")
    else:
        print(f"  {yellow(bar)}  {bright(yellow(f'{pct}%'))}  {yellow(status)}")
    print()

    # Phase list
    for phase_status, label in phases:
        if phase_status == "done":
            print(f"  {green('✓')} {label}")
        elif phase_status == "active":
            print(f"  {yellow('▸')} {yellow(label)}")
        else:
            print(f"  {dim('○')} {dim(label)}")

    # In-progress items from TODO
    if state["todo_in_progress"]:
        print()
        for item in state["todo_in_progress"][:3]:
            print(f"    {yellow('▸')} {item[:60]}")

    # Done items from TODO
    if state["todo_done"]:
        for item in state["todo_done"][:3]:
            print(f"    {green('✓')} {item[:60]}")

    # Output files
    if state["output_files"]:
        print()
        for f in state["output_files"][:5]:
            fpath = task_dir / "output" / f
            size = fpath.stat().st_size if fpath.exists() else 0
            size_str = f"{size/1024:.1f} KB" if size > 1024 else f"{size} B"
            print(f"  📦 {f} ({size_str})")

    # Cost
    if state["cost"] is not None:
        duration_s = state["duration"] / 1000 if state["duration"] else 0
        mins = int(duration_s // 60)
        secs = int(duration_s % 60)
        print(f"  💰 ${state['cost']:.2f}  ⏱  {mins}m {secs}s")

    print()


def watch(task_name: str, task_dir: Path, once: bool = False):
    """Watch loop — refresh every 5 seconds."""
    if not once:
        print("\033[?1049h", end="")  # switch to alternate screen buffer
    try:
        while True:
            state = check_phase(task_dir)
            pct, status, phases = determine_progress(state)
            render(task_name, task_dir, pct, status, phases, state)

            if once or pct == 100:
                break

            print(dim(f"  Refreshing every 5s... Ctrl-C to exit"))
            try:
                time.sleep(5)
            except KeyboardInterrupt:
                print()
                break
    finally:
        if not once:
            print("\033[?1049l", end="")  # restore main screen buffer


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: progress.py <task-name> [--once]")
        print("  Watches .dobby/<task-name>/ for progress")
        sys.exit(1)

    task_name = sys.argv[1]
    once = "--once" in sys.argv

    # Try to find the task directory
    task_dir = Path(f".dobby/{task_name}")
    if not task_dir.exists():
        # Try absolute path from CWD
        task_dir = Path.cwd() / ".dobby" / task_name

    if not task_dir.exists():
        print(f"Task folder not found: .dobby/{task_name}/")
        sys.exit(1)

    watch(task_name, task_dir, once=once)
