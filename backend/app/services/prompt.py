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


def build_translation_messages(req: TranslationRequest) -> list[dict[str, str]]:
    """Return chat messages (system + user) for a translation request.

    `req.reference_context` is expected to be the DERIVED context (summary + candidate
    terms) assembled by the context builder — never raw reference chapter text.
    """
    lang = _lang_name(req.source_lang)
    parts: list[str] = []

    if req.glossary:
        # Entries with a source_term render as an authoritative pair; English-only entries
        # render as a preferred spelling. (Phase 4 expands this into category/gender-aware
        # blocks; this keeps the paired path working after the English-first redefinition.)
        glossary_lines = "\n".join(
            (
                f"- {e.source_term} => {e.surface_form}"
                if e.source_term
                else f"- {e.surface_form}"
            )
            + (f"  ({e.note})" if e.note else "")
            for e in req.glossary
        )
        parts.append(f"## Glossary (authoritative term mappings)\n{glossary_lines}")

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
    return EXTRACTION_SYSTEM_PROMPT


def build_extraction_messages(
    content: str, source_lang: SourceLang
) -> list[dict[str, str]]:
    """Return chat messages for extracting a summary + candidate terms from a reference."""
    lang = _lang_name(source_lang)
    user = (
        f"The reference chapter is a {lang}-to-English translation (its text may be "
        "English). Extract the summary and candidate terms as instructed.\n\n"
        "## Reference chapter\n"
        f"{content}"
    )
    return [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
