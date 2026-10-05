"""Unit tests for the occurrence-detection service (task 14.2).

Pure, offline. These lock in the "exact whole-word, case-insensitive, detection-only"
contract the in-context review loop depends on.
"""

from __future__ import annotations

from app.models import GlossaryEntry
from app.services.term_match import find_occurrences


def _term(surface_form: str, *, id="t", status="approved", category="term") -> GlossaryEntry:
    return GlossaryEntry(
        id=id,
        project_id="p",
        surface_form=surface_form,
        status=status,
        category=category,
    )


def test_basic_whole_word_match():
    out = find_occurrences("Fang Yuan drew his sword.", [_term("Fang Yuan")])
    assert len(out) == 1
    assert out[0].surface_form == "Fang Yuan"
    assert out[0].count == 1
    assert out[0].snippets  # at least one context snippet


def test_case_insensitive():
    out = find_occurrences("fang yuan and FANG YUAN", [_term("Fang Yuan")])
    assert out[0].count == 2


def test_no_substring_match():
    # "Lin" must not match inside "Linda" or "sapling".
    out = find_occurrences("Linda saw a sapling. Lin smiled.", [_term("Lin")])
    assert out[0].count == 1


def test_multi_word_phrase_and_newline_between_words():
    text = "Azure Peak rose high.\nThe Azure\nPeak glowed at dusk."
    out = find_occurrences(text, [_term("Azure Peak")])
    # Both the inline and the newline-separated occurrence count.
    assert out[0].count == 2


def test_term_not_present_is_omitted():
    out = find_occurrences("A quiet village.", [_term("Fang Yuan")])
    assert out == []


def test_empty_output_returns_empty():
    assert find_occurrences("", [_term("Fang Yuan")]) == []


def test_blank_and_punctuation_terms_skipped():
    out = find_occurrences("hello world", [_term("   "), _term("!!!", id="t2")])
    assert out == []


def test_snippet_count_capped_but_total_count_exact():
    text = " ".join(["Lin"] * 10)
    out = find_occurrences(text, [_term("Lin")])
    assert out[0].count == 10
    assert len(out[0].snippets) <= 3  # _MAX_SNIPPETS


def test_duplicate_surface_forms_counted_once():
    terms = [_term("Lin", id="a"), _term("lin", id="b")]
    out = find_occurrences("Lin Lin Lin", terms)
    assert len(out) == 1
    assert out[0].count == 3


def test_results_sorted_by_count_desc():
    text = "Lin Lin Lin. Fang Yuan once."
    out = find_occurrences(text, [_term("Fang Yuan", id="fy"), _term("Lin", id="lin")])
    assert [m.surface_form for m in out] == ["Lin", "Fang Yuan"]


def test_carries_status_and_category():
    out = find_occurrences(
        "Senior Brother nodded.",
        [_term("Senior Brother", status="candidate", category="title")],
    )
    assert out[0].status == "candidate"
    assert out[0].category == "title"


def test_regex_special_chars_in_term_are_literal():
    # A term with regex metacharacters must be matched literally, not as a pattern.
    out = find_occurrences("the C++ guild met", [_term("C++")])
    assert out[0].count == 1
