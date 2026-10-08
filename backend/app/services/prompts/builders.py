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

from app.debug import dump_messages
from app.engines.base import TranslationRequest
from app.models import SourceLang
from app.services.prompts.constants import (
    _LANG_NAMES,
    _RAW_CLOSE,
    _RAW_OPEN,
    _TRANS_CLOSE,
    _TRANS_OPEN,
)
from app.services.prompts.profile import PromptProfile
from app.services.prompts.profiles import get_profile


def _lang_name(source_lang: str) -> str:
    return _LANG_NAMES.get(source_lang, source_lang)


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
    return [e for e in req.glossary if e.source_term or e.status == "approved"]


def _format_glossary_blocks(
    entries: list,
    profile: PromptProfile,
) -> list[str]:
    """Render glossary and cast blocks.

    Glossary:
        Authoritative source => translation mappings only.

    Cast:
        Character metadata (gender, notes) separated from translation rules.
    """
    pairs = [e for e in entries if e.source_term]
    english_only = [e for e in entries if not e.source_term]

    blocks: list[str] = []

    # ------------------------------------------------------------------
    # Glossary (pure mappings)
    # ------------------------------------------------------------------
    if pairs:
        lines = "\n".join(
            f"- {e.source_term} => {e.surface_form} [{e.category}]" for e in pairs
        )

        blocks.append(
            "## Glossary (authoritative term mappings — translate the source term "
            f"exactly as the mapped English; category tags provide context)\n{lines}"
        )

    # ------------------------------------------------------------------
    # Cast / metadata
    # ------------------------------------------------------------------
    cast_entries = [e for e in entries if e.category == "character"]

    if cast_entries:
        cast_lines: list[str] = []

        for e in cast_entries:
            source = (
                f"{e.source_term} => {e.surface_form}"
                if e.source_term
                else e.surface_form
            )

            gender = (
                f" [{e.gender.capitalize()}]"
                if e.gender and e.gender != "unknown"
                else ""
            )

            cast_lines.append(f"- {source}{gender}")

            if profile.include_cast_notes and e.note:
                cast_lines.append(f"  Note: {e.note}")

        blocks.append(
            "## Cast (character information — use this for gender, pronouns, "
            "and character context)\n" + "\n".join(cast_lines)
        )

    # ------------------------------------------------------------------
    # Preferred English spellings
    # ------------------------------------------------------------------
    if profile.include_preferred_spellings and english_only:
        lines = []

        for e in english_only:
            line = f"- {e.surface_form}"

            if e.category != "term":
                line += f" [{e.category}]"

            if e.note:
                line += f"\n  Note: {e.note}"

            lines.append(line)

        blocks.append(
            "## Preferred English spellings\n"
            "Use these exact spellings whenever these English names or terms appear.\n"
            + "\n".join(lines)
        )

    return blocks


def build_translation_messages(
    req: TranslationRequest,
    profile_name: str = "low",
) -> list[dict[str, str]]:
    """Return chat messages (system + user) for a translation request.

    `req.reference_context` is expected to be the DERIVED context (summary + candidate
    terms) assembled by the context builder — never raw reference chapter text.
    """
    profile = get_profile(profile_name)

    lang = _lang_name(req.source_lang)
    parts: list[str] = []

    # The per-project style profile goes first: it's a top-level instruction on HOW to
    # write, so the model should read it before terminology and the raw chapter. It's a
    # guide for tone/register, not text to reproduce (same stance as reference context).
    style = req.style_profile.strip()
    if style:
        parts.append(
            "## Writing style (follow these style instructions for the translation — this "
            f"describes HOW to write, it is NOT text to translate or reproduce)\n{style}"
        )

    # Only approved / paired entries steer the prompt (Phase 4). Rendered as up to two
    # blocks: authoritative pairs, and a category/gender-aware preferred-spellings list.
    parts.extend(_format_glossary_blocks(_prompt_glossary_entries(req), profile))

    # TODO: Remove the use of refernce_context as we do not use ai to summarize text, now we extract writing style
    # ref = req.reference_context.strip()
    # if ref:
    #     parts.append(
    #         "## Reference context (style/terminology background — DO NOT translate or "
    #         f"reproduce)\n{ref}"
    #     )
    # else:
    #     parts.append(
    #         "## Reference context\n(none available — translate from the glossary and "
    #         "the raw chapter alone)"
    #     )

    parts.append(
        f"## Raw chapter to translate (source language: {lang})\n"
        "Translate ONLY the text between the delimiters below. "
        "The output should contain approximately the same amount of content as the raw chapter. "
        "Do not continue the story. Do not add new text. Output only the English translation.\n"
        f"{_RAW_OPEN}\n{req.raw_text}\n{_RAW_CLOSE}"
    )

    messages = [
        {"role": "system", "content": profile.translation_system_prompt},
        {"role": "user", "content": "\n\n".join(parts)},
    ]
    dump_messages(messages, "STYLE EXTRACTION")
    return messages



