"""Debug helpers gated by the NB_DEBUG_PROMPTS setting.

Keeps the prompt-inspection prints out of stdout unless explicitly enabled, so a
hosted/production run stays quiet and never risks dumping chapter content or system prompts
into logs. Enable with NB_DEBUG_PROMPTS=true.
"""

from __future__ import annotations

from app.config import get_settings


def debug_prompts_enabled() -> bool:
    return bool(get_settings().nb_debug_prompts)


def dump_messages(messages: list[dict], label: str = "") -> None:
    """Print chat messages (role + content) when prompt debugging is on; no-op otherwise."""
    if not debug_prompts_enabled():
        return
    if label:
        print(f"\n========== {label} ==========")
    for i, msg in enumerate(messages):
        print(f"\n--- MESSAGE {i} ({msg.get('role', '?')}) ---")
        print(msg.get("content", ""))
    if label:
        print("=" * (22 + len(label)))
