"""Tests for the translation engines and factory."""

from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.engines.base import TranslationRequest
from app.engines.factory import EngineConfigError, get_engine
from app.engines.mock_engine import MockEngine
from app.engines.ollama_engine import OllamaEngine
from app.models import GlossaryEntry


def _glossary(pid: str = "p1") -> list[GlossaryEntry]:
    return [GlossaryEntry(id="g1", project_id=pid, source_term="林", translation="Lin")]


async def _collect(engine, req):
    chunks = []
    async for c in engine.stream(req):
        chunks.append(c)
    return chunks


async def test_mock_engine_deterministic_and_substitutes():
    engine = MockEngine()
    req = TranslationRequest(raw_text="我是林", source_lang="zh", glossary=_glossary())
    out1 = "".join(c.content for c in await _collect(engine, req))
    out2 = "".join(c.content for c in await _collect(engine, req))
    assert out1 == out2  # deterministic
    assert out1.startswith("[MOCK]")  # marker
    assert "我是Lin" in out1  # glossary substitution applied
    chunks = await _collect(engine, req)
    assert chunks[-1].done is True


async def test_mock_engine_no_glossary():
    engine = MockEngine()
    req = TranslationRequest(raw_text="hello", source_lang="ja")
    out = "".join(c.content for c in await _collect(engine, req))
    assert "[MOCK]" in out
    assert "hello" in out


async def test_ollama_engine_parses_ndjson_and_strips_think():
    # Simulated Ollama NDJSON stream with a <think> block that must be stripped.
    lines = [
        {"message": {"content": "<think>reasoning"}, "done": False},
        {"message": {"content": " here</think>Hello"}, "done": False},
        {"message": {"content": " world"}, "done": False},
        {"message": {"content": ""}, "done": True, "eval_count": 3, "total_duration": 1},
    ]
    body = "\n".join(json.dumps(x) for x in lines).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert payload["think"] is False
        assert payload["options"]["num_ctx"] == 16384
        return httpx.Response(200, content=body)

    transport = httpx.MockTransport(handler)

    engine = OllamaEngine(base_url="http://x:11434", model="qwen3.5:0.8b")

    # Patch the client used inside stream() to use our mock transport.
    import app.engines.ollama_engine as oe

    orig = oe.httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return orig(transport=transport, **kwargs)

    oe.httpx.AsyncClient = client_factory  # type: ignore[assignment]
    try:
        req = TranslationRequest(raw_text="你好", source_lang="zh")
        chunks = await _collect(engine, req)
    finally:
        oe.httpx.AsyncClient = orig  # type: ignore[assignment]

    text = "".join(c.content for c in chunks)
    assert "reasoning" not in text  # think content stripped
    assert "Hello world" in text
    assert chunks[-1].done is True
    assert chunks[-1].meta and chunks[-1].meta["eval_count"] == 3


async def test_mock_engine_extract_reference_deterministic():
    engine = MockEngine()
    content = "Lin Feng climbed Azure Peak. The Sect Elders watched. Dawn broke slowly."
    r1 = await engine.extract_reference(content, "zh")
    r2 = await engine.extract_reference(content, "zh")
    assert r1.summary == r2.summary  # deterministic
    assert r1.candidate_terms == r2.candidate_terms
    assert r1.summary.startswith("[MOCK-SUMMARY]")
    # Capitalized words become candidate terms.
    assert "Lin" in r1.candidate_terms and "Azure" in r1.candidate_terms


def test_parse_extraction_strict_json():
    from app.engines.ollama_engine import _parse_extraction

    out = _parse_extraction('{"summary": "A calm chapter.", "candidate_terms": ["Lin", "Lin", "Peak"]}')
    assert out.summary == "A calm chapter."
    assert out.candidate_terms == ["Lin", "Peak"]  # de-duplicated, order kept


def test_parse_extraction_embedded_json():
    from app.engines.ollama_engine import _parse_extraction

    noisy = 'Here is the result:\n{"summary": "X", "candidate_terms": []}\nThanks!'
    out = _parse_extraction(noisy)
    assert out.summary == "X"
    assert out.candidate_terms == []


def test_parse_extraction_non_json_fallback():
    from app.engines.ollama_engine import _parse_extraction

    out = _parse_extraction("the model just wrote prose, no json here")
    assert out.summary.startswith("the model just wrote prose")
    assert out.candidate_terms == []


def test_factory_selects_mock():
    s = Settings(nb_engine="mock")
    assert isinstance(get_engine(s), MockEngine)


def test_factory_selects_ollama():
    s = Settings(nb_engine="ollama", ollama_base_url="http://x:11434", ollama_model="m")
    assert isinstance(get_engine(s), OllamaEngine)


def test_factory_rejects_unknown():
    s = Settings(nb_engine="bogus")
    with pytest.raises(EngineConfigError):
        get_engine(s)


def test_factory_rejects_missing_ollama_config():
    s = Settings(nb_engine="ollama", ollama_base_url="", ollama_model="m")
    with pytest.raises(EngineConfigError):
        get_engine(s)
