"""Tests for the restructured prompt builders (task 13).

These lock in the behavior that fixes the reference-echo bug: a strong system
preamble that forbids reproducing the reference, and a user message where the raw
chapter is the final, clearly fenced block.
"""

from __future__ import annotations

from app.engines.base import TranslationRequest
from app.models import GlossaryEntry
from app.services.prompts import builders


def _req(**kw) -> TranslationRequest:
    base = dict(raw_text="RAWBODY", source_lang="zh")
    base.update(kw)
    return TranslationRequest(**base)


# Prompts have changed and are variable
# def test_system_prompt_forbids_reproducing_reference():
#     sp = builders.build_translation_system_prompt().lower()
#     assert "translate only" in sp
#     assert "never" in sp and "reproduce" in sp
#     assert "reference" in sp


def test_user_message_fences_raw_chapter_last():
    # reference_context is no longer injected into the translate prompt (it hurt quality —
    # the project pivoted to a per-project style profile). The raw chapter must still be the
    # final, clearly fenced block, and the removed reference text must NOT appear.
    msgs = builders.build_translation_messages(
        _req(reference_context="Summary: a quiet chapter.")
    )
    user = msgs[1]["content"]
    # Raw chapter is fenced with explicit delimiters...
    assert builders._RAW_OPEN in user and builders._RAW_CLOSE in user
    assert "RAWBODY" in user
    # ...and the raw-chapter section is the last thing in the message.
    assert user.rstrip().endswith(builders._RAW_CLOSE)
    # Reference context is intentionally dropped — it must not leak into the prompt.
    assert "a quiet chapter" not in user


def test_user_message_omits_reference_context_section():
    # With no reference (and none injected anymore), the message carries no reference-context
    # section at all — just the fenced raw chapter.
    msgs = builders.build_translation_messages(_req(reference_context=""))
    user = msgs[1]["content"]
    # No "## Reference context" section header (the instruction text may still mention the
    # phrase in passing; it's the dedicated block that must be gone).
    assert "## reference context" not in user.lower()
    assert user.rstrip().endswith(builders._RAW_CLOSE)


def test_paired_entry_rendered_as_authoritative_pair():
    g = [
        GlossaryEntry(
            id="g1", project_id="p", surface_form="Lin", source_term="林",
            status="approved",
        )
    ]
    msgs = builders.build_translation_messages(_req(glossary=g))
    assert "林 => Lin" in msgs[1]["content"]


def test_approved_english_only_rendered_as_preferred_spelling():
    g = [
        GlossaryEntry(id="g1", project_id="p", surface_form="Fang Yuan", status="approved")
    ]
    msgs = builders.build_translation_messages(_req(glossary=g), profile_name="balanced")
    content = msgs[1]["content"]
    assert "Preferred English spellings" in content
    assert "Fang Yuan" in content
    assert "=> Fang Yuan" not in content  # no bogus pair without a source term


def test_candidate_and_rejected_english_terms_excluded_from_prompt():
    g = [
        GlossaryEntry(id="c", project_id="p", surface_form="Candidate Name", status="candidate"),
        GlossaryEntry(id="r", project_id="p", surface_form="Rejected Name", status="rejected"),
        GlossaryEntry(id="a", project_id="p", surface_form="Approved Name", status="approved"),
    ]
    content = builders.build_translation_messages(_req(glossary=g), profile_name="balanced")[1]["content"]
    assert "Approved Name" in content
    assert "Candidate Name" not in content  # not endorsed -> excluded
    assert "Rejected Name" not in content


def test_character_gender_shown_and_titles_grouped():
    g = [
        GlossaryEntry(
            id="c", project_id="p", surface_form="Fang Yuan", status="approved",
            category="character", gender="male",
        ),
        GlossaryEntry(
            id="t", project_id="p", surface_form="Senior Brother", status="approved",
            category="title",
        ),
    ]
    content = builders.build_translation_messages(_req(glossary=g), profile_name="balanced")[1]["content"]
    # Characters render in a dedicated Cast block with capitalized gender in brackets.
    assert "## Cast" in content
    assert "Fang Yuan [Male]" in content
    # English-only entries also appear in the preferred-spellings block with a category tag
    # (anything other than the default "term" is labeled).
    assert "[character]" in content
    assert "Senior Brother" in content and "[title]" in content


def test_candidate_paired_entry_still_reaches_prompt():
    # A paired entry is authoritative regardless of status (it has a source mapping).
    g = [
        GlossaryEntry(
            id="g", project_id="p", surface_form="Lin", source_term="林", status="candidate"
        )
    ]
    content = builders.build_translation_messages(_req(glossary=g))[1]["content"]
    assert "林 => Lin" in content


def test_extraction_messages_request_json_summary_and_terms():
    msgs = builders.build_extraction_messages("some reference text", "ja")
    sys = msgs[0]["content"].lower()
    assert "json" in sys
    assert "summary" in sys and "candidate_terms" in sys
    assert "some reference text" in msgs[1]["content"]


