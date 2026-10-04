"""Assemble reference context within a token budget (Requirements 4.1, 4.2, 2.5).

Strategy (design decision Q9):
- The glossary and the raw chapter are always kept in full (handled by the prompt).
- The remaining budget is filled with the TAIL of the most recently added reference
  chapter (most relevant for narrative continuity).
- If the reference exceeds the remaining budget, it is truncated from the start and an
  omission note is prepended; a truncation flag is returned.

Token counting uses a cheap character-based heuristic for the PoC, kept behind one
function so it can be upgraded to a real tokenizer later.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import GlossaryEntry, ReferenceChapter

# Rough heuristic: CJK text averages well under 4 chars/token, but mixed English
# reference text runs higher. ~3 chars/token is a safe, simple estimate.
_CHARS_PER_TOKEN = 3

_OMISSION_NOTE = "[earlier reference omitted to fit context]\n"


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


@dataclass
class BuiltContext:
    reference_context: str
    truncated: bool


def _glossary_tokens(glossary: list[GlossaryEntry]) -> int:
    total = 0
    for e in glossary:
        total += estimate_tokens(e.source_term) + estimate_tokens(e.translation)
        if e.note:
            total += estimate_tokens(e.note)
        total += 4  # formatting overhead per line
    return total


def build(
    glossary: list[GlossaryEntry],
    references: list[ReferenceChapter],
    raw_text: str,
    budget_tokens: int,
    *,
    system_prompt_tokens: int = 220,
    reply_headroom_tokens: int = 1024,
) -> BuiltContext:
    """Return the trimmed reference context plus a truncation flag."""
    # Reserve budget for everything that is always included.
    reserved = (
        system_prompt_tokens
        + reply_headroom_tokens
        + _glossary_tokens(glossary)
        + estimate_tokens(raw_text)
    )
    remaining = budget_tokens - reserved

    if remaining <= 0 or not references:
        return BuiltContext(reference_context="", truncated=bool(references))

    # Most recently added reference is the most relevant for continuity.
    latest = references[-1]
    text = latest.content

    allowed_chars = remaining * _CHARS_PER_TOKEN
    if len(text) <= allowed_chars:
        return BuiltContext(reference_context=text, truncated=False)

    # Keep the TAIL (end of the chapter is closest to where the raw continues).
    tail = text[-allowed_chars:]
    return BuiltContext(reference_context=_OMISSION_NOTE + tail, truncated=True)