# Deprecated: Is not being used
def build_extraction_messages(
    content: str,
    source_lang: SourceLang,
    detected_names: list[str] | None = None,
    profile_name: str = "low",
) -> list[dict[str, str]]:
    """Return chat messages for extracting a summary + candidate terms from a reference.

    ``detected_names`` are proper nouns found by the spaCy NER pass (Issue 1). They are
    passed as a hint so the model doesn't rediscover names NER already handles and can focus
    on terminology NER can't catch (lowercase jargon, skills, concepts). The model is told
    these are hints, not a required echo.
    """
    profile = get_profile(profile_name)
    lang = _lang_name(source_lang)
    parts = [
        f"The reference chapter is a {lang}-to-English translation (its text may be ",
        "English). Extract the summary and candidate terms as instructed.",
    ]
    if detected_names:
        parts.append(
            "## Already-detected names (NER has already extracted these proper names — "
            "character/place/org names are handled, so do NOT just re-list them. Focus your "
            "candidate_terms on what NER misses: lowercase concepts, skills, techniques, and "
            "terminology. Add a detected name only if it is a genuinely important recurring "
            "term.)\n" + ", ".join(detected_names)
        )
    parts.append("## Reference chapter\n" + content)
    return [
        {"role": "system", "content": profile.extraction_system_prompt},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def build_glossary_pairing_messages(
    raw_text: str,
    output_text: str,
    source_lang: SourceLang,
    candidates: list[str] | None = None,
    profile_name: str = "low",
) -> list[dict[str, str]]:
    """Return chat messages to pair source terms to the English spellings in a translation.

    ``candidates`` are deterministic pre-filtered terms (source-language proper nouns from
    the NER pass and/or English names) passed as hints so a weak local model focuses on real
    recurring terms rather than scanning the whole text blind — this is the token-saving
    hybrid (rule-based pre-filter + a small LLM pass). The model may still add pairs beyond
    the hints, and is told these are hints, not a required echo.
    """
    profile = get_profile(profile_name)
    lang = _lang_name(source_lang)
    parts = [f"The source chapter is {lang}; the translation is its English rendering."]
    # if candidates:
    #     parts.append(
    #         "## Candidate terms (a deterministic pre-pass flagged these as likely recurring "
    #         "terms — prioritize pairing them, but add any other clearly recurring entity you "
    #         "find. These are hints, not a required list.)\n" + ", ".join(candidates)
    #     )
    parts.append(f"## Source chapter\n{_RAW_OPEN}\n{raw_text}\n{_RAW_CLOSE}")
    parts.append(
        f"## English translation\n{_TRANS_OPEN}\n{output_text}\n{_TRANS_CLOSE}"
    )
    messages = [
        {"role": "system", "content": profile.glossary_pairing_system_prompt},
        {"role": "user", "content": "\n\n".join(parts)},
    ]
    dump_messages(messages, "GLOSSARY PAIRING")
    return messages


def build_style_extraction_messages(
    content: str,
    source_lang: SourceLang,
    profile_name: str = "low",
) -> list[dict[str, str]]:
    """Return chat messages to extract a writing-style profile from a reference chapter."""
    profile = get_profile(profile_name)
    lang = _lang_name(source_lang)

    # Testing how truncating the reference chapter affects style extraction
    chapter = _truncate_style_reference(
        content,
        profile.style_extraction_max_chars,
    )

    parts = [
        f"The reference chapter below is a {lang}-to-English translation. Analyze the " +
        "English prose style as instructed and output a Writing Style Profile.",
        "## Reference chapter\n" + chapter,
    ]
    messages = [
        {"role": "system", "content": profile.style_extraction_system_prompt},
        {"role": "user", "content": "\n\n".join(parts)},
    ]
    dump_messages(messages, "STYLE EXTRACTION")
    return messages

# Helper

def _truncate_style_reference(
    content: str,
    max_chars: int,
) -> str:
    if len(content) <= max_chars:
        return content

    truncated = content[:max_chars]

    last_break = truncated.rfind("\n")

    return (
        truncated[:last_break]
        if last_break > 0
        else truncated
    )