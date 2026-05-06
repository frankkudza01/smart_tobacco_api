"""
Base workflow handler. Each conversational workflow inherits from this
and defines state transitions as methods named `handle_<STATE>`.
"""
import abc
import logging
from typing import NamedTuple

from apps.whatsapp.models import WhatsAppConversation

logger = logging.getLogger(__name__)


class Reply(NamedTuple):
    text: str
    end_conversation: bool = False


class BaseWorkflow(abc.ABC):
    """
    State-machine driven workflow handler.
    Subclasses define `handle_<state_name>(conv, body, contact)` methods.
    The router looks up the current state and dispatches accordingly.
    """

    @abc.abstractmethod
    def get_name(self) -> str:
        ...

    def process(self, conv: WhatsAppConversation, body: str) -> Reply:
        state = conv.current_state.upper()
        handler_name = f"handle_{state.lower()}"
        handler = getattr(self, handler_name, None)

        if handler is None:
            logger.warning(
                "Workflow %s has no handler for state %s", self.get_name(), state,
            )
            return Reply("Something went wrong. Type CANCEL to start over.", end_conversation=False)

        return handler(conv, body, conv.contact)

    @staticmethod
    def _menu_options(options: list[str]) -> str:
        lines = []
        for i, opt in enumerate(options, 1):
            lines.append(f"{i}. {opt}")
        return "\n".join(lines)

    @staticmethod
    def _parse_choice(body: str, max_choice: int) -> int | None:
        body = body.strip()
        if body.isdigit():
            val = int(body)
            if 1 <= val <= max_choice:
                return val
        return None
