"""Tests for the proper-noun pre-pass (field-fix #2 / Issue 1: spaCy NER).

Two layers, both offline:

- NER layer (``extract_proper_nouns`` with the spaCy model). Skipped automatically via
  ``importorskip`` if ``en_core_web_sm`` isn't installed, so the suite still runs offline.
  These lock in the Issue 1 win: sentence-openers and contractions ("I'm", "Although",
  "Unfortunately") no longer leak into detected names, and multiword names stay whole.
- Fallback layer (``_regex_proper_nouns`` directly). Always runs — no model needed. These
  keep the previous deterministic heuristic honest for the no-model case.
"""

from __future__ import annotations

import pytest

from app.services.noun_extract import _get_nlp, _regex_proper_nouns, extract_proper_nouns


def _ner_available() -> bool:
    return _get_nlp() is not None


# ---------------------------------------------------------------------------
# NER layer — the real path. Skipped if the model isn't installed.
# ---------------------------------------------------------------------------

ner = pytest.mark.skipif(not _ner_available(), reason="en_core_web_sm not installed")


@ner
def test_ner_multi_word_name_kept_whole():
    text = "The disciple bowed. Li Changshou raised his hand as Li Changshou smiled."
    names = extract_proper_nouns(text)
    assert "Li Changshou" in names


@ner
def test_ner_contractions_not_treated_as_names():
    # The core Issue 1 regression: regex leaked "I'm"/"I'll"/"I"; NER must not.
    names = extract_proper_nouns("I'm fine. I'll go. the man watched.")
    assert "I'm" not in names
    assert "I'll" not in names
    assert "I" not in names


@ner
def test_ner_sentence_opener_adverbs_dropped():
    text = "However it rained. Although skies cleared. Unfortunately the road flooded. Everyone left."
    names = extract_proper_nouns(text)
    for w in ["However", "Although", "Unfortunately", "Everyone", "I'm", "I'll", "Ah"]:
        assert w not in names


@ner
def test_ner_opener_not_glued_to_real_name():
    text = "Although Li Changshou hesitated, Li Changshou pressed on."
    names = extract_proper_nouns(text)
    assert "Li Changshou" in names
    assert "Although Li Changshou" not in names
    assert "Although" not in names


@ner
def test_ner_possessive_stripped():
    names = extract_proper_nouns("the sword was Li Changshou's. Later Li Changshou spoke.")
    assert "Li Changshou" in names
    assert not any(n.endswith("'s") or n.endswith("’s") for n in names)


@ner
def test_ner_leading_article_trimmed():
    # A leading article is stripped from a span. Use a PERSON name (reliably tagged); the
    # label set is intentionally narrow (PERSON/ORG/GPE/LOC/FAC) so invented place names
    # that NER guesses as WORK_OF_ART are not surfaced — that narrowing is what removes the
    # junk ("Clang", pill phrases) seen on real chapters.
    names = extract_proper_nouns(
        "The Gautama arrived. The Gautama spoke to the council about the Gautama's plan."
    )
    assert any(n == "Gautama" for n in names)
    assert not any(n.lower().startswith("the ") for n in names)


@ner
def test_ner_rejects_quote_and_punctuation_spans():
    # Spans that straddle quotes/sentence boundaries must not surface as garbage names.
    text = 'He shouted, "No... Ah!" Li Changshou ran. Li Changshou ran again to the gate.'
    names = extract_proper_nouns(text)
    assert all('"' not in n and "!" not in n and "…" not in n and "." not in n for n in names)
    # The real recurring name still comes through.
    assert any("Changshou" in n for n in names)


@ner
def test_ner_rejects_lone_interjections():
    text = "Clang! Hmph. Yo, the man said. Hmm, he thought. Li Changshou watched quietly."
    names = extract_proper_nouns(text)
    for junk in ["Clang", "Hmph", "Yo", "Hmm"]:
        assert junk not in names


@ner
def test_ner_rejects_trailing_lowercase_verb():
    # NER sometimes glues a lowercase verb onto a name span ("Li Changshou frowned").
    text = "Li Changshou frowned at the elder. Later Li Changshou frowned again."
    names = extract_proper_nouns(text)
    assert "Li Changshou frowned" not in names
    assert all(all(tok[0].isupper() or tok.lower() in {"of", "the", "and"} for tok in n.split()) for n in names)


