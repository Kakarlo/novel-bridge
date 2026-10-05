"""Tests for deterministic chapter-number extraction (services/chapter_number.py).

Offline, no model needed — pure string parsing.
"""

from __future__ import annotations

import pytest

from app.services.chapter_number import parse_chapter_number


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Chapter 12: Title", 12),
        ("Chapter 12", 12),
        ("chapter 7 - the gate", 7),  # lowercase
        ("CHAPTER 999", 999),
        # The messy real case from the author's screenshot: site chapter number first,
        # a secondary source index second — take the first.
        ("Chapter 1035 - 469: Death and Destruction Bring New Life [Grand Finale]", 1035),
        ("Ch. 7 - Title", 7),
        ("Ch 7", 7),
        ("Ch.7", 7),
        # Decimal / interlude: keep the integer part.
        ("Chapter 12.5 Title", 12),
        # Bare leading number, no keyword.
        ("12. Title", 12),
        ("12 - Title", 12),
        ("1035: a title", 1035),
    ],
)
def test_parses_expected_number(title, expected):
    assert parse_chapter_number(title) == expected


@pytest.mark.parametrize(
    "title",
    [
        "",
        "   ",
        "Prologue",
        "Epilogue",
        "A Title With No Number",
        # A number mid-title (not leading, no keyword) must NOT be mistaken for a chapter.
        "The 300 Spartans",
    ],
)
def test_indeterminate_returns_none(title):
    assert parse_chapter_number(title) is None


@pytest.mark.parametrize(
    "title",
    [
        "Volume 2, Chapter 5",
        "Vol. 2 Ch. 5",
        "Volume 3",
    ],
)
def test_volume_titles_return_none_by_design(title):
    # A single int can't order (volume, chapter); return None so ordering falls back to
    # upload order and the UI can prompt. Documented in the module + VOLUME TODO.
    assert parse_chapter_number(title) is None


def test_similar_words_do_not_false_match():
    # Words that start with "ch" but aren't "chapter" must not trigger the keyword path.
    assert parse_chapter_number("Chart 5 of the Realm") is None
    assert parse_chapter_number("Church bells at 9") is None
