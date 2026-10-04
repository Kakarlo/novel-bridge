"""Assemble reference context within a token budget (Requirements 4.1, 4.2, 2.5, 3.5).

Strategy (design decision Q9, revised for task 13):
- The glossary and the raw chapter are always kept in full (handled by the prompt).
- Reference chapters are NO LONGER dumped as raw text (that caused the model to echo the
  reference). Instead we feed the DERIVED context extracted at upload time: a short style
  summary plus candidate glossary terms. These are compact and non-echoable.
- Summaries from the most recent references are included newest-first until the remaining
  budget is exhausted; if even the newest summary doesn't fit it is truncated from the end
  and a truncation flag is returned.

Token counting uses a cheap character-based heuristic for the PoC, kept behind one
function so it can be upgraded to a real tokenizer later.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import GlossaryEntry, ReferenceChapter

# Rough heuristic: CJK text averages well under 4 chars/token, but mixed English
# reference text runs higher. ~3 chars/token is a safe, simple estimate.
_CHARS_PER_TOKEN = 3

_OMISSION_NOTE = "[earlier reference summaries omitted to fit context]\n"


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


def _format_reference(ref: ReferenceChapter) -> str:
    """Render one reference's derived context (summary + candidate terms)."""
    lines = [f"### {ref.title}"]
    if ref.summary:
        lines.append(ref.summary.strip())
    if ref.candidate_terms:
        lines.append("Candidate terms: " + ", ".join(ref.candidate_terms))
    return "\n".join(lines)


def build(
    glossary: list[GlossaryEntry],
    references: list[ReferenceChapter],
    raw_text: str,
    budget_tokens: int,
    *,
    system_prompt_tokens: int = 260,
    reply_headroom_tokens: int = 1024,
) -> BuiltContext:
    """Return the trimmed, DERIVED reference context plus a truncation flag."""
    # Reserve budget for everything that is always included.
    reserved = (
        system_prompt_tokens
        + reply_headroom_tokens
        + _glossary_tokens(glossary)
        + estimate_tokens(raw_text)
    )
    remaining = budget_tokens - reserved

    # Only references that actually have derived context contribute.
    usable = [r for r in references if (r.summary or r.candidate_terms)]

    if remaining <= 0 or not usable:
        # If references exist but none are usable (not yet summarized) or there's no
        # room, report truncation only when we actually dropped available content.
        return BuiltContext(reference_context="", truncated=bool(usable))

    allowed_chars = remaining * _CHARS_PER_TOKEN

    # Newest-first: the most recent chapters are most relevant for continuity.
    blocks: list[str] = []
    used_chars = 0
    truncated = False
    for ref in reversed(usable):
        block = _format_reference(ref)
        sep = 2 if blocks else 0  # "\n\n" between blocks
        if used_chars + len(block) + sep <= allowed_chars:
            blocks.append(block)
            used_chars += len(block) + sep
        else:
            remaining_chars = allowed_chars - used_chars - sep
            if not blocks and remaining_chars > 0:
                # Even the newest summary doesn't fit: keep its head, flag truncation.
                blocks.append(_OMISSION_NOTE + block[:remaining_chars])
            truncated = True
            break

    reference_context = "\n\n".join(blocks)
    return BuiltContext(reference_context=reference_context, truncated=truncated)