@ner
def test_ner_real_person_name_detected():
    text = "Beijing fell silent. Li Changshou traveled to Beijing with Ah Da."
    names = extract_proper_nouns(text)
    assert "Beijing" in names
    assert any("Changshou" in n for n in names)


@ner
def test_ner_empty_and_lowercase():
    assert extract_proper_nouns("") == []
    assert extract_proper_nouns("   ") == []
    assert extract_proper_nouns("the cat sat on the mat quietly") == []


@ner
def test_ner_limit_respected():
    text = " ".join(f"Then {n} arrived in London." for n in
                     ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Grace"])
    assert len(extract_proper_nouns(text, limit=3)) <= 3


# ---------------------------------------------------------------------------
# Fallback layer — deterministic regex, used when the model is absent. Always runs.
# ---------------------------------------------------------------------------

def test_fallback_multi_word_name_kept_whole():
    text = "The disciple bowed. Li Changshou raised his hand as Li Changshou smiled."
    names = _regex_proper_nouns(text)
    assert "Li Changshou" in names
    assert "Li" not in names


def test_fallback_sentence_initial_common_word_filtered():
    text = "Dawn came early. The dawn was cold. Dawn faded."
    assert "Dawn" not in _regex_proper_nouns(text)


def test_fallback_recurring_single_name_kept():
    text = "Fang Yuan walked. Later, Fang spoke. Fang left."
    assert "Fang Yuan" in _regex_proper_nouns(text)


def test_fallback_midsentence_single_capital_kept():
    assert "Changshou" in _regex_proper_nouns("the elder told Changshou to wait.")


def test_fallback_connectives_inside_name_preserved():
    text = "He joined the Sect of the Azure Cloud. The Sect of the Azure Cloud was old."
    assert any("Azure Cloud" in n for n in _regex_proper_nouns(text))


def test_fallback_leading_the_trimmed():
    text = "The Azure Peak loomed. The Azure Peak glowed."
    names = _regex_proper_nouns(text)
    assert "Azure Peak" in names
    assert "The Azure Peak" not in names


def test_fallback_frequency_ordering():
    text = (
        "the elder Jin Guang spoke. then Lin Feng replied to Jin Guang. "
        "later Jin Guang and Lin Feng left."
    )
    names = _regex_proper_nouns(text)
    assert names.index("Jin Guang") < names.index("Lin Feng")


def test_fallback_empty_text():
    assert _regex_proper_nouns("") == []
    assert _regex_proper_nouns("   ") == []


def test_fallback_pure_lowercase_has_no_names():
    assert _regex_proper_nouns("the cat sat on the mat quietly") == []


def test_fallback_limit_respected():
    text = " ".join(f"saw Name{i} there." for i in range(50))
    assert len(_regex_proper_nouns(text, limit=5)) == 5


def test_fallback_possessive_stripped_to_base_name():
    text = "the sword was Li Changshou's. Later Li Changshou spoke."
    names = _regex_proper_nouns(text)
    assert "Li Changshou" in names
    assert not any(n.endswith("'s") or n.endswith("’s") for n in names)
    assert "Li Changshou's" not in names


def test_fallback_trailing_apostrophe_variant_not_separate():
    text = "Big Sister' words. Big Sister's plan. the elder told Big Sister to wait."
    names = _regex_proper_nouns(text)
    assert "Big Sister" in names
    assert "Big Sister'" not in names
    assert "Big Sister's" not in names


def test_fallback_contractions_not_treated_as_names():
    names = _regex_proper_nouns("I'm fine. I'll go. the man watched.")
    assert "I'm" not in names
    assert "I'll" not in names
    assert "I" not in names


def test_fallback_sentence_opener_adverbs_dropped():
    text = "However it rained. Although skies cleared. Unfortunately the road flooded. Everyone left."
    names = _regex_proper_nouns(text)
    for w in ["However", "Although", "Unfortunately", "Everyone"]:
        assert w not in names


def test_fallback_opener_stripped_from_real_name_run():
    text = "Although Li Changshou hesitated, Li Changshou pressed on."
    names = _regex_proper_nouns(text)
    assert "Li Changshou" in names
    assert "Although Li Changshou" not in names
    assert "Although" not in names
