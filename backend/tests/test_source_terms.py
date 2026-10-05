"""Tests for the EXPERIMENTAL zh/ja source-term detector.

Offline-safe: when the zh/ja spaCy models aren't installed, the detector must degrade to
an empty list (never raise). If a model IS present, we assert it finds something.
"""

from __future__ import annotations

import importlib.util

from app.services.source_terms import extract_source_terms


def _model_installed(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def test_empty_and_blank_return_empty():
    assert extract_source_terms("", "zh") == []
    assert extract_source_terms("   ", "zh") == []


def test_unsupported_language_returns_empty():
    # English isn't a source language here (handled by noun_extract); unknown -> empty.
    assert extract_source_terms("some text", "en") == []


def test_missing_model_degrades_gracefully():
    # When the model isn't installed, we get [] rather than an exception.
    if _model_installed("zh_core_web_sm"):
        return  # covered by the live test below
    assert extract_source_terms("林风走向了青云宗。", "zh") == []


def test_zh_detection_when_model_present():
    if not _model_installed("zh_core_web_sm"):
        return  # model not installed; skipped (offline-safe)
    text = "林风走向了北京。北京很大。林风在北京住下。"
    terms = extract_source_terms(text, "zh")
    # Should find at least one multi-char proper noun (e.g. 北京 / 林风).
    assert isinstance(terms, list)
    assert any(len(t) >= 2 for t in terms)
