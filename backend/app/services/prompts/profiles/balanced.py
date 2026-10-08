from app.services.prompts.extraction import EXTRACTION_SYSTEM_PROMPT
from app.services.prompts.glossary_pairing import GLOSSARY_PAIRING_SYSTEM_PROMPT
from app.services.prompts.profile import PromptProfile
from app.services.prompts.style_extraction import STYLE_EXTRACTION_SYSTEM_PROMPT
from app.services.prompts.translation import TRANSLATION_SYSTEM_PROMPT

BALANCED_PROFILE = PromptProfile(
    translation_system_prompt=TRANSLATION_SYSTEM_PROMPT,
    extraction_system_prompt=EXTRACTION_SYSTEM_PROMPT,
    glossary_pairing_system_prompt=GLOSSARY_PAIRING_SYSTEM_PROMPT,
    style_extraction_system_prompt=STYLE_EXTRACTION_SYSTEM_PROMPT,

    max_style_words=200,
    style_extraction_max_chars=12000,

    include_cast_notes=True,
    include_preferred_spellings=True,
)
