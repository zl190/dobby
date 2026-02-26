"""Notification event definitions."""

from dataclasses import dataclass, field
from enum import Enum


class EventType(Enum):
    COMPLETED = "completed"
    QUESTION = "question"
    CONVERGENCE = "convergence"
    TEAM_DONE = "team_done"
    COMMAND = "command"
    DECISION = "decision"
    CHECKPOINT = "checkpoint"


@dataclass
class NotifyEvent:
    event_type: EventType
    task_name: str
    message: str
    metadata: dict = field(default_factory=dict)


def completed_event(task_name: str, cost: float, output_dir: str, duration_ms: int = 0) -> NotifyEvent:
    return NotifyEvent(
        event_type=EventType.COMPLETED,
        task_name=task_name,
        message=f"Dobby has finished: {task_name} (${cost:.2f})",
        metadata={"cost": cost, "output_dir": output_dir, "duration_ms": duration_ms},
    )


def question_event(task_name: str, question_text: str) -> NotifyEvent:
    return NotifyEvent(
        event_type=EventType.QUESTION,
        task_name=task_name,
        message=f"Dobby needs help with: {task_name}",
        metadata={"question_text": question_text},
    )


def convergence_event(
    task_name: str, iteration: int, score: float,
    decision: str, trajectory: list[float] | None = None
) -> NotifyEvent:
    return NotifyEvent(
        event_type=EventType.CONVERGENCE,
        task_name=task_name,
        message=f"Dobby convergence: {task_name} v{iteration} scored {score:.1f} [{decision}]",
        metadata={
            "iteration": iteration, "score": score,
            "decision": decision, "trajectory": trajectory or [],
        },
    )


def team_done_event(tasks: list[str], total_cost: float, request: str) -> NotifyEvent:
    return NotifyEvent(
        event_type=EventType.TEAM_DONE,
        task_name="team",
        message=f"Dobby team finished ({len(tasks)} agents, ${total_cost:.2f})",
        metadata={"tasks": tasks, "total_cost": total_cost, "request": request},
    )


def command_event(task_name: str, request: str, user: str, platform: str) -> NotifyEvent:
    return NotifyEvent(
        event_type=EventType.COMMAND,
        task_name=task_name,
        message=f"Dobby command from {platform}: {request}",
        metadata={"request": request, "user": user, "platform": platform},
    )


def decision_event(task_name: str, decision: str, rationale: str) -> NotifyEvent:
    return NotifyEvent(
        event_type=EventType.DECISION,
        task_name=task_name,
        message=f"Dobby decided: {decision}",
        metadata={"decision": decision, "rationale": rationale},
    )


def checkpoint_event(task_name: str, summary: str, iteration: int = 0) -> NotifyEvent:
    return NotifyEvent(
        event_type=EventType.CHECKPOINT,
        task_name=task_name,
        message=f"Dobby checkpoint: {task_name} (phase {iteration})",
        metadata={"summary": summary, "iteration": iteration},
    )
