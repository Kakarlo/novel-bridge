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
# Additional fence for translated chapters
_TRANS_OPEN = "<<<ENGLISH_TRANSLATION_START>>>"
_TRANS_CLOSE = "<<<ENGLISH_TRANSLATION_END>>>"


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
            f"- {e.source_term} => {e.surface_form} [{e.category}]"
            for e in pairs
        )

        blocks.append(
            "## Glossary (authoritative term mappings — translate the source term "
            f"exactly as the mapped English; category tags provide context)\n{lines}"
        )

    # ------------------------------------------------------------------
    # Cast / metadata
    # ------------------------------------------------------------------
    cast_entries = [
        e for e in entries
        if e.category == "character"
    ]

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

            if e.note:
                cast_lines.append(f"  Note: {e.note}")

        blocks.append(
            "## Cast (character information — use this for gender, pronouns, "
            "and character context)\n"
            + "\n".join(cast_lines)
        )

    # ------------------------------------------------------------------
    # Preferred English spellings
    # ------------------------------------------------------------------
    if english_only:
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


def build_translation_messages(req: TranslationRequest) -> list[dict[str, str]]:
    """Return chat messages (system + user) for a translation request.

    `req.reference_context` is expected to be the DERIVED context (summary + candidate
    terms) assembled by the context builder — never raw reference chapter text.
    """
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
    parts.extend(_format_glossary_blocks(_prompt_glossary_entries(req)))

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

# GLOSSARY_PAIRING_SYSTEM_PROMPT = (
#     "You align terminology between a source-language novel chapter and its existing "
#     "English translation. You do NOT translate or re-translate anything.\n"
#     "\n"
#     "You are given the raw source chapter and the English translation that was already "
#     "produced from it. They tell the same story in the same order. Your job is to bind "
#     "each important recurring source term (character names, places, organizations, titles, "
#     "skills, key terminology) to the EXACT English spelling that already appears in the "
#     "translation. Never invent a new romanization or spelling — only use spellings that "
#     "are actually present in the English text.\n"
#     "\n"
#     "Return ONLY a single JSON object, no prose and no code fences, with exactly one key:\n"
#     '  "pairs": an array of up to 30 objects, each with:\n'
#     '     "source_term": the term as it appears in the source text (required),\n'
#     '     "surface_form": the exact English spelling used in the translation (required),\n'
#     '     "category": one of "character", "title", "term" (default "term"),\n'
#     '     "gender": one of "male", "female", "unknown" (characters only; else "unknown"),\n'
#     '     "note": a short optional disambiguator (e.g. "protagonist"), or an empty string.\n'
#     "\n"
#     "Only include a pair when you are confident the source term and the English spelling "
#     "refer to the same entity. Omit anything you cannot pair with a spelling present in the "
#     "translation. No duplicates. Output JSON only."
# )

