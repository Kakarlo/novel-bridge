"""Prompt construction for translation requests (Requirements 3.3, 4.1)."""

from __future__ import annotations

from app.engines.base import TranslationRequest

_LANG_NAMES = {"zh": "Chinese", "ja": "Japanese"}

SYSTEM_PROMPT = (
    "You are an expert literary translator of web and light novels. "
    "Translate the given chapter into fluent, natural English prose. "
    "Follow these rules strictly:\n"
    "1. The glossary is authoritative. Always translate the listed source terms "
    "exactly as specified (names, places, skills, terminology).\n"
    "2. Match the tone, register, and narrative style of the provided reference "
    "text so the chapter reads consistently with earlier translated chapters.\n"
    "3. Preserve paragraph breaks and dialogue structure.\n"
    "4. Output ONLY the English translation. Do not add notes, commentary, "
    "pinyin, romaji, or the original text."
)


def build_messages(req: TranslationRequest) -> list[dict[str, str]]:
    """Return chat messages (system + user) for the engine."""
    lang = _LANG_NAMES.get(req.source_lang, req.source_lang)

    parts: list[str] = []

    if req.glossary:
        glossary_lines = "\n".join(
            f"- {e.source_term} => {e.translation}"
            + (f"  ({e.note})" if e.note else "")
            for e in req.glossary
        )
        parts.append(f"## Glossary (authoritative)\n{glossary_lines}")

    if req.reference_context.strip():
        parts.append(
            "## Reference (previously translated, for style/continuity)\n"
            f"{req.reference_context.strip()}"
        )
    else:
        parts.append("## Reference\n(none available)")

    parts.append(f"## Raw chapter to translate (source language: {lang})\n{req.raw_text}")
    parts.append("## Your English translation:")

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]
