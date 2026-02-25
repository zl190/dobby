"""Abstract base class for messaging platform adapters."""

from abc import ABC, abstractmethod
from typing import Callable, Optional

# Type alias: (task_name, answer_text) -> accepted
AnswerCallback = Callable[[str, str], bool]
# Type alias: (request, user_id, platform) -> task_name or None
CommandCallback = Callable[[str, str, str], Optional[str]]


class BaseAdapter(ABC):
    """Interface that all messaging platform adapters must implement.

    Lifecycle:
        adapter = SlackAdapter(config, answer_callback)
        adapter.connect()       # establish connection (WebSocket, etc.)
        adapter.send_question(task_name, question_text)
        # ... user replies in platform, adapter calls answer_callback ...
        adapter.disconnect()    # clean shutdown

    Threading: Adapters run their event loops in background threads.
    The answer_callback is called from the adapter's thread — the RelayServer
    handles thread safety internally.
    """

    def __init__(self, answer_callback: AnswerCallback, command_callback: Optional[CommandCallback] = None):
        self._answer_callback = answer_callback
        self._command_callback = command_callback

    @abstractmethod
    def connect(self) -> None:
        """Establish connection. Non-blocking — start event loop in a background thread."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Cleanly disconnect. Idempotent."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the adapter has an active connection."""
        ...

    @abstractmethod
    def send_question(self, task_name: str, question_text: str) -> bool:
        """Send a HITL question to the messaging platform. Returns True on success."""
        ...

    @abstractmethod
    def confirm_answer(self, task_name: str) -> None:
        """Notify the platform that a question has been answered."""
        ...

    @abstractmethod
    def cancel_question(self, task_name: str) -> None:
        """Cancel a pending question (answered elsewhere or timed out)."""
        ...

    def send_completion(self, task_name: str, cost: float, output_dir: str, duration_secs: int = 0) -> bool:
        """Post a completion notification for a finished command-launched task.

        Returns True on success. Default does nothing — override in adapters.
        """
        return False

    def send_status(self, task_name: str, status_text: str) -> bool:
        """Send a status update for a launched command. Returns True on success.

        Default implementation does nothing. Override in adapters that support commands.
        """
        return False

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Human-readable platform name, e.g. 'Slack' or 'Discord'."""
        ...