GLOSSARY_PAIRING_SYSTEM_PROMPT = (
    "You align terminology between a source-language novel chapter and its existing "
    "English translation. You do NOT translate, rewrite, summarize, or interpret "
    "either text.\n"
    "\n"
    "The source chapter and English translation describe the same events. "
    "Your task is to identify source-language entities and pair them with the "
    "EXACT English spellings already present in the translation.\n"
    "\n"
    "Never invent a translation, romanization, spelling, title, gender, "
    "relationship, affiliation, role, or note that is not supported by "
    "evidence in the provided texts.\n"
    "\n"
    "# CATEGORIES\n"
    "\n"
    'Use exactly one of these values for "category":\n'
    '- "character" — named people\n'
    '- "title" — honorifics, ranks, and forms of address\n'
    '- "location" — places, regions, buildings, landmarks, and realms\n'
    '- "organization" — sects, clans, factions, schools, courts, and groups\n'
    '- "item" — artifacts, treasures, pills, weapons, techniques, manuals, and named objects\n'
    '- "term" — other recurring terminology\n'
    "\n"
    "# GENDER\n"
    "\n"
    "For entities in the \"character\" category, also report the character's gender.\n"
    "\n"
    "Gender exists to help future translations maintain pronoun consistency.\n"
    "\n"
    "Determine gender ONLY from evidence in the source chapter or English translation:\n"
    "- gendered pronouns\n"
    "- explicit descriptions\n"
    "- gendered titles or forms of address\n"
    "- clearly stated relationships\n"
    "\n"
    "Do NOT infer gender from the name itself.\n"
    "Do NOT assume the protagonist is male.\n"
    "\n"
    'Report exactly one of:\n'
    '- "female"\n'
    '- "male"\n'
    '- "unknown"\n'
    "\n"
    "\"unknown\" is the correct answer whenever evidence is absent.\n"
    "A wrong gender is worse than an unknown gender.\n"
    "\n"
    "# NOTES\n"
    "\n"
    "The note field is optional.\n"
    "\n"
    "Use it only when the text provides a short factual identifier that helps "
    "identify or distinguish the entity.\n"
    "\n"
    "Suitable note content includes:\n"
    "- roles\n"
    "- ranks\n"
    "- occupations\n"
    "- affiliations\n"
    "- explicitly stated relationships\n"
    "\n"
    "Do NOT include:\n"
    "- personality traits\n"
    "- appearance descriptions\n"
    "- opinions\n"
    "- power-level assessments\n"
    "- plot summaries\n"
    "- speculation\n"
    "\n"
    "Keep notes concise.\n"
    "Leave note as an empty string when no useful factual identifier is available.\n"
    "\n"
    "# OUTPUT FORMAT\n"
    "\n"
    "Return ONLY a single JSON object with exactly one key:\n"
    '  "pairs"\n'
    "\n"
    'Each element of "pairs" must be:\n'
    "{\n"
    '  "source_term": string,\n'
    '  "surface_form": string,\n'
    '  "category": "character" | "title" | "location" | "organization" | "item" | "term",\n'
    '  "gender": "male" | "female" | "unknown",\n'
    '  "note": string\n'
    "}\n"
    "\n"
    "# EXTRACTION RULES\n"
    "\n"
    "1. Use only English spellings that already appear in the translation.\n"
    "2. Never invent a spelling or romanization.\n"
    "3. Include only pairs you can confidently align.\n"
    "4. Omit uncertain pairs.\n"
    "5. Remove duplicates.\n"
    "6. Prefer recurring and translation-relevant entities.\n"
    "7. Preserve the source term exactly as it appears in the source text.\n"
    "8. Preserve the English spelling exactly as it appears in the translation.\n"
    "\n"
    "Output JSON only."
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
        f"The source chapter is {lang}; the translation is its English rendering."
    ]
    # if candidates:
    #     parts.append(
    #         "## Candidate terms (a deterministic pre-pass flagged these as likely recurring "
    #         "terms — prioritize pairing them, but add any other clearly recurring entity you "
    #         "find. These are hints, not a required list.)\n" + ", ".join(candidates)
    #     )
    parts.append(f"## Source chapter\n{_RAW_OPEN}\n{raw_text}\n{_RAW_CLOSE}")
    parts.append(f"## English translation\n{_TRANS_OPEN}\n{output_text}\n{_TRANS_CLOSE}")
    print(GLOSSARY_PAIRING_SYSTEM_PROMPT)
    print(parts)
    return [
        {"role": "system", "content": GLOSSARY_PAIRING_SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


# --- Style extraction prompts ------------------------------------------------

STYLE_EXTRACTION_SYSTEM_PROMPT = (
    "You are a linguistic analyst and literary editor. You analyze a previously translated "
    "novel chapter and extract a concise, reusable Writing Style Profile.\n"
    "\n"
    "Ignore the plot, characters, and events entirely. Instead, focus on HOW the text is "
    "written:\n"
    "\n"
    "1. PROSE PATTERNS: sentence length and rhythm (short/punchy vs long/descriptive), "
    "narrative pacing, paragraph structure.\n"
    "2. VOCABULARY & REGISTER: archaic, formal, conversational, or mixed? How literary vs "
    "modern is the word choice?\n"
    "3. DIALOGUE TONE: how different characters speak (do elders use formal English? do "
    "younger characters use modern slang?). Dialogue tag style.\n"
    "4. NARRATIVE PERSPECTIVE: first person, third person limited, third person omniscient? "
    "How close is the POV to the character's thoughts?\n"
    "5. LOCALIZATION PREFERENCES: are honorifics left intact (e.g. '-san', 'Shixiong'), "
    "capitalized literally ('Elder', 'Senior Brother'), or heavily localized? Are titles "
    "and terms left in the source language or translated?\n"
    "6. IMAGERY & DESCRIPTION: level of sensory detail, metaphor density, action scene pacing.\n"
    "\n"
    "Output a concise, structured markdown guide (150-300 words maximum) that another AI "
    "translator can use as a system instruction to replicate this writing style exactly. "
    "Write it as direct instructions ('Use ...', 'Maintain ...', 'Keep ...'), not as "
    "observations ('The text uses ...'). No plot summary, no character names, no code fences."
)


def build_style_extraction_system_prompt() -> str:
    return STYLE_EXTRACTION_SYSTEM_PROMPT


def build_style_extraction_messages(
    content: str,
    source_lang: SourceLang,
) -> list[dict[str, str]]:
    """Return chat messages to extract a writing-style profile from a reference chapter."""
    lang = _lang_name(source_lang)
    parts = [
        f"The reference chapter below is a {lang}-to-English translation. Analyze the "
        "English prose style as instructed and output a Writing Style Profile.",
        "## Reference chapter\n" + content,
    ]
    return [
        {"role": "system", "content": STYLE_EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]
