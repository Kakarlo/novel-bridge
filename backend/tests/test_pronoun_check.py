"""Tests for the EXPERIMENTAL pronoun-drift detector (stdlib, offline).

Detection only — these assert it FLAGS likely mismatches and never claims to rewrite.
"""

from __future__ import annotations

from app.models import GlossaryEntry
from app.services.pronoun_check import find_pronoun_drift


def _char(surface: str, gender: str) -> GlossaryEntry:
    return GlossaryEntry(
        id=surface,
        project_id="p",
        surface_form=surface,
        status="approved",
        category="character",
        gender=gender,
    )


def test_flags_opposite_pronoun_near_name():
    text = "Fang Yuan drew his sword. Then she smiled, which was odd."
    flags = find_pronoun_drift(text, [_char("Fang Yuan", "male")])
    # 'she' near a male character is flagged.
    assert any(f.found_pronoun == "she" for f in flags)
    assert flags[0].expected_gender == "male"
    assert "Fang Yuan" in flags[0].snippet


def test_no_flag_when_pronoun_matches_gender():
    text = "Fang Yuan drew his sword. He smiled."
    assert find_pronoun_drift(text, [_char("Fang Yuan", "male")]) == []


def test_neutral_pronoun_never_flagged():
    text = "Fang Yuan nodded. They left together."
    assert find_pronoun_drift(text, [_char("Fang Yuan", "male")]) == []


def test_unknown_gender_skipped():
    text = "Fang Yuan drew his sword. Then she smiled."
    assert find_pronoun_drift(text, [_char("Fang Yuan", "unknown")]) == []


def test_non_character_skipped():
    entry = GlossaryEntry(
        id="t", project_id="p", surface_form="Azure Sect", status="approved",
        category="term", gender=None,
    )
    text = "Azure Sect fell. She was gone."
    assert find_pronoun_drift(text, [entry]) == []


def test_female_character_flags_male_pronoun():
    text = "Yunyun raised her hand, but he hesitated for a moment there."
    flags = find_pronoun_drift(text, [_char("Yunyun", "female")])
    assert any(f.found_pronoun == "he" for f in flags)


def test_empty_text():
    assert find_pronoun_drift("", [_char("Fang Yuan", "male")]) == []
