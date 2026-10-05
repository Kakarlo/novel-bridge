"""Deterministic chapter-number extraction from a reference title.

Why: reference ordering (context_builder) keys continuity off chapter order, but today it
only has upload time (`created_at`) as a proxy — wrong if chapters are uploaded out of order.
Pulling an explicit number from the title lets ordering be correct regardless of upload order.

Offline, deterministic, no LLM. Returns the chapter number or None; a None means "couldn't
tell", and the caller falls back to upload order (and the UI can ask the user to set one).

Handled formats (the common web-novel cases):
    "Chapter 12: Title"              -> 12
    "Chapter 1035 - 469: ..."        -> 1035   (first number after "Chapter"; the 469 is a
                                                 secondary source index and is ignored)
    "Ch. 7 - Title" / "Ch 7"         -> 7
    "Chapter 12.5 Title"             -> 12     (decimal/interlude: take the integer part)
    "12. Title" / "12 - Title"       -> 12     (bare leading number, no "Chapter" keyword)

NOT handled on purpose (returns None, left to the user / a future pass):
    "Volume 2, Chapter 5"            -> None   see VOLUME TODO below
    "Vol. 2 Ch. 5"                   -> None
A volume+chapter title needs a COMPOSITE ordering key (volume-major, chapter-minor), not a
single int, so the current `chapter_number: int | None` can't represent it correctly. Rather
than return a misleading bare 5 (which would sort a vol-2 chapter among vol-1 chapters), we
return None so it falls back to upload order and the UI can prompt for a manual value.

ponytail: TODO (volumes) — when volume support is wanted, model ordering as a (volume,
chapter) tuple or a composite sort key, and extend this parser to populate it. Deliberately
out of scope now: no volume data in the model yet, and single-arc series (the common case)
don't need it.
"""

from __future__ import annotations

import re

# "chapter"/"ch"/"ch." + optional separator + the first integer. Case-insensitive. We take
# the FIRST integer run after the keyword, so "Chapter 1035 - 469" yields 1035. A following
# ".5" (interlude) is matched but discarded — we keep the integer part.
_CHAPTER_KEYWORD_RE = re.compile(r"\bch(?:apter|\.?)\s*[-:.]?\s*(\d+)", re.IGNORECASE)

# Fallback: a bare leading number ("12. Title", "12 - Title", "12 Title"). Anchored at the
# start (after optional whitespace) so a number appearing mid-title isn't mistaken for one.
_LEADING_NUMBER_RE = re.compile(r"^\s*(\d+)\b")

# Volume markers — if present we bail to None (see module docstring: can't represent a
# (volume, chapter) order as a single int, so don't guess).
_VOLUME_RE = re.compile(r"\bvol(?:ume|\.?)\s*\d+", re.IGNORECASE)


def parse_chapter_number(title: str) -> int | None:
    """Return the chapter number parsed from ``title``, or None if indeterminate.

    Deterministic and offline. A volume-prefixed title returns None by design (see module
    docstring) because a single int can't order volume+chapter correctly.
    """
    if not title:
        return None
    if _VOLUME_RE.search(title):
        return None
    m = _CHAPTER_KEYWORD_RE.search(title)
    if m is None:
        m = _LEADING_NUMBER_RE.search(title)
    if m is None:
        return None
    try:
        return int(m.group(1))
    except (ValueError, IndexError):
        return None
