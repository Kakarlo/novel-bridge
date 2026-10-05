"""Detect glossary-term occurrences in a translation's output (task 14.2).

This powers the in-context review loop: after a translation completes (and when a saved
translation is reopened), we scan the output for each glossary term's English
``surface_form`` and surface the matches so the user can approve/reject them.

Design (settled decisions):
- **Detection only.** This never rewrites the translation. The glossary is a *guide*; the
  model stays free to prioritize flow. We only report where a term appears.
- **Exact whole-word, case-insensitive.** Pure stdlib ``re``, no NLP deps. Fuzzy/alias
  matching is a flagged follow-up, not v1.
- Multi-word surface forms (e.g. "Fang Yuan") are matched as a whole phrase; internal
  whitespace in the term is treated flexibly (one-or-more whitespace) so a newline between
  the words still matches.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.models import GlossaryEntry, TermMatch

# How much context to show around each occurrence, and how many snippets to keep per term.
_SNIPPET_RADIUS = 40
_MAX_SNIPPETS = 3


def _build_pattern(surface_form: str) -> re.Pattern[str] | None:
    """Compile a whole-word, case-insensitive pattern for one surface form.

    Returns ``None`` for a surface form that has no word characters to match on (so an
    all-punctuation/whitespace term never produces spurious matches).
    """
    term = surface_form.strip()
    if not term:
        return None

    # Escape regex-special chars, then let any run of whitespace in the term match any run
    # of whitespace in the text (handles a line break inside a multi-word name).
    tokens = [re.escape(tok) for tok in term.split()]
    if not tokens:
        return None
    core = r"\s+".join(tokens)

    # Whole-word boundaries via lookarounds so adjacency to word chars doesn't match
    # (e.g. "Lin" must not match inside "Linda"). Lookarounds work for multi-word phrases
    # where a leading/trailing \b alone would be awkward.
    pattern = rf"(?<!\w)(?:{core})(?!\w)"
    return re.compile(pattern, re.IGNORECASE)


def _snippets(text: str, pattern: re.Pattern[str]) -> tuple[int, list[str]]:
    """Return (total occurrence count, up to _MAX_SNIPPETS context windows)."""
    count = 0
    snippets: list[str] = []
    for m in pattern.finditer(text):
        count += 1
        if len(snippets) < _MAX_SNIPPETS:
            start = max(0, m.start() - _SNIPPET_RADIUS)
            end = min(len(text), m.end() + _SNIPPET_RADIUS)
            prefix = "…" if start > 0 else ""
            suffix = "…" if end < len(text) else ""
            snippet = prefix + text[start:end].strip() + suffix
            snippets.append(" ".join(snippet.split()))  # collapse internal whitespace
    return count, snippets


def find_occurrences(
    output_text: str, terms: Iterable[GlossaryEntry]
) -> list[TermMatch]:
    """Find whole-word, case-insensitive occurrences of each term in ``output_text``.

    Returns one ``TermMatch`` per term that appears at least once, in descending order of
    occurrence count (ties keep input order), so the review UI can lead with the most
    prominent names. Terms that never appear are omitted. Pure and offline.
    """
    if not output_text:
        return []

    matches: list[TermMatch] = []
    seen_surface: set[str] = set()
    for term in terms:
        key = term.surface_form.strip().casefold()
        if not key or key in seen_surface:
            # Skip blanks and duplicate surface forms (unique constraint should prevent
            # the latter, but guard anyway so a stray dupe can't double-count).
            continue
        seen_surface.add(key)

        pattern = _build_pattern(term.surface_form)
        if pattern is None:
            continue
        count, snippets = _snippets(output_text, pattern)
        if count == 0:
            continue
        matches.append(
            TermMatch(
                term_id=term.id,
                surface_form=term.surface_form,
                status=term.status,
                category=term.category,
                count=count,
                snippets=snippets,
            )
        )

    matches.sort(key=lambda m: m.count, reverse=True)
    return matches
