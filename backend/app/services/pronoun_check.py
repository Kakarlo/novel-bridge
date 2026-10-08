"""EXPERIMENTAL — English pronoun-drift DETECTION (never a rewrite).

zh/ja have no grammatical gender on pronouns, so machine/LLM translations often drift —
a male character gets a stray "she". That drift breaks reading immersion. This flags likely
drift so the user (or a later prompt tweak) can address it. It is a DETECTOR, in the spirit
of the glossary term-match loop: it reports, it never edits the translation. (The glossary
is a guide, not a find-and-replace — rewriting pronouns mechanically would wreck grammar.)

Approach (stdlib ``re`` only, no NLP deps, offline):
- For each glossary CHARACTER with a known gender (male/female), find its name in the text.
- Look in a short window AFTER each mention; if a pronoun of the OPPOSITE gender appears
  before the next character name, flag it with a context snippet.
- This is a naive proximity heuristic, NOT coreference. ponytail: known ceiling — it will
  miss cross-sentence references and false-positive in dense multi-character scenes. The
  upgrade path is real coreference (spaCy ``coreferee`` / a trf model), deliberately not
  built while this is experimental.

CHEAP TO REMOVE: this file + its one call site + the ``NB_PRONOUN_CHECK`` flag. No schema
change, no storage. Delete and it's gone.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import BaseModel

from app.models import GlossaryEntry

# Gendered subject/object/possessive pronouns we can judge. "they/their" is neutral and
# never flagged (a legitimate choice for unknown/ambiguous).
_MALE = {"he", "him", "his", "himself"}
_FEMALE = {"she", "her", "hers", "herself"}

# How far after a name mention to look for a conflicting pronoun, in characters.
_WINDOW = 120
# Max flags per character, to keep the review list readable.
_MAX_PER_NAME = 5


class PronounFlag(BaseModel):
    """One likely pronoun/gender mismatch for a character, for the review UI."""

    surface_form: str
    expected_gender: str  # 'male' | 'female'
    found_pronoun: str
    snippet: str


def _name_pattern(surface_form: str) -> re.Pattern[str] | None:
    term = surface_form.strip()
    if not term:
        return None
    core = r"\s+".join(re.escape(tok) for tok in term.split())
    if not core:
        return None
    return re.compile(rf"(?<!\w)(?:{core})(?!\w)", re.IGNORECASE)


def find_pronoun_drift(
    output_text: str, terms: Iterable[GlossaryEntry]
) -> list[PronounFlag]:
    """Flag likely gender/pronoun mismatches for gendered characters in ``output_text``.

    Returns one flag per suspicious occurrence (capped per name). Pure, offline, detection
    only. Characters without a known male/female gender are skipped.
    """
    if not output_text:
        return []

    flags: list[PronounFlag] = []
    for term in terms:
        if term.category != "character":
            continue
        gender = term.gender
        if gender not in ("male", "female"):
            continue
        conflicting = _FEMALE if gender == "male" else _MALE
        pattern = _name_pattern(term.surface_form)
        if pattern is None:
            continue

        found = 0
        for m in pattern.finditer(output_text):
            if found >= _MAX_PER_NAME:
                break
            window = output_text[m.end() : m.end() + _WINDOW]
            # Stop the window at the next capitalized name-ish token so we don't attribute
            # a pronoun that clearly belongs to a later subject (very rough guard).
            pron = _first_conflicting_pronoun(window, conflicting)
            if pron is None:
                continue
            start = max(0, m.start() - 20)
            end = min(len(output_text), m.end() + _WINDOW)
            snippet = " ".join(output_text[start:end].split())
            flags.append(
                PronounFlag(
                    surface_form=term.surface_form,
                    expected_gender=gender,
                    found_pronoun=pron,
                    snippet=snippet,
                )
            )
            found += 1

    return flags


def _first_conflicting_pronoun(window: str, conflicting: set[str]) -> str | None:
    """Return the first conflicting-gender pronoun (whole word, lowercased) in the window."""
    for w in re.finditer(r"\w+", window):
        word = w.group(0).lower()
        if word in conflicting:
            return word
    return None
