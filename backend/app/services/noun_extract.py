"""Proper-noun detection for reference chapters (field-fix #2, Issue 1: spaCy NER).

References are English, so character/place/sect names are what the "Detected names" pass is
after. The job is to find them WITHOUT asking the weak local LLM (that's the point of a
deterministic pre-pass). The AI extraction still runs; its semantic picks and these
structural picks reinforce each other (surfaced separately so the user can judge each pass).

Primary approach: **spaCy NER** (`en_core_web_sm`). We use named-entity *spans*
(PERSON/ORG/GPE/FAC/LOC/NORP/EVENT/WORK_OF_ART/LAW), NOT raw POS ``PROPN`` tags — PROPN
misclassifies ordinary sentence-openers and spaCy's own docs call PROPN-vs-NOUN the tagger's
weakest spot. NER yields clean multiword spans ("Li Changshou") and naturally drops
sentence-initial capitals and contractions ("I'm", "Although", "Unfortunately") — the exact
false positives the old regex pass leaked.

Caveat (acceptable, by design): the model is trained on web/news, so it nails character/place
names but misses lowercase xianxia jargon ("qi refinement", "primordial world"). That's fine —
the LLM extraction pass covers concept terms; see ``build_extraction_messages``.

Fallback: if spaCy or the model can't be imported/loaded, we fall back to the previous
deterministic regex pass (``_regex_proper_nouns``) so the app still runs offline without the
model (a warning is logged once). Same public signature either way.

ponytail: the regex fallback is a known-weaker heuristic (can't judge grammatical role) kept
only for the no-model case; the NER path is the real one. Upgrade path if the fallback ever
needs to be the primary again: a larger spaCy model or a trf pipeline.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

logger = logging.getLogger(__name__)

# Entity labels that denote a name we want to surface. Kept DELIBERATELY NARROW: character,
# place, org, and facility names cluster in these five. We tried the broader set
# (NORP/WORK_OF_ART/LAW/EVENT) on a real xianxia chapter and it dragged in noise —
# interjections ("Clang") as NORP, pill/skill phrases as WORK_OF_ART — so those are excluded.
# ponytail: narrower labels = fewer false positives, which is the whole point of the pass.
_NAME_LABELS = {"PERSON", "ORG", "GPE", "FAC", "LOC"}

# Leading/trailing determiners/connectives to strip from a span ("The Azure Peak" ->
# "Azure Peak"). Lowercase connectives may still appear *inside* a name ("Court of Dao").
_LEADING_DROP = {"the", "a", "an", "of", "and"}

# Single-token interjections / onomatopoeia that NER capitalizes at sentence start and
# mislabels as names ("Clang!", "Hmph", "Yo"). Vetoed when they stand alone.
_INTERJECTIONS = {
    "clang", "yo", "hmm", "hmmm", "hmph", "hmpf", "ah", "oh", "eh", "hey", "ha", "haha",
    "huh", "wow", "ugh", "oof", "psh", "tsk", "heh", "hng", "mm", "mmm", "er", "um", "uh",
}

# Possessive / contraction tail on a token: 's, ', 'll, 'm, 're, 've, 'd (and curly ').
_APOS_TAIL_RE = re.compile(r"['’](?:s|ll|m|re|ve|d)?$", re.IGNORECASE)

# Punctuation that must NOT appear inside a clean name span. If a cleaned span still
# contains any of these, it straddled a quote/sentence boundary (e.g. 'No… Ah!" Li
# Changshou') and is rejected rather than surfaced as a garbage "name".
_BAD_IN_NAME_RE = re.compile(r"[\"“”‘’…!?,.:;()\[\]{}]")

# Module-level singleton. ``False`` means "tried and failed, use fallback"; ``None`` means
# "not loaded yet". We keep the model loaded for the process lifetime (first load ~0.5s).
_nlp: object | None = None
_nlp_failed = False


def _get_nlp():
    """Load the spaCy NER pipeline once, or return ``None`` if unavailable.

    Keeps only the NER-relevant components (``exclude`` the tagger/parser/lemmatizer/etc.) so
    load is fast and memory small — we only read ``doc.ents``.
    """
    global _nlp, _nlp_failed
    if _nlp is not None:
        return _nlp
    if _nlp_failed:
        return None
    try:
        import spacy

        _nlp = spacy.load(
            "en_core_web_sm",
            exclude=["tagger", "parser", "lemmatizer", "attribute_ruler", "tok2vec"],
        )
        return _nlp
    except Exception as exc:  # ImportError or model-not-found (OSError) or load error
        _nlp_failed = True
        logger.warning(
            "spaCy NER unavailable (%s); falling back to the regex proper-noun pass. "
            "Install the model with: python -m spacy download en_core_web_sm",
            exc,
        )
        return None


def _clean_span(span_text: str) -> str:
    """Normalize an entity span into a candidate name.

    - Collapse internal whitespace/newlines (spans can straddle line breaks).
    - Strip surrounding quote marks ('"Big Sister' -> 'Big Sister').
    - Strip a possessive/contraction tail from the LAST token ("Changshou's" -> "Changshou").
    - Drop leading/trailing determiners/connectives ("The Azure Peak" -> "Azure Peak").
    """
    # Collapse whitespace/newlines, then strip wrapping quotes from the whole span.
    text = " ".join(span_text.split()).strip("\"“”‘’")
    tokens = text.split()
    if not tokens:
        return ""
    tokens[-1] = _APOS_TAIL_RE.sub("", tokens[-1])
    tokens = [t for t in tokens if t]
    while tokens and tokens[0].lower() in _LEADING_DROP:
        tokens.pop(0)
    while tokens and tokens[-1].lower() in _LEADING_DROP:
        tokens.pop()
    return " ".join(tokens)


def _is_name_like(name: str) -> bool:
    """True if a cleaned span looks like a real name worth surfacing.

    Rejects: empties/single chars, lowercase-leading spans, spans that still carry
    sentence punctuation (straddled a quote/boundary), spans with a non-capitalized token
    (a trailing verb like 'Li Changshou frowned'), and lone interjections/stopwords.
    Inner lowercase connectives ('of'/'the' in 'Court of Dao') are allowed.
    """
    if len(name) <= 1 or not name[0].isupper():
        return False
    if _BAD_IN_NAME_RE.search(name):
        return False
    tokens = name.split()
    # Every token must be either a capitalized word or an allowed inner connective. This
    # drops spans where NER glued on a lowercase verb/adverb ("Li Changshou frowned").
    for tok in tokens:
        if tok.lower() in _LEADING_DROP:
            continue
        if not tok[0].isupper():
            return False
    content = [t for t in tokens if t.lower() not in _LEADING_DROP]
    if not content:
        return False
    if len(content) == 1 and content[0].lower() in (_STOPWORDS | _INTERJECTIONS):
        return False
    return True


def _ner_proper_nouns(text: str, *, limit: int) -> list[str]:
    """spaCy-NER implementation. Caller guarantees ``_get_nlp()`` returned a model."""
    nlp = _get_nlp()
    assert nlp is not None  # caller checked
    doc = nlp(text)

    counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    for ent in doc.ents:
        if ent.label_ not in _NAME_LABELS:
            continue
        name = _clean_span(ent.text)
        if not _is_name_like(name):
            continue
        key = name.casefold()
        counts[key] += 1
        display.setdefault(key, name)

    # Frequency desc, then alphabetical for stable output (matches the old contract).
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], display[kv[0]].casefold()))
    return [display[key] for key, _ in ordered[:limit]]


def extract_proper_nouns(text: str, *, limit: int = 30) -> list[str]:
    """Return likely proper nouns in ``text``, most frequent first.

    Offline and deterministic. Uses spaCy NER when available (clean multiword name spans,
    no sentence-opener false positives), falling back to a regex pass if the model is absent.
    De-duplicated case-insensitively; original surface casing preserved; capped at ``limit``.
    """
    if not text or not text.strip():
        return []
    if _get_nlp() is not None:
        return _ner_proper_nouns(text, limit=limit)
    return _regex_proper_nouns(text, limit=limit)


# ---------------------------------------------------------------------------
# Regex fallback (previous implementation) — used only when spaCy/model is absent.
# ---------------------------------------------------------------------------

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
    # Conjunctive adverbs / interjections / quantifiers that commonly OPEN a sentence and
    # get capitalized — frequent false positives in novel prose (seen in testing).
    "however", "although", "though", "therefore", "thus", "hence", "meanwhile",
    "moreover", "furthermore", "nevertheless", "nonetheless", "besides", "instead",
    "otherwise", "unfortunately", "fortunately", "suddenly", "finally", "eventually",
    "perhaps", "maybe", "indeed", "surely", "certainly", "clearly", "obviously",
    "everyone", "everything", "everywhere", "someone", "something", "somewhere",
    "anyone", "anything", "nobody", "nothing", "ah", "oh", "eh", "hmm", "well",
    "yes", "okay", "ok", "please", "thanks", "hello", "goodbye",
    "all", "some", "many", "most", "few", "each", "every", "both", "either", "neither",
    "because", "since", "unless", "until", "whether", "whereas",
}

# Short lowercase connectives allowed to appear *inside* a multi-word proper-noun run.
_CONNECTIVES = {"of", "the", "and", "de", "van", "von", "da", "di"}

# A capitalized token: starts uppercase, letters/digits/hyphens (apostrophes handled
# separately so possessives/contractions don't become part of the name).
_CAP_TOKEN = r"[A-Z][A-Za-z0-9-]*(?:['’][A-Za-z]+)?"
# A run: a capitalized token, then zero+ (connective | capitalized token).
_RUN_RE = re.compile(rf"{_CAP_TOKEN}(?:\s+(?:{'|'.join(_CONNECTIVES)}|{_CAP_TOKEN}))*")

# Sentence boundary just before a position: start of text, or ., !, ?, newline, quote, colon.
_SENTENCE_START_RE = re.compile(r"(?:^|[.!?;:\n\r\"“”‘’()\[\]])\s*$")


def _strip_apostrophe(token: str) -> str:
    """Drop a possessive/contraction tail: Changshou's -> Changshou, I'm -> I, Sister' -> Sister."""
    return _APOS_TAIL_RE.sub("", token)


