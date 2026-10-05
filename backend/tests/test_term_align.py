"""Tests for deterministic source-term -> English alignment (services/term_align.py).

Fully offline: align_terms takes the source-term list as a plain argument (no spaCy needed),
so these never touch a model. They lock in the structural-correlation behavior: pairing by
appearance order + frequency, NOT by string similarity or translation.
"""

from __future__ import annotations

from app.models import GlossaryEntry
from app.services.term_align import align_terms


def _entry(surface_form: str, source_term: str | None = None) -> GlossaryEntry:
    return GlossaryEntry(
        id=f"g-{surface_form}",
        project_id="p",
        surface_form=surface_form,
        source_term=source_term,
    )


def test_basic_two_character_alignment():
    # 林尘 appears first and most often -> Lin Chen (first, most often in the English).
    raw = "林尘走进大厅。林尘看着苏青。苏青点头。林尘微笑。"
    out = "Lin Chen walked in. Lin Chen looked at Su Qing. Su Qing nodded. Lin Chen smiled."
    glossary = [_entry("Lin Chen"), _entry("Su Qing")]
    pairs = align_terms(["林尘", "苏青"], glossary, raw, out)
    by_source = {c.source_term: c.surface_form for c in pairs}
    assert by_source["林尘"] == "Lin Chen"
    assert by_source["苏青"] == "Su Qing"


def test_pairs_are_one_to_one():
    raw = "林尘。苏青。林尘。"
    out = "Lin Chen. Su Qing. Lin Chen."
    glossary = [_entry("Lin Chen"), _entry("Su Qing")]
    pairs = align_terms(["林尘", "苏青"], glossary, raw, out)
    assert len({c.source_term for c in pairs}) == len(pairs)  # each source once
    assert len({c.surface_form for c in pairs}) == len(pairs)  # each english once


def test_frequency_lifts_confidence_for_matching_counts():
    # Same appearance order; the pair whose counts match exactly should score >= the other.
    raw = "林尘。林尘。林尘。苏青。"
    out = "Lin Chen. Lin Chen. Lin Chen. Su Qing."
    glossary = [_entry("Lin Chen"), _entry("Su Qing")]
    pairs = align_terms(["林尘", "苏青"], glossary, raw, out)
    conf = {c.source_term: c.confidence for c in pairs}
    assert conf["林尘"] >= conf["苏青"]
    assert all(0.0 <= c.confidence <= 1.0 for c in pairs)


def test_already_paired_entries_are_skipped():
    raw = "林尘。苏青。"
    out = "Lin Chen. Su Qing."
    glossary = [_entry("Lin Chen", source_term="林尘"), _entry("Su Qing")]
    pairs = align_terms(["林尘", "苏青"], glossary, raw, out)
    # Lin Chen is already paired -> only the unpaired Su Qing is a candidate.
    assert all(c.surface_form != "Lin Chen" for c in pairs)
    assert any(c.surface_form == "Su Qing" for c in pairs)


def test_source_term_absent_from_raw_is_dropped():
    raw = "林尘走来。"
    out = "Lin Chen arrives. Su Qing waits."
    glossary = [_entry("Lin Chen"), _entry("Su Qing")]
    # 苏青 is detected but never actually appears in raw -> no occurrence, dropped.
    pairs = align_terms(["林尘", "苏青"], glossary, raw, out)
    assert all(c.source_term != "苏青" for c in pairs)


def test_english_name_absent_from_output_is_dropped():
    raw = "林尘。苏青。"
    out = "Lin Chen walks alone."  # Su Qing never appears in the translation
    glossary = [_entry("Lin Chen"), _entry("Su Qing")]
    pairs = align_terms(["林尘", "苏青"], glossary, raw, out)
    assert all(c.surface_form != "Su Qing" for c in pairs)


def test_whole_word_english_matching_no_substring():
    # "Lin" must not match inside "Linda"; relies on term_match's whole-word pattern.
    raw = "林。"
    out = "Linda went home."
    pairs = align_terms(["林"], [_entry("Lin")], raw, out)
    assert pairs == []


def test_empty_inputs_return_empty():
    assert align_terms([], [_entry("Lin Chen")], "raw", "out") == []
    assert align_terms(["林尘"], [], "林尘", "Lin Chen") == []
    assert align_terms(["林尘"], [_entry("Lin Chen")], "", "") == []


def test_confidence_sorted_descending():
    raw = "林尘。林尘。苏青。王武。王武。王武。"
    out = "Lin Chen. Lin Chen. Su Qing. Wang Wu. Wang Wu. Wang Wu."
    glossary = [_entry("Lin Chen"), _entry("Su Qing"), _entry("Wang Wu")]
    pairs = align_terms(["林尘", "苏青", "王武"], glossary, raw, out)
    confs = [c.confidence for c in pairs]
    assert confs == sorted(confs, reverse=True)
