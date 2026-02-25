# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Dobby smoke test — full pipeline with mock agent. No API calls, no cost."""

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
TASK_NAME = "smoke-test"
DOBBY_DIR = Path(".dobby")
TASK_DIR = DOBBY_DIR / TASK_NAME
TEAM_TASKS = ["smoke-team-a", "smoke-team-b"]
CONVERGE_TASK = "smoke-converge"


def run(cmd, **kwargs):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kwargs)


def cleanup():
    if TASK_DIR.exists():
        shutil.rmtree(TASK_DIR)
    cost_file = Path(f"/tmp/dobby_{TASK_NAME}_output.txt")
    if cost_file.exists():
        cost_file.unlink()
    run(f"tmux kill-session -t dobby-{TASK_NAME} 2>/dev/null")
    # Clean up multi-agent team tasks and convergence task
    all_slugs = [TASK_NAME] + TEAM_TASKS + [CONVERGE_TASK]
    for slug in TEAM_TASKS + [CONVERGE_TASK]:
        team_dir = DOBBY_DIR / slug
        if team_dir.exists():
            shutil.rmtree(team_dir)
        team_cost = Path(f"/tmp/dobby_{slug}_output.txt")
        if team_cost.exists():
            team_cost.unlink()
        run(f"tmux kill-session -t dobby-{slug} 2>/dev/null")
    # Clean up convergence-specific sessions and files
    for suffix in ["-prod", "-qual"]:
        run(f"tmux kill-session -t dobby-{CONVERGE_TASK}{suffix} 2>/dev/null")
    for f in Path("/tmp").glob(f"dobby_{CONVERGE_TASK}_*"):
        f.unlink(missing_ok=True)
    for f in Path("/tmp").glob("dobby_qual_*"):
        if f.is_dir():
            shutil.rmtree(f, ignore_errors=True)
    # Clean up bot-completion test artifacts
    comp_dir = DOBBY_DIR / "comp-test"
    if comp_dir.exists():
        shutil.rmtree(comp_dir)
    comp_cost = Path("/tmp/dobby_cmd_comp-test_output.txt")
    if comp_cost.exists():
        comp_cost.unlink()
    roster = DOBBY_DIR / "records" / "roster.md"
    if roster.exists():
        lines = roster.read_text().splitlines()
        lines = [l for l in lines if not (l.strip().startswith("|") and l.split("|")[1].strip() in all_slugs)]
        roster.write_text("\n".join(lines) + "\n")


def mock_team_agent_script(slug: str, other_slug: str) -> str:
    """Mock agent for multi-agent test. Writes a deliverable and exits."""
    task_dir = (DOBBY_DIR / slug).resolve()
    other_output = (DOBBY_DIR / other_slug / "output").resolve()
    return f"""#!/bin/bash
cd {task_dir}
sleep 1
mkdir -p records output
cat > records/TODO.md << 'EOF'
# Action Queue
## Done
- [x] Write deliverable
EOF
cat > output/result.md << EOF
# Team Agent: {slug}
Deliverable from {slug}.
Other agent output dir: {other_output}
EOF
sleep 1
"""


def mock_agent_script(today: str) -> str:
    return f"""#!/bin/bash
cd {TASK_DIR.resolve()}
sleep 1
mkdir -p records output
cat > records/TODO.md << 'EOF'
# Action Queue
## In Progress
- [ ] **Write deliverable**
## Done
EOF
cat > records/version_registry.md << 'EOF'
| Version | Date | Strategy | Score | Key Change |
|---|---|---|---|---|
EOF

# --- Human-in-the-loop: ask a question ---
cat > records/QUESTION.md << 'EOF'
## Dobby needs help

I need you to scan a QR code to log in to the platform.
Please scan and confirm when done.

**Waiting for your response...**
EOF
tmux wait-for -S dobby_{TASK_NAME}_question
tmux wait-for dobby_{TASK_NAME}_answer
ANSWER=$(cat records/ANSWER.md 2>/dev/null || echo "no answer")
# --- Continue after getting answer ---

sleep 1
cat > output/analysis.md << EOF
# Smoke Test Deliverable
Mock output. Pipeline verified.
User answered: $ANSWER
EOF
cat > records/TODO.md << 'EOF'
# Action Queue
## Done
- [x] Write deliverable
- [x] Set up infrastructure
- [x] Got user input
# Decision Log
| Decision | Rationale | Date |
| Mock | Smoke test | {today} |
EOF
sleep 1
"""


