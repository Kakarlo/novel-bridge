"""Prompt construction for translation + reference extraction (Requirements 3.3, 4.1).

Prompts are a small set of named, composable builders rather than one blob:

- `build_translation_system_prompt()` / `build_translation_messages()` — the translate
  path. The system prompt pins the task hard (translate ONLY the raw chapter; the
  reference-derived context is for style/consistency and must NEVER be reproduced or
  continued; output only the translation). The raw chapter is the last, most prominent,
  clearly fenced block. This structure fixes the reference-echo bug where a raw reference
  dump dominated the context and the model continued/echoed it.

- `build_extraction_system_prompt()` / `build_extraction_messages()` — the reference
  extraction path (runs once at upload / on resummarize). Asks for a compact JSON object
  with a short style/plot summary and candidate glossary terms, so later translations send
  the *summary + glossary*, never the raw reference text.
"""

from __future__ import annotations

from app.engines.base import TranslationRequest
from app.models import SourceLang

_LANG_NAMES = {"zh": "Chinese", "ja": "Japanese"}

# Fence used to delimit the raw chapter so the instruction can point at it unambiguously.
_RAW_OPEN = "<<<RAW_CHAPTER_START>>>"
_RAW_CLOSE = "<<<RAW_CHAPTER_END>>>"


def _lang_name(source_lang: str) -> str:
    return _LANG_NAMES.get(source_lang, source_lang)


# --- Translation prompts ----------------------------------------------------

TRANSLATION_SYSTEM_PROMPT = (
    "You are an expert literary translator of web and light novels. Your sole task is "
    "to translate the RAW CHAPTER provided by the user into fluent, natural English "
    "prose.\n"
    "\n"
    "Follow these rules strictly:\n"
    "1. Translate ONLY the text inside the raw-chapter delimiters. Do not translate, "
    "reproduce, quote, summarize, or continue any other section.\n"
    "2. The reference context (summary and terms) is background for STYLE, TONE, and "
    "TERMINOLOGY CONSISTENCY ONLY. It is NOT part of the text to translate and must "
    "NEVER appear in your output, verbatim or paraphrased.\n"
    "3. The glossary is authoritative: translate the listed source terms exactly as "
    "specified (names, places, skills, terminology).\n"
    "4. Preserve paragraph breaks and dialogue structure of the raw chapter.\n"
    "5. Output ONLY the English translation of the raw chapter. No notes, commentary, "
    "pinyin, romaji, headings, or the original text."
)


def build_translation_system_prompt() -> str:
    return TRANSLATION_SYSTEM_PROMPT


def _prompt_glossary_entries(req: TranslationRequest) -> list:
    """The glossary entries that may steer the prompt (task 14, Phase 4).

    Only entries that are safe to assert as authoritative reach the model:
    - any entry with a ``source_term`` (a classic paired mapping), OR
    - an English-first entry whose ``status`` is ``approved``.

    ``candidate`` (not yet reviewed) and ``rejected`` English-only entries are excluded —
    the user hasn't endorsed them, so the model must not treat them as preferred spellings.
    Occurrence detection still runs over the full glossary elsewhere, so candidates can
    still be surfaced for approval.
    """
    return [
        e for e in req.glossary if e.source_term or e.status == "approved"
    ]


