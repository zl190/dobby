# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Level 1: One-way webhook notifications via curl. Zero dependencies."""

import json
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__" or "notify" not in sys.modules:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from notify.config import NotifyConfig, load_config
from notify.events import (
    EventType, NotifyEvent,
    completed_event, question_event, convergence_event, team_done_event,
    command_event,
)


def format_slack_payload(event: NotifyEvent) -> dict:
    """Format a NotifyEvent as a Slack webhook JSON payload (Block Kit)."""
    blocks = []

    emoji_map = {
        EventType.COMPLETED: ":white_check_mark:",
        EventType.QUESTION: ":question:",
        EventType.CONVERGENCE: ":chart_with_upwards_trend:",
        EventType.TEAM_DONE: ":tada:",
        EventType.COMMAND: ":zap:",
    }
    emoji = emoji_map.get(event.event_type, ":robot_face:")
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": f"{emoji} {event.message}"}
    })

    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": f"*Task:* `{event.task_name}`"}]
    })

    meta = event.metadata
    if event.event_type == EventType.COMPLETED:
        fields = [
            f"*Cost:* ${meta.get('cost', 0):.2f}",
            f"*Output:* `{meta.get('output_dir', 'N/A')}`",
        ]
        if meta.get("duration_ms"):
            mins = meta["duration_ms"] // 60000
            secs = (meta["duration_ms"] % 60000) // 1000
            fields.append(f"*Duration:* {mins}m {secs}s")
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(fields)}})

    elif event.event_type == EventType.QUESTION:
        question_text = meta.get("question_text", "(no question text)")
        if len(question_text) > 2900:
            question_text = question_text[:2900] + "..."
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"```{question_text}```"}})
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": "_Answer in your terminal to continue the agent._"}
        ]})

    elif event.event_type == EventType.CONVERGENCE:
        trajectory = meta.get("trajectory", [])
        trajectory_str = " -> ".join(f"{s:.1f}" for s in trajectory) if trajectory else "N/A"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": (
            f"*Iteration:* v{meta.get('iteration', '?')}\n"
            f"*Score:* {meta.get('score', '?')}\n"
            f"*Decision:* {meta.get('decision', '?')}\n"
            f"*Trajectory:* {trajectory_str}"
        )}})

    elif event.event_type == EventType.TEAM_DONE:
        tasks = meta.get("tasks", [])
        task_list = ", ".join(f"`{t}`" for t in tasks)
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": (
            f"*Agents:* {task_list}\n"
            f"*Total cost:* ${meta.get('total_cost', 0):.2f}\n"
            f"*Request:* {meta.get('request', 'N/A')}"
        )}})

    elif event.event_type == EventType.COMMAND:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": (
            f"*Request:* {meta.get('request', 'N/A')}\n"
            f"*User:* {meta.get('user', '?')}\n"
            f"*Platform:* {meta.get('platform', '?')}"
        )}})

    return {"blocks": blocks}


def format_discord_payload(event: NotifyEvent) -> dict:
    """Format a NotifyEvent as a Discord webhook JSON payload (embed)."""
    color_map = {
        EventType.COMPLETED: 0x2ECC71,
        EventType.QUESTION: 0xF39C12,
        EventType.CONVERGENCE: 0x3498DB,
        EventType.TEAM_DONE: 0x9B59B6,
        EventType.COMMAND: 0xE67E22,
    }

    embed = {
        "title": event.message,
        "color": color_map.get(event.event_type, 0x95A5A6),
        "fields": [{"name": "Task", "value": f"`{event.task_name}`", "inline": True}],
    }

    meta = event.metadata
    if event.event_type == EventType.COMPLETED:
        embed["fields"].extend([
            {"name": "Cost", "value": f"${meta.get('cost', 0):.2f}", "inline": True},
            {"name": "Output", "value": f"`{meta.get('output_dir', 'N/A')}`", "inline": False},
        ])

    elif event.event_type == EventType.QUESTION:
        question_text = meta.get("question_text", "(no question text)")
        if len(question_text) > 1900:
            question_text = question_text[:1900] + "..."
        embed["description"] = f"```\n{question_text}\n```"
        embed["footer"] = {"text": "Answer in your terminal to continue the agent."}

    elif event.event_type == EventType.CONVERGENCE:
        trajectory = meta.get("trajectory", [])
        trajectory_str = " -> ".join(f"{s:.1f}" for s in trajectory) if trajectory else "N/A"
        embed["fields"].extend([
            {"name": "Iteration", "value": f"v{meta.get('iteration', '?')}", "inline": True},
            {"name": "Score", "value": str(meta.get("score", "?")), "inline": True},
            {"name": "Decision", "value": meta.get("decision", "?"), "inline": True},
            {"name": "Trajectory", "value": trajectory_str, "inline": False},
        ])

    elif event.event_type == EventType.TEAM_DONE:
        tasks = meta.get("tasks", [])
        embed["fields"].extend([
            {"name": "Agents", "value": ", ".join(f"`{t}`" for t in tasks), "inline": False},
            {"name": "Total Cost", "value": f"${meta.get('total_cost', 0):.2f}", "inline": True},
            {"name": "Request", "value": meta.get("request", "N/A"), "inline": False},
        ])

    elif event.event_type == EventType.COMMAND:
        embed["fields"].extend([
            {"name": "Request", "value": meta.get("request", "N/A"), "inline": False},
            {"name": "User", "value": meta.get("user", "?"), "inline": True},
            {"name": "Platform", "value": meta.get("platform", "?"), "inline": True},
        ])

    return {"embeds": [embed]}


