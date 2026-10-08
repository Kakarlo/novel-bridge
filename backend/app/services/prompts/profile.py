from dataclasses import dataclass


@dataclass(frozen=True)
class PromptProfile:
    translation_system_prompt: str
    extraction_system_prompt: str
    glossary_pairing_system_prompt: str
    style_extraction_system_prompt: str

    max_style_words: int
    style_extraction_max_chars: int

    include_cast_notes: bool
    include_preferred_spellings: bool