def _format_glossary_blocks(entries: list) -> list[str]:
    """Render up to two glossary blocks: authoritative source=>English pairs, and a
    category/gender-aware 'preferred English spellings' list for English-first entries."""
    pairs = [e for e in entries if e.source_term]
    english_only = [e for e in entries if not e.source_term]

    blocks: list[str] = []

    if pairs:
        lines = "\n".join(
            f"- {e.source_term} => {e.surface_form}" + (f"  ({e.note})" if e.note else "")
            for e in pairs
        )
        blocks.append(
            "## Glossary (authoritative term mappings — translate the source term exactly "
            f"as the mapped English)\n{lines}"
        )

    if english_only:
        # Group by category so a weak model gets structure. Characters carry gender inline
        # (steers zh->en pronoun consistency); titles are grouped; terms are a plain list.
        by_cat: dict[str, list] = {"character": [], "title": [], "term": []}
        for e in english_only:
            by_cat.get(e.category, by_cat["term"]).append(e)

        sub: list[str] = []
        for e in by_cat["character"]:
            gender = f" ({e.gender})" if e.gender and e.gender != "unknown" else ""
            note = f" — {e.note}" if e.note else ""
            sub.append(f"- {e.surface_form}{gender}{note}  [character]")
        for e in by_cat["title"]:
            note = f" — {e.note}" if e.note else ""
            sub.append(f"- {e.surface_form}{note}  [title]")
        for e in by_cat["term"]:
            note = f" — {e.note}" if e.note else ""
            sub.append(f"- {e.surface_form}{note}")

        blocks.append(
            "## Preferred English spellings (use these exact spellings for these names and "
            "terms; for characters, keep pronouns consistent with the stated gender)\n"
            + "\n".join(sub)
        )

    return blocks


