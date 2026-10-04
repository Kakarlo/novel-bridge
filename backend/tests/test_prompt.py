"""Tests for the restructured prompt builders (task 13).

These lock in the behavior that fixes the reference-echo bug: a strong system
preamble that forbids reproducing the reference, and a user message where the raw
chapter is the final, clearly fenced block.
"""

from __future__ import annotations

from app.engines.base import TranslationRequest
from app.models import GlossaryEntry
from app.services import prompt


def _req(**kw) -> TranslationRequest:
    base = dict(raw_text="RAWBODY", source_lang="zh")
    base.update(kw)
    return TranslationRequest(**base)


def test_system_prompt_forbids_reproducing_reference():
    sp = prompt.build_translation_system_prompt().lower()
    assert "translate only" in sp
    assert "never" in sp and "reproduce" in sp
    assert "reference" in sp


def test_user_message_fences_raw_chapter_last():
    msgs = prompt.build_translation_messages(
        _req(reference_context="Summary: a quiet chapter.")
    )
    user = msgs[1]["content"]
    # Raw chapter is fenced with explicit delimiters...
    assert prompt._RAW_OPEN in user and prompt._RAW_CLOSE in user
    assert "RAWBODY" in user
    # ...and the raw-chapter section is the last thing in the message.
    assert user.rstrip().endswith(prompt._RAW_CLOSE)
    # Reference context is present but labeled as non-translatable background.
    assert "a quiet chapter" in user
    assert "do not translate" in user.lower()


def test_user_message_handles_no_reference():
    msgs = prompt.build_translation_messages(_req(reference_context=""))
    user = msgs[1]["content"]
    assert "none available" in user.lower()


def test_glossary_rendered_when_present():
    g = [GlossaryEntry(id="g1", project_id="p", source_term="林", translation="Lin")]
    msgs = prompt.build_translation_messages(_req(glossary=g))
    assert "林 => Lin" in msgs[1]["content"]


def test_extraction_messages_request_json_summary_and_terms():
    msgs = prompt.build_extraction_messages("some reference text", "ja")
    sys = msgs[0]["content"].lower()
    assert "json" in sys
    assert "summary" in sys and "candidate_terms" in sys
    assert "some reference text" in msgs[1]["content"]


def test_build_messages_alias_still_works():
    # Backwards-compatible alias used by older imports.
    msgs = prompt.build_messages(_req())
    assert msgs[0]["role"] == "system"