def _is_sentence_start(text: str, pos: int) -> bool:
    """True if ``pos`` begins a new sentence (so a lone capital there is suspect)."""
    return bool(_SENTENCE_START_RE.search(text[:pos]))


def _trim_run(run: str) -> str:
    """Clean a run into a candidate name.

    - Strip possessive/contraction tails from each token (Changshou's -> Changshou).
    - Strip leading/trailing connectives ('the', 'of') AND leading/trailing stopwords, so a
      sentence-initial opener merged into a run is removed ('Although Li Changshou' ->
      'Li Changshou'; 'The Azure' -> 'Azure').
    """
    tokens = [_strip_apostrophe(t) for t in run.split()]
    tokens = [t for t in tokens if t]  # a bare apostrophe token collapses to ""

    def _droppable(tok: str) -> bool:
        low = tok.lower()
        return low in _CONNECTIVES or low in _STOPWORDS

    while tokens and _droppable(tokens[0]):
        tokens.pop(0)
    while tokens and _droppable(tokens[-1]):
        tokens.pop()
    return " ".join(tokens)


def _regex_proper_nouns(text: str, *, limit: int = 30) -> list[str]:
    """Deterministic regex fallback. Returns likely proper nouns, most frequent first.

    Multi-word names are kept whole. A single capitalized word is only kept if it appears
    somewhere that is NOT a sentence start, or it recurs — this filters ordinary
    sentence-initial capitals. Returns the original surface form, de-duplicated
    case-insensitively.
    """
    if not text or not text.strip():
        return []

    counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    seen_midsentence: set[str] = set()
    lowercased_words = {m.group(0).lower() for m in re.finditer(r"\b[a-z][\w'’-]*\b", text)}

    for m in _RUN_RE.finditer(text):
        raw_run = _trim_run(m.group(0))
        if not raw_run:
            continue
        tokens = raw_run.split()
        key = raw_run.casefold()

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

        keep = is_multiword or key in seen_midsentence or count >= 2
        if not is_multiword:
            if single.lower() in _STOPWORDS:
                keep = False
            if single.lower() in lowercased_words and key not in seen_midsentence:
                keep = False
        if keep:
            results.append((display[key], count))

    results.sort(key=lambda x: (-x[1], x[0].casefold()))
    return [form for form, _ in results[:limit]]
