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
    "If nothing fits a field, use an empty string or empty array. Output JSON only."
)
