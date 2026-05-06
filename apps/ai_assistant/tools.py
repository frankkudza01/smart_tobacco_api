"""
Legacy module: unsafe tools that queried by raw IDs without RBAC have been removed.

All assistant capabilities live in `apps.ai_intelligence.assistant_tools` and are invoked
only through `run_hardened_assistant_chat` with per-request user binding.
"""

TOOL_REGISTRY: dict[str, object] = {}
