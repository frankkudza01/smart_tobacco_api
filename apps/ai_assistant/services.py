import logging

from apps.ai_intelligence.assistant_service import run_hardened_assistant_chat

logger = logging.getLogger(__name__)


def process_ai_query(*, user, prompt: str, context: dict | None = None) -> dict:
    """
    Backwards-compatible entry for WhatsApp / Celery. Delegates to hardened assistant.
    `context` is ignored for security (untrusted); use scoped tools only.
    """
    return run_hardened_assistant_chat(user=user, prompt=prompt, conversation_id=None)
