"""Unit tests for the rule-based proper-noun pre-pass (field-fix #2).

Pure, offline. These lock in the behavior that supplements the AI extraction: catch
capitalized names reliably, keep multi-word names whole, and filter the obvious
sentence-initial false positives.
"""

from __future__ import annotations

from app.services.noun_extract import extract_proper_nouns


def test_multi_word_name_kept_whole():
    text = "The disciple bowed. Li Changshou raised his hand as Li Changshou smiled."
    names = extract_proper_nouns(text)
    assert "Li Changshou" in names
    # The multi-word name is not split into bare "Li"/"Changshou".
    assert "Li" not in names


def test_sentence_initial_common_word_filtered():
    # "Dawn" only ever appears at a sentence start and also as a lowercase word -> dropped.
    text = "Dawn came early. The dawn was cold. Dawn faded."
    names = extract_proper_nouns(text)
    assert "Dawn" not in names


def test_recurring_single_name_kept():
    text = "Fang Yuan walked. Later, Fang spoke. Fang left."
    names = extract_proper_nouns(text)
    assert "Fang Yuan" in names


def test_midsentence_single_capital_kept():
    text = "the elder told Changshou to wait."
    names = extract_proper_nouns(text)
    assert "Changshou" in names


def test_connectives_inside_name_preserved():
    text = "He joined the Sect of the Azure Cloud. The Sect of the Azure Cloud was old."
    names = extract_proper_nouns(text)
    assert any("Azure Cloud" in n for n in names)


def test_leading_the_trimmed():
    text = "The Azure Peak loomed. The Azure Peak glowed."
    names = extract_proper_nouns(text)
    assert "Azure Peak" in names
    assert "The Azure Peak" not in names


def test_frequency_ordering():
    # "Jin Guang" appears 3x, "Lin Feng" 2x -> Jin Guang listed first.
    text = (
        "the elder Jin Guang spoke. then Lin Feng replied to Jin Guang. "
        "later Jin Guang and Lin Feng left."
    )
    names = extract_proper_nouns(text)
    assert names.index("Jin Guang") < names.index("Lin Feng")


def test_empty_text():
    assert extract_proper_nouns("") == []
    assert extract_proper_nouns("   ") == []


def test_pure_lowercase_has_no_names():
    assert extract_proper_nouns("the cat sat on the mat quietly") == []


def test_limit_respected():
    # Distinct mid-sentence names separated by lowercase filler so each is its own run.
    text = " ".join(f"saw Name{i} there." for i in range(50))
    names = extract_proper_nouns(text, limit=5)
    assert len(names) == 5