def main():
    results = []
    total_start = time.time()

    print("\033[1;33m⚡ Dobby Smoke Test\033[0m\n")

    cleanup()

    # 1. Bootstrap
    if not DOBBY_DIR.exists():
        os.makedirs(DOBBY_DIR / "records", exist_ok=True)
        (DOBBY_DIR / "records" / "roster.md").write_text(
            "| Task | Folder | Status | Budget | Spent | Started | Last Update |\n|---|---|---|---|---|---|---|\n"
        )

    results.append(("Bootstrap", (DOBBY_DIR / "records" / "roster.md").exists()))

    # 2. Scaffold task
    os.makedirs(TASK_DIR / "records", exist_ok=True)
    os.makedirs(TASK_DIR / "output", exist_ok=True)
    claude_md = f"""# Mission
Write a smoke test deliverable.

## Asking for Help
If you need something you cannot do yourself:
1. Write your question to `records/QUESTION.md`
2. Run: `tmux wait-for -S dobby_{TASK_NAME}_question`
3. Run: `tmux wait-for dobby_{TASK_NAME}_answer`
4. Read the answer from `records/ANSWER.md`
5. Delete both files and continue working

## State Management
Track progress in `records/TODO.md`. Write deliverables to `output/`.
"""
    (TASK_DIR / "CLAUDE.md").write_text(claude_md)

    today = datetime.now().strftime("%Y-%m-%d")
    with open(DOBBY_DIR / "records" / "roster.md", "a") as f:
        f.write(f"| {TASK_NAME} | {TASK_NAME} | Running | $1.00 | $0.00 | {today} | {today} |\n")

    results.append(("Scaffold", (TASK_DIR / "CLAUDE.md").exists() and "Mission" in (TASK_DIR / "CLAUDE.md").read_text()))

    # 3. Mock agent in tmux
    mock_script = TASK_DIR / "_mock.sh"
    mock_script.write_text(mock_agent_script(today))
    mock_script.chmod(0o755)
    run(f"tmux new-session -d -s dobby-{TASK_NAME}")
    run(f"tmux send-keys -t dobby-{TASK_NAME} 'bash {mock_script.resolve()} ; tmux wait-for -S dobby_{TASK_NAME}_done' Enter")
    results.append(("Tmux launch", f"dobby-{TASK_NAME}" in run("tmux list-sessions").stdout))

    # 4. Human-in-the-loop: wait for question signal
    r = run(f"timeout 10 tmux wait-for dobby_{TASK_NAME}_question")
    question_file = TASK_DIR / "records" / "QUESTION.md"
    question_received = r.returncode == 0 and question_file.exists()
    results.append(("Question relay", question_received))

    # 5. Answer the question and signal back
    if question_received:
        (TASK_DIR / "records" / "ANSWER.md").write_text("QR code scanned. Confirmed.")
    run(f"tmux wait-for -S dobby_{TASK_NAME}_answer")

    # 6. Progress bar
    time.sleep(1)
    r = run(f"uv run {SKILL_DIR / 'progress.py'} {TASK_NAME} --once")
    results.append(("Progress bar", r.returncode == 0))

    # 7. Completion signal
    r = run(f"timeout 15 tmux wait-for dobby_{TASK_NAME}_done")
    results.append(("Completion signal", r.returncode == 0))

    # 8. Deliverables — check that agent used our answer
    Path(f"/tmp/dobby_{TASK_NAME}_output.txt").write_text(json.dumps({
        "total_cost_usd": 0.0, "num_turns": 3, "duration_ms": 5000,
    }))
    deliverable = TASK_DIR / "output" / "analysis.md"
    has_answer = deliverable.exists() and "QR code scanned" in deliverable.read_text()
    results.append(("Deliverables", has_answer))

    # 9. Complete state
    run(f"tmux kill-session -t dobby-{TASK_NAME} 2>/dev/null")
    r = run(f"uv run {SKILL_DIR / 'progress.py'} {TASK_NAME} --once")
    results.append(("Complete state", "100%" in r.stdout))

    # 10. Multi-agent team: launch 2 mock agents, verify both complete
    for slug in TEAM_TASKS:
        team_dir = DOBBY_DIR / slug
        os.makedirs(team_dir / "records", exist_ok=True)
        os.makedirs(team_dir / "output", exist_ok=True)
        other = [s for s in TEAM_TASKS if s != slug][0]
        team_claude_md = f"""# Mission
Deliver result for {slug}.

## Team Context
You are part of a team working on: "smoke test multi-agent"
Your specific task: "{slug}"
Other team members and their output directories:
- {other} → .dobby/{other}/output/
You may read other team members' output/ directories for coordination.

## State Management
Track progress in `records/TODO.md`. Write deliverables to `output/`.
"""
        (team_dir / "CLAUDE.md").write_text(team_claude_md)
        script = team_dir / "_mock.sh"
        script.write_text(mock_team_agent_script(slug, other))
        script.chmod(0o755)
        run(f"tmux new-session -d -s dobby-{slug}")
        run(f"tmux send-keys -t dobby-{slug} 'bash {script.resolve()} ; tmux wait-for -S dobby_{slug}_done' Enter")

    # Wait for both completion signals
    team_ok = True
    for slug in TEAM_TASKS:
        r = run(f"timeout 15 tmux wait-for dobby_{slug}_done")
        if r.returncode != 0:
            team_ok = False

    # Verify both deliverables exist
    for slug in TEAM_TASKS:
        deliverable = DOBBY_DIR / slug / "output" / "result.md"
        if not deliverable.exists() or slug not in deliverable.read_text():
            team_ok = False

    results.append(("Multi-agent team", team_ok))

    # Clean up team tmux sessions
    for slug in TEAM_TASKS:
        run(f"tmux kill-session -t dobby-{slug} 2>/dev/null")

    # 11. Convergence loop: production -> quality -> iterate -> ship
    conv_dir = DOBBY_DIR / CONVERGE_TASK
    os.makedirs(conv_dir / "records", exist_ok=True)
    os.makedirs(conv_dir / "output", exist_ok=True)

    # Write quality rubric
    (conv_dir / "quality_rubric.md").write_text(
        "# Evaluation Rubric\nScore the deliverable 1-10.\nWrite EVAL_RESULT.json.\n"
    )

    # Write loop state
    (conv_dir / "records" / "loop_state.json").write_text(json.dumps({
        "iteration": 0, "max_iterations": 3, "scores": [], "status": "running"
    }))

    # Write version registry headers
    (conv_dir / "records" / "version_registry.md").write_text(
        "| Version | Date | Strategy | Score | Key Change |\n|---|---|---|---|---|\n"
    )

    # --- Iteration 1: production v1 ---
    prod_v1_script = conv_dir / "_prod_v1.sh"
    prod_v1_script.write_text(f"""#!/bin/bash
cd {conv_dir.resolve()}
sleep 1
cat > output/deliverable.md << 'EOF'
# Draft v1
First version of the deliverable.
EOF
cat > records/TODO.md << 'EOF'
# Action Queue
## Done
- [x] Write v1 draft
EOF
""")
    prod_v1_script.chmod(0o755)
    run(f"tmux new-session -d -s dobby-{CONVERGE_TASK}-prod")
    run(f"tmux send-keys -t dobby-{CONVERGE_TASK}-prod 'bash {prod_v1_script.resolve()} ; tmux wait-for -S dobby_{CONVERGE_TASK}_prod_v1_done' Enter")
    r = run(f"timeout 10 tmux wait-for dobby_{CONVERGE_TASK}_prod_v1_done")
    prod_v1_ok = r.returncode == 0 and (conv_dir / "output" / "deliverable.md").exists()
    run(f"tmux kill-session -t dobby-{CONVERGE_TASK}-prod 2>/dev/null")

    # --- Iteration 1: quality evaluation (in isolated temp dir) ---
    qual_dir = Path(f"/tmp/dobby_qual_{CONVERGE_TASK}_test")
    if qual_dir.exists():
        shutil.rmtree(qual_dir)
    qual_dir.mkdir(parents=True)
    shutil.copy(conv_dir / "output" / "deliverable.md", qual_dir / "deliverable.md")
    shutil.copy(conv_dir / "quality_rubric.md", qual_dir / "CLAUDE.md")

    qual_v1_script = qual_dir / "_qual.sh"
    qual_v1_script.write_text(f"""#!/bin/bash
cd {qual_dir}
sleep 1
cat > EVAL_RESULT.json << 'EOF'
{{"score": 6.5, "dimensions": {{"clarity": 7, "completeness": 6}}, "issues": ["Needs more detail", "Missing examples"], "strengths": ["Good structure"]}}
EOF
""")
    qual_v1_script.chmod(0o755)
    run(f"tmux new-session -d -s dobby-{CONVERGE_TASK}-qual")
    run(f"tmux send-keys -t dobby-{CONVERGE_TASK}-qual 'bash {qual_v1_script.resolve()} ; tmux wait-for -S dobby_{CONVERGE_TASK}_qual_v1_done' Enter")
    r = run(f"timeout 10 tmux wait-for dobby_{CONVERGE_TASK}_qual_v1_done")
    qual_v1_ok = r.returncode == 0 and (qual_dir / "EVAL_RESULT.json").exists()
    run(f"tmux kill-session -t dobby-{CONVERGE_TASK}-qual 2>/dev/null")

    # Copy eval result back (as orchestrator would)
    if qual_v1_ok:
        shutil.copy(qual_dir / "EVAL_RESULT.json", conv_dir / "records" / "EVAL_RESULT_v1.json")
        # Update version registry
        with open(conv_dir / "records" / "version_registry.md", "a") as f:
            f.write(f"| v1 | {today} | initial | 6.5 | First draft |\n")
        # Write feedback for next iteration
        (conv_dir / "records" / "EVAL_FEEDBACK.md").write_text(
            "## Issues to fix\n- Needs more detail\n- Missing examples\n"
        )

    # Verify isolation: quality agent dir should NOT contain version_registry or loop_state
    isolation_ok = (
        not (qual_dir / "version_registry.md").exists()
        and not (qual_dir / "loop_state.json").exists()
        and not (qual_dir / "records").exists()
    )
    shutil.rmtree(qual_dir, ignore_errors=True)

    # --- Iteration 2: production v2 (reads feedback, improves) ---
    prod_v2_script = conv_dir / "_prod_v2.sh"
    prod_v2_script.write_text(f"""#!/bin/bash
cd {conv_dir.resolve()}
sleep 1
FEEDBACK=$(cat records/EVAL_FEEDBACK.md 2>/dev/null || echo "none")
cat > output/deliverable.md << EOF
# Draft v2
Improved version with more detail and examples.
Addressed feedback: $FEEDBACK
EOF
""")
    prod_v2_script.chmod(0o755)
    run(f"tmux new-session -d -s dobby-{CONVERGE_TASK}-prod")
    run(f"tmux send-keys -t dobby-{CONVERGE_TASK}-prod 'bash {prod_v2_script.resolve()} ; tmux wait-for -S dobby_{CONVERGE_TASK}_prod_v2_done' Enter")
    r = run(f"timeout 10 tmux wait-for dobby_{CONVERGE_TASK}_prod_v2_done")
    prod_v2_ok = r.returncode == 0
    run(f"tmux kill-session -t dobby-{CONVERGE_TASK}-prod 2>/dev/null")

    # Verify v2 incorporated feedback
    v2_has_feedback = False
    if prod_v2_ok:
        v2_text = (conv_dir / "output" / "deliverable.md").read_text()
        v2_has_feedback = "Improved" in v2_text and "v2" in v2_text.lower()
        # Update version registry
        with open(conv_dir / "records" / "version_registry.md", "a") as f:
            f.write(f"| v2 | {today} | optimization | 8.2 | Added detail and examples |\n")

    # Check version registry has trajectory
    registry_text = (conv_dir / "records" / "version_registry.md").read_text()
    registry_ok = "v1" in registry_text and "v2" in registry_text and "6.5" in registry_text

    converge_ok = all([prod_v1_ok, qual_v1_ok, isolation_ok, prod_v2_ok, v2_has_feedback, registry_ok])
    results.append(("Convergence loop", converge_ok))

    # 12. Webhook notification: test event creation and payload formatting
    try:
        sys.path.insert(0, str(SKILL_DIR))
        from notify.events import completed_event, question_event, convergence_event, team_done_event, EventType
        from notify.webhook import format_slack_payload, format_discord_payload
        from notify.config import NotifyConfig, load_config

        ev = completed_event("test-task", 1.50, ".dobby/test-task/output/", 30000)
        slack_p = format_slack_payload(ev)
        discord_p = format_discord_payload(ev)
        config = load_config()  # should return disabled config (no env vars set)

        webhook_ok = (
            ev.event_type == EventType.COMPLETED
            and ev.task_name == "test-task"
            and "$1.50" in ev.message
            and "blocks" in slack_p
            and "embeds" in discord_p
            and not config.has_any_webhook  # no webhook configured in test env
        )
    except Exception as e:
        webhook_ok = False
        print(f"    Webhook test error: {e}")
    results.append(("Webhook notifications", webhook_ok))

    # 13. Two-way relay: test RelayServer with mock adapter, verify answer flow
    try:
        from notify.relay import RelayServer, TerminalAnswerWatcher
        from notify.adapters.base import BaseAdapter, AnswerCallback
        import threading

        # Create a mock adapter inline
        class MockAdapter(BaseAdapter):
            def __init__(self, answer_callback):
                super().__init__(answer_callback)
                self._connected = False
                self.sent = []
                self.confirmed = []
                self.cancelled = []

            @property
            def platform_name(self): return "Mock"
            def connect(self): self._connected = True
            def disconnect(self): self._connected = False
            def is_connected(self): return self._connected
            def send_question(self, task_name, text):
                self.sent.append((task_name, text))
                return True
            def confirm_answer(self, task_name): self.confirmed.append(task_name)
            def cancel_question(self, task_name): self.cancelled.append(task_name)

        relay_config = NotifyConfig(enabled=False)  # no webhooks
        relay_dir = DOBBY_DIR
        relay = RelayServer(relay_config, relay_dir)

        # Manually inject mock adapter
        mock = MockAdapter(relay.receive_answer)
        mock.connect()
        relay.adapters = [mock]

        # Post a question
        relay_task = "relay-test"
        relay_task_dir = relay_dir / relay_task / "records"
        os.makedirs(relay_task_dir, exist_ok=True)
        relay.post_question(relay_task, "What database?")

        # Verify question was sent to mock adapter
        q_sent = len(mock.sent) == 1 and mock.sent[0] == (relay_task, "What database?")

        # Simulate bot answer
        accepted = relay.receive_answer(relay_task, "PostgreSQL")

        # Verify answer was written to filesystem
        answer_path = relay_task_dir / "ANSWER.md"
        answer_written = answer_path.exists() and "PostgreSQL" in answer_path.read_text()

        # Verify confirm was called
        confirmed = relay_task in mock.confirmed

        # Verify duplicate answer is rejected
        rejected = not relay.receive_answer(relay_task, "MySQL")

        # Test terminal answer watcher (cancel path)
        relay.post_question("watcher-test", "Another question?")
        os.makedirs(relay_dir / "watcher-test" / "records", exist_ok=True)
        watcher = TerminalAnswerWatcher(relay, relay_dir, "watcher-test")
        watcher_thread = threading.Thread(target=watcher.watch, daemon=True)
        watcher_thread.start()
        # Simulate terminal writing ANSWER.md
        (relay_dir / "watcher-test" / "records" / "ANSWER.md").write_text("terminal answer")
        time.sleep(1)
        watcher_cancelled = "watcher-test" in mock.cancelled

        relay.stop()
        # Cleanup
        shutil.rmtree(relay_dir / relay_task, ignore_errors=True)
        shutil.rmtree(relay_dir / "watcher-test", ignore_errors=True)

        relay_ok = all([q_sent, accepted, answer_written, confirmed, rejected, watcher_cancelled])
    except Exception as e:
        relay_ok = False
        print(f"    Relay test error: {e}")
    results.append(("Two-way relay", relay_ok))

    # 14. Command interface: test command callback, slugify, event
    try:
        from notify.commander import slugify
        from notify.events import command_event, EventType

        # Test slugify
        slug_ok = (
            slugify("build an API") == "build-an-api"
            and slugify("  Hello World!!! ") == "hello-world"
            and slugify("") == "task"
        )

        # Test command event
        cmd_ev = command_event("build-an-api", "build an API", "U123", "slack")
        cmd_ev_ok = (
            cmd_ev.event_type == EventType.COMMAND
            and cmd_ev.task_name == "build-an-api"
            and cmd_ev.metadata["request"] == "build an API"
            and cmd_ev.metadata["user"] == "U123"
            and cmd_ev.metadata["platform"] == "slack"
        )

        # Test command callback in RelayServer
        from notify.relay import RelayServer
        launched_tasks = []

        def mock_handler(request, user, platform):
            slug = slugify(request)
            launched_tasks.append((slug, user, platform))
            return slug

        cmd_config = NotifyConfig(enabled=False)
        cmd_relay = RelayServer(cmd_config, DOBBY_DIR, command_handler=mock_handler)
        # Simulate command callback
        result = cmd_relay._handle_command("build an API", "U123", "discord")
        handler_ok = result == "build-an-api" and len(launched_tasks) == 1

        # Test webhook payload for command event
        from notify.webhook import format_slack_payload, format_discord_payload
        slack_cmd = format_slack_payload(cmd_ev)
        discord_cmd = format_discord_payload(cmd_ev)
        payload_ok = "blocks" in slack_cmd and "embeds" in discord_cmd

        command_ok = all([slug_ok, cmd_ev_ok, handler_ok, payload_ok])
    except Exception as e:
        command_ok = False
        print(f"    Command test error: {e}")
    results.append(("Command interface", command_ok))

    # 15. Bot completion: relay waiter thread fires send_completion via tmux signal
    try:
        from notify.relay import RelayServer
        from notify.adapters.base import BaseAdapter
        from notify.commander import slugify
        import threading

        class CompletionMockAdapter(BaseAdapter):
            def __init__(self, answer_callback):
                super().__init__(answer_callback)
                self._connected = False
                self.completions = []
            @property
            def platform_name(self): return "CompletionMock"
            def connect(self): self._connected = True
            def disconnect(self): self._connected = False
            def is_connected(self): return self._connected
            def send_question(self, task_name, text): return True
            def confirm_answer(self, task_name): pass
            def cancel_question(self, task_name): pass
            def send_completion(self, task_name, cost, output_dir, duration_secs=0):
                self.completions.append((task_name, cost, output_dir, duration_secs))
                return True

        comp_task = "comp-test"
        comp_signal = f"dobby_cmd_{comp_task}_done"

        # Write a mock cost file (uses dobby_cmd_ prefix to match relay)
        cost_path = Path(f"/tmp/dobby_cmd_{comp_task}_output.txt")
        cost_path.write_text(json.dumps({"total_cost_usd": 0.42, "duration_ms": 20270}))

        # Create output dir
        comp_out = DOBBY_DIR / comp_task / "output"
        os.makedirs(comp_out, exist_ok=True)
        (comp_out / "result.md").write_text("mock deliverable")

        # Create a fake tmux session so liveness check passes
        run(f"tmux new-session -d -s dobby-cmd-{comp_task}")

        # Set up relay with mock adapter
        comp_config = NotifyConfig(enabled=False)
        comp_relay = RelayServer(comp_config, DOBBY_DIR)
        comp_mock = CompletionMockAdapter(comp_relay.receive_answer)
        comp_mock.connect()
        comp_relay.adapters = [comp_mock]

        # Start waiter thread with listening event (matches new signature)
        listening = threading.Event()
        waiter = threading.Thread(
            target=comp_relay._wait_for_command_completion,
            args=(comp_task, comp_signal, listening),
            daemon=True,
        )
        waiter.start()
        listening.wait(timeout=5)  # wait until tmux wait-for is active

        # Fire the tmux signal (simulates commander.py after claude exits)
        run(f"tmux wait-for -S {comp_signal}")

        # Wait for waiter to finish
        waiter.join(timeout=10)

        # Check thread actually finished
        if waiter.is_alive():
            bot_comp_ok = False
        else:
            comp_relay.stop()

            # Verify send_completion was called with correct args
            bot_comp_ok = (
                len(comp_mock.completions) == 1
                and comp_mock.completions[0][0] == comp_task
                and abs(comp_mock.completions[0][1] - 0.42) < 0.001
                and comp_task in comp_mock.completions[0][2]
                and comp_mock.completions[0][2].endswith("/output/")
                and comp_mock.completions[0][3] == 20  # 20270ms -> 20s
            )

        # Cleanup
        run(f"tmux kill-session -t dobby-cmd-{comp_task} 2>/dev/null")
        cost_path.unlink(missing_ok=True)
        shutil.rmtree(DOBBY_DIR / comp_task, ignore_errors=True)
    except Exception as e:
        bot_comp_ok = False
        print(f"    Bot completion test error: {e}")
    results.append(("Bot completion", bot_comp_ok))

    # Results
    elapsed = time.time() - total_start
    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    for label, ok in results:
        mark = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        print(f"  {mark} {label}")

    print()
    if passed == total:
        print(f"  \033[32m{passed}/{total} passed\033[0m  {elapsed:.1f}s  \033[32m⚡ Dobby is ready.\033[0m")
    else:
        print(f"  \033[31m{total - passed}/{total} failed\033[0m  {elapsed:.1f}s")

    cleanup()
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