def send_webhook(url: str, payload: dict, timeout: int = 5) -> bool:
    """Send a webhook payload via curl. Returns True on success."""
    payload_json = json.dumps(payload)
    try:
        result = subprocess.run(
            [
                "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                "-X", "POST",
                "-H", "Content-Type: application/json",
                "-d", payload_json,
                "--max-time", str(timeout),
                url,
            ],
            capture_output=True, text=True, timeout=timeout + 2,
        )
        status_code = result.stdout.strip()
        return status_code.startswith("2")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
        return False


def dispatch(event: NotifyEvent, config: NotifyConfig | None = None) -> dict[str, bool]:
    """Dispatch a notification event to all configured webhooks."""
    if config is None:
        config = load_config()

    if not config.should_notify(event.event_type.value):
        return {"slack": False, "discord": False}

    results = {"slack": False, "discord": False}

    if config.slack.has_webhook:
        payload = format_slack_payload(event)
        results["slack"] = send_webhook(config.slack.webhook_url, payload, config.timeout)

    if config.discord.has_webhook:
        payload = format_discord_payload(event)
        results["discord"] = send_webhook(config.discord.webhook_url, payload, config.timeout)

    return results


def main():
    """CLI: webhook.py <event_type> --task NAME [--cost X] [--message MSG] ..."""
    import argparse

    parser = argparse.ArgumentParser(description="Dobby webhook notifier")
    parser.add_argument("event_type", choices=["completed", "question", "convergence", "team_done", "command"])
    parser.add_argument("--task", required=True)
    parser.add_argument("--cost", type=float, default=0.0)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--duration-ms", type=int, default=0)
    parser.add_argument("--message", default="")
    parser.add_argument("--iteration", type=int, default=0)
    parser.add_argument("--score", type=float, default=0.0)
    parser.add_argument("--decision", default="")
    parser.add_argument("--tasks", default="")
    parser.add_argument("--total-cost", type=float, default=0.0)
    parser.add_argument("--request", default="")
    parser.add_argument("--trajectory", default="")  # comma-separated scores
    parser.add_argument("--user", default="unknown")
    parser.add_argument("--platform", default="cli")
    args = parser.parse_args()

    event_builders = {
        "completed": lambda: completed_event(args.task, args.cost, args.output_dir, args.duration_ms),
        "question": lambda: question_event(args.task, args.message),
        "convergence": lambda: convergence_event(
            args.task, args.iteration, args.score, args.decision,
            [float(s) for s in args.trajectory.split(",") if s.strip()] if args.trajectory else None
        ),
        "team_done": lambda: team_done_event(
            [t.strip() for t in args.tasks.split(",") if t.strip()],
            args.total_cost, args.request
        ),
        "command": lambda: command_event(args.task, args.request, args.user, args.platform),
    }

    event = event_builders[args.event_type]()
    results = dispatch(event)

    # Exit 0 always — webhook failure must not block the caller
    sent_to = [k for k, v in results.items() if v]
    if sent_to:
        print(f"Notified: {', '.join(sent_to)}")
    sys.exit(0)


if __name__ == "__main__":
    main()