def build_translation_messages(req: TranslationRequest) -> list[dict[str, str]]:
    """Return chat messages (system + user) for a translation request.

    `req.reference_context` is expected to be the DERIVED context (summary + candidate
    terms) assembled by the context builder — never raw reference chapter text.
    """
    lang = _lang_name(req.source_lang)
    parts: list[str] = []

    # Only approved / paired entries steer the prompt (Phase 4). Rendered as up to two
    # blocks: authoritative pairs, and a category/gender-aware preferred-spellings list.
    parts.extend(_format_glossary_blocks(_prompt_glossary_entries(req)))

    ref = req.reference_context.strip()
    if ref:
        parts.append(
            "## Reference context (style/terminology background — DO NOT translate or "
            f"reproduce)\n{ref}"
        )
    else:
        parts.append(
            "## Reference context\n(none available — translate from the glossary and "
            "the raw chapter alone)"
        )

    parts.append(
        f"## Raw chapter to translate (source language: {lang})\n"
        "Translate ONLY the text between the delimiters below. It may be short — if so, "
        "your translation must be correspondingly short. Do not add, continue, or pad with "
        "anything from the reference context. Output only the English translation.\n"
        f"{_RAW_OPEN}\n{req.raw_text}\n{_RAW_CLOSE}"
    )

    return [
        {"role": "system", "content": TRANSLATION_SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


# Backwards-compatible alias (older imports used `build_messages`).
def build_messages(req: TranslationRequest) -> list[dict[str, str]]:
    return build_translation_messages(req)


# --- Reference extraction prompts -------------------------------------------

EXTRACTION_SYSTEM_PROMPT = (
    "You analyze a previously translated novel chapter and extract reusable context "
    "for keeping future translations consistent. You do NOT translate anything.\n"
    "\n"
    "Return ONLY a single JSON object, no prose and no code fences, with exactly these "
    "keys:\n"
    '  "summary": a 2-4 sentence summary of the chapter\'s plot, tone, narrative voice, '
    "and register (formal/casual, POV), useful for matching style.\n"
    '  "candidate_terms": an array of up to 20 short strings — recurring proper nouns '
    "and terminology (character names, places, titles, skills) a translator should keep "
    "consistent. No duplicates, no explanations.\n"
    "\n"
    'If nothing fits a field, use an empty string or empty array. Output JSON only.'
)


def build_extraction_system_prompt() -> str:
    # ponytail: REVISIT whether the AI `candidate_terms` extraction still earns its keep.
    # Its unique value was lowercase genre jargon that NER misses — but the deterministic
    # domain-vocab union (services/noun_extract.py + app/data/*.txt) now backfills much of
    # that offline, and spaCy NER handles proper names. If measurement shows candidate_terms
    # rarely adds a term beyond NER + domain vocab, drop the terms half of this extraction and
    # keep only the summary (one fewer thing for a weak local model to get wrong). Needs a
    # before/after comparison on real chapters first — a measurement call, not a now-change.
    return EXTRACTION_SYSTEM_PROMPT


def build_extraction_messages(
    content: str,
    source_lang: SourceLang,
    detected_names: list[str] | None = None,
) -> list[dict[str, str]]:
    """Return chat messages for extracting a summary + candidate terms from a reference.

    ``detected_names`` are proper nouns found by the spaCy NER pass (Issue 1). They are
    passed as a hint so the model doesn't rediscover names NER already handles and can focus
    on terminology NER can't catch (lowercase jargon, skills, concepts). The model is told
    these are hints, not a required echo.
    """
    lang = _lang_name(source_lang)
    parts = [
        f"The reference chapter is a {lang}-to-English translation (its text may be "
        "English). Extract the summary and candidate terms as instructed."
    ]
    if detected_names:
        parts.append(
            "## Already-detected names (NER has already extracted these proper names — "
            "character/place/org names are handled, so do NOT just re-list them. Focus your "
            "candidate_terms on what NER misses: lowercase concepts, skills, techniques, and "
            "terminology. Add a detected name only if it is a genuinely important recurring "
            "term.)\n"
            + ", ".join(detected_names)
        )
    parts.append("## Reference chapter\n" + content)
    return [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


# --- Glossary pairing prompts -----------------------------------------------

GLOSSARY_PAIRING_SYSTEM_PROMPT = (
    "You align terminology between a source-language novel chapter and its existing "
    "English translation. You do NOT translate or re-translate anything.\n"
    "\n"
    "You are given the raw source chapter and the English translation that was already "
    "produced from it. They tell the same story in the same order. Your job is to bind "
    "each important recurring source term (character names, places, organizations, titles, "
    "skills, key terminology) to the EXACT English spelling that already appears in the "
    "translation. Never invent a new romanization or spelling — only use spellings that "
    "are actually present in the English text.\n"
    "\n"
    "Return ONLY a single JSON object, no prose and no code fences, with exactly one key:\n"
    '  "pairs": an array of up to 30 objects, each with:\n'
    '     "source_term": the term as it appears in the source text (required),\n'
    '     "surface_form": the exact English spelling used in the translation (required),\n'
    '     "category": one of "character", "title", "term" (default "term"),\n'
    '     "gender": one of "male", "female", "unknown" (characters only; else "unknown"),\n'
    '     "note": a short optional disambiguator (e.g. "protagonist"), or an empty string.\n'
    "\n"
    "Only include a pair when you are confident the source term and the English spelling "
    "refer to the same entity. Omit anything you cannot pair with a spelling present in the "
    "translation. No duplicates. Output JSON only."
)


def build_glossary_pairing_system_prompt() -> str:
    return GLOSSARY_PAIRING_SYSTEM_PROMPT


def build_glossary_pairing_messages(
    raw_text: str,
    output_text: str,
    source_lang: SourceLang,
    candidates: list[str] | None = None,
) -> list[dict[str, str]]:
    """Return chat messages to pair source terms to the English spellings in a translation.

    ``candidates`` are deterministic pre-filtered terms (source-language proper nouns from
    the NER pass and/or English names) passed as hints so a weak local model focuses on real
    recurring terms rather than scanning the whole text blind — this is the token-saving
    hybrid (rule-based pre-filter + a small LLM pass). The model may still add pairs beyond
    the hints, and is told these are hints, not a required echo.
    """
    lang = _lang_name(source_lang)
    parts = [
        f"The source chapter is {lang}; the translation is its English rendering. Pair the "
        "source terms to the exact English spellings used in the translation, as instructed."
    ]
    if candidates:
        parts.append(
            "## Candidate terms (a deterministic pre-pass flagged these as likely recurring "
            "terms — prioritize pairing them, but add any other clearly recurring entity you "
            "find. These are hints, not a required list.)\n" + ", ".join(candidates)
        )
    parts.append(f"## Source chapter\n{_RAW_OPEN}\n{raw_text}\n{_RAW_CLOSE}")
    parts.append("## English translation\n" + output_text)
    return [
        {"role": "system", "content": GLOSSARY_PAIRING_SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]
