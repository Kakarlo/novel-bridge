"""Rule-based proper-noun detection for reference chapters (field-fix #2).

References are English, so proper nouns (character names, places, sects, titles) are
reliably *capitalized*. A deterministic pass over the text catches most of them without
asking the model — which is the point: don't make a weak local LLM do what simple rules
do reliably. The AI extraction still runs; its semantic picks and these structural picks
reinforce each other (surfaced separately so the user can judge which pass found what).

Approach (stdlib ``re`` only, offline):
- Find runs of Capitalized Words (e.g. "Li Changshou", "Azure Cloud Sect"), allowing short
  connective words inside a run ("of", "the") so "Sect of the Azure Cloud" stays whole.
- Drop a run that sits at the start of a sentence AND is a single word AND looks like an
  ordinary sentence-initial capital (a stopword, or seen lowercased elsewhere) — this is the
  main false-positive source in prose.
- Drop pure stopwords and single-letter runs.
- Rank by frequency; a form seen 2+ times is almost certainly a proper noun.

Limitations (acceptable for v1): won't catch lowercase common-noun jargon ("cultivation");
the AI pass covers those. Fuzzy/alias handling is out of scope.
"""

from __future__ import annotations

import re
from collections import Counter

# Words that are capitalized at sentence start / in titles but are rarely proper nouns on
# their own. Kept small and generic; genre terms are intentionally NOT excluded.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "so", "yet", "for", "nor",
    "of", "to", "in", "on", "at", "by", "with", "from", "as", "into", "onto", "upon",
    "he", "she", "it", "they", "we", "you", "i", "his", "her", "their", "our", "your",
    "him", "them", "us", "me", "my", "its", "this", "that", "these", "those",
    "there", "here", "when", "where", "why", "how", "what", "who", "whom", "which",
    "is", "was", "were", "are", "be", "been", "am", "do", "did", "does", "done",
    "have", "has", "had", "will", "would", "shall", "should", "can", "could", "may",
    "might", "must", "not", "no", "yes", "now", "once", "after", "before", "while",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "chapter", "part", "volume", "prologue", "epilogue",
}

# Short lowercase connectives allowed to appear *inside* a multi-word proper-noun run.
_CONNECTIVES = {"of", "the", "and", "de", "van", "von", "da", "di"}

# A capitalized token: starts uppercase, may contain more letters/apostrophes/hyphens.
_CAP_TOKEN = r"[A-Z][\w'’-]*"
# A run: a capitalized token, then zero+ (connective | capitalized token).
_RUN_RE = re.compile(rf"{_CAP_TOKEN}(?:\s+(?:{'|'.join(_CONNECTIVES)}|{_CAP_TOKEN}))*")

# Sentence boundary just before a position: start of text, or ., !, ?, newline, quote, colon.
_SENTENCE_START_RE = re.compile(r"(?:^|[.!?;:\n\r\"“”‘’()\[\]])\s*$")


def _is_sentence_start(text: str, pos: int) -> bool:
    """True if ``pos`` begins a new sentence (so a lone capital there is suspect)."""
    return bool(_SENTENCE_START_RE.search(text[:pos]))


def _trim_run(run: str) -> str:
    """Strip leading/trailing connectives from a run (e.g. 'The Azure' -> 'Azure')."""
    tokens = run.split()
    while tokens and tokens[0].lower() in _CONNECTIVES:
        tokens.pop(0)
    while tokens and tokens[-1].lower() in _CONNECTIVES:
        tokens.pop()
    return " ".join(tokens)


def extract_proper_nouns(text: str, *, limit: int = 30) -> list[str]:
    """Return likely proper nouns in ``text``, most frequent first.

    Deterministic and offline. Multi-word names are kept whole. A single capitalized word
    is only kept if it appears somewhere that is NOT a sentence start, or it recurs — this
    filters ordinary sentence-initial capitals. Returns the original surface form (first
    casing seen), de-duplicated case-insensitively.
    """
    if not text or not text.strip():
        return []

    # Track, per normalized form: display form, total count, and whether we ever saw it
    # in a non-sentence-start position (strong proper-noun signal).
    counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    seen_midsentence: set[str] = set()
    # Also track which single lowercase words appear, to catch "Dawn" (sentence start) vs
    # a word that also occurs lowercased ("dawn") — the latter is likely not a name.
    lowercased_words = {m.group(0).lower() for m in re.finditer(r"\b[a-z][\w'’-]*\b", text)}

    for m in _RUN_RE.finditer(text):
        raw_run = _trim_run(m.group(0))
        if not raw_run:
            continue
        tokens = raw_run.split()
        key = raw_run.casefold()

        # Reject pure stopwords / single letters.
        content_tokens = [t for t in tokens if t.lower() not in _CONNECTIVES]
        if not content_tokens:
            continue
        if all(t.lower() in _STOPWORDS for t in content_tokens):
            continue
        if len(raw_run) <= 1:
            continue

        counts[key] += 1
        display.setdefault(key, raw_run)
        if not _is_sentence_start(text, m.start()):
            seen_midsentence.add(key)

    results: list[tuple[str, int]] = []
    for key, count in counts.items():
        tokens = display[key].split()
        is_multiword = len(tokens) > 1
        single = tokens[0] if not is_multiword else ""

        # Keep if: multi-word (strong), OR seen mid-sentence, OR recurs 2+ times.
        keep = is_multiword or key in seen_midsentence or count >= 2
        # Single-word vetoes (ordinary words merely capitalized at a sentence start):
        if not is_multiword:
            if single.lower() in _STOPWORDS:
                keep = False
            # If the same word also appears lowercased and we NEVER saw it mid-sentence,
            # it's almost certainly a common word at a sentence start — veto even if it
            # recurs (frequency alone shouldn't rescue "Dawn"/"dawn").
            if single.lower() in lowercased_words and key not in seen_midsentence:
                keep = False
        if keep:
            results.append((display[key], count))

    # Frequency desc, then alphabetical for stable output.
    results.sort(key=lambda x: (-x[1], x[0].casefold()))
    return [form for form, _ in results[:limit]]
