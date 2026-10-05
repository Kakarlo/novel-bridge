"""Tests for the context builder token-budgeting strategy (task 13 revision).

References now contribute DERIVED context (summary + candidate terms) rather than raw
chapter text, which is what fixes the reference-echo bug. These tests assert the derived
context is assembled, budgeted, and truncated correctly.
"""

from __future__ import annotations

from app.models import GlossaryEntry, ReferenceChapter
from app.services import context_builder as cb


def _ref(
    summary: str = "",
    terms: list[str] | None = None,
    title: str = "Ch",
    content: str = "raw reference body that must never be fed to the model",
    chapter_number: int | None = None,
) -> ReferenceChapter:
    return ReferenceChapter(
        id="r",
        project_id="p",
        title=title,
        content=content,
        created_at="now",
        chapter_number=chapter_number,
        summary=summary or None,
        candidate_terms=terms or [],
    )


def test_no_references_returns_empty_not_truncated():
    out = cb.build([], [], "raw", budget_tokens=10_000)
    assert out.reference_context == ""
    assert out.truncated is False


def test_reference_without_summary_contributes_nothing():
    # A reference that hasn't been summarized yet is skipped (not raw-dumped), and
    # since it carries no usable derived content, that is not a truncation.
    ref = _ref(summary="", terms=[])
    out = cb.build([], [ref], "raw", budget_tokens=10_000)
    assert out.reference_context == ""
    assert out.truncated is False


def test_raw_content_is_never_included():
    secret = "ECHO_BAIT_RAW_TEXT"
    ref = _ref(summary="A calm chapter.", content=secret)
    out = cb.build([], [ref], "raw", budget_tokens=10_000)
    assert secret not in out.reference_context
    assert "A calm chapter." in out.reference_context


def test_summary_and_terms_included():
    ref = _ref(summary="Hero climbs a mountain.", terms=["Lin Feng", "Azure Peak"])
    out = cb.build([], [ref], "raw", budget_tokens=10_000)
    assert "Hero climbs a mountain." in out.reference_context
    assert "Lin Feng" in out.reference_context
    assert "Azure Peak" in out.reference_context
    assert out.truncated is False


def test_newest_references_first():
    old = _ref(summary="OLD summary", title="Ch1")
    new = _ref(summary="NEW summary", title="Ch2")
    out = cb.build([], [old, new], "raw", budget_tokens=10_000)
    # Both fit; newest is listed first.
    assert out.reference_context.index("NEW summary") < out.reference_context.index(
        "OLD summary"
    )
    assert out.truncated is False


def test_chapter_number_orders_newest_first_regardless_of_upload_order():
    # Uploaded out of chapter order: ch2 first, then ch1, then ch3. Ordering must use the
    # chapter number (newest=highest first: 3,2,1), NOT the upload/list order.
    ch2 = _ref(summary="SUMMARY_TWO", title="Chapter 2", chapter_number=2)
    ch1 = _ref(summary="SUMMARY_ONE", title="Chapter 1", chapter_number=1)
    ch3 = _ref(summary="SUMMARY_THREE", title="Chapter 3", chapter_number=3)
    out = cb.build([], [ch2, ch1, ch3], "raw", budget_tokens=10_000)
    ctx = out.reference_context
    assert ctx.index("SUMMARY_THREE") < ctx.index("SUMMARY_TWO") < ctx.index("SUMMARY_ONE")


def test_numbered_chapters_precede_unnumbered():
    # A numbered chapter is a stronger recency signal than an unnumbered one, so numbered
    # chapters come first; unnumbered (e.g. a prologue/volume title) trail.
    numbered = _ref(summary="NUMBERED", title="Chapter 5", chapter_number=5)
    unnumbered = _ref(summary="UNNUMBERED", title="Prologue", chapter_number=None)
    out = cb.build([], [unnumbered, numbered], "raw", budget_tokens=10_000)
    ctx = out.reference_context
    assert ctx.index("NUMBERED") < ctx.index("UNNUMBERED")


def test_unnumbered_fall_back_to_reverse_upload_order():
    # With no chapter numbers at all, behavior matches the old newest-upload-first: the last
    # item in the (created_at ASC) list is surfaced first.
    first_up = _ref(summary="FIRST_UP", title="A", chapter_number=None)
    last_up = _ref(summary="LAST_UP", title="B", chapter_number=None)
    out = cb.build([], [first_up, last_up], "raw", budget_tokens=10_000)
    ctx = out.reference_context
    assert ctx.index("LAST_UP") < ctx.index("FIRST_UP")


def test_oldest_summaries_dropped_when_budget_tight():
    old = _ref(summary="O" * 600, title="Ch1")
    new = _ref(summary="N" * 300, title="Ch2")
    # ~300 tokens of room: enough for the newest summary (~130 tokens of chars) but
    # not both. Reserves are zeroed to isolate the reference-budget behavior.
    out = cb.build(
        [],
        [old, new],
        "raw",
        budget_tokens=300,
        system_prompt_tokens=0,
        reply_headroom_tokens=0,
    )
    assert "N" * 300 in out.reference_context  # newest kept
    assert "O" * 600 not in out.reference_context  # oldest dropped
    assert out.truncated is True


def test_single_oversized_summary_truncated_with_note():
    huge = _ref(summary="Z" * 9000, title="Ch1")
    out = cb.build(
        [],
        [huge],
        "raw",
        budget_tokens=600,
        system_prompt_tokens=0,
        reply_headroom_tokens=0,
    )
    assert out.truncated is True
    assert out.reference_context.startswith("[earlier reference summaries omitted")


def test_glossary_and_raw_reduce_remaining_budget():
    glossary = [
        GlossaryEntry(
            id=f"g{i}", project_id="p", surface_form="y" * 30, source_term="x" * 30,
            status="approved",
        )
        for i in range(5)
    ]
    ref = _ref(summary="Z" * 6000, title="Ch1")
    big_raw = "R" * 3000
    out = cb.build(glossary, [ref], big_raw, budget_tokens=2000)
    # Reserved budget (glossary + raw + overhead) leaves no room for the summary.
    assert out.truncated is True


def test_estimate_tokens_monotonic():
    assert cb.estimate_tokens("") == 0
    assert cb.estimate_tokens("abc") >= 1
    assert cb.estimate_tokens("a" * 300) > cb.estimate_tokens("a" * 30)
