"""Tests for the context builder token-budgeting strategy."""

from __future__ import annotations

from app.models import GlossaryEntry, ReferenceChapter
from app.services import context_builder as cb


def _ref(content: str) -> ReferenceChapter:
    return ReferenceChapter(
        id="r", project_id="p", title="t", content=content, created_at="now"
    )


def test_no_references_returns_empty_not_truncated():
    out = cb.build([], [], "raw", budget_tokens=10_000)
    assert out.reference_context == ""
    assert out.truncated is False


def test_short_reference_included_whole():
    ref = _ref("short reference text")
    out = cb.build([], [ref], "raw", budget_tokens=10_000)
    assert out.reference_context == "short reference text"
    assert out.truncated is False


def test_long_reference_truncated_from_start_with_note():
    long_text = "A" * 9000 + "ENDMARKER"
    ref = _ref(long_text)
    # Small budget forces truncation.
    out = cb.build([], [ref], "raw", budget_tokens=1500)
    assert out.truncated is True
    assert out.reference_context.startswith("[earlier reference omitted")
    # The tail (most recent) is kept, so the end marker survives.
    assert out.reference_context.endswith("ENDMARKER")
    assert "[earlier reference omitted" in out.reference_context


def test_latest_reference_is_used():
    out = cb.build(
        [],
        [_ref("old chapter"), _ref("newest chapter")],
        "raw",
        budget_tokens=10_000,
    )
    assert out.reference_context == "newest chapter"


def test_glossary_and_raw_reduce_remaining_budget():
    glossary = [
        GlossaryEntry(id=f"g{i}", project_id="p", source_term="x" * 30, translation="y" * 30)
        for i in range(5)
    ]
    ref = _ref("Z" * 6000)
    big_raw = "R" * 3000
    out = cb.build(glossary, [ref], big_raw, budget_tokens=2000)
    # Reserved budget (glossary + raw + overhead) should force truncation here.
    assert out.truncated is True


def test_estimate_tokens_monotonic():
    assert cb.estimate_tokens("") == 0
    assert cb.estimate_tokens("abc") >= 1
    assert cb.estimate_tokens("a" * 300) > cb.estimate_tokens("a" * 30)
