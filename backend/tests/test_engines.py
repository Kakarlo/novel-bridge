"""Tests for the translation engines and factory."""

from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.engines.base import TranslationRequest
from app.engines.factory import EngineConfigError, get_engine
from app.engines.mock_engine import MockEngine
from app.engines.ollama_engine import OllamaEngine, _parse_glossary_pairs
from app.models import GlossaryEntry


def _glossary(pid: str = "p1") -> list[GlossaryEntry]:
    return [
        GlossaryEntry(
            id="g1", project_id=pid, surface_form="Lin", source_term="林",
            status="approved",
        )
    ]


async def _collect(engine, req):
    chunks = []
    async for c in engine.stream(req):
        chunks.append(c)
    return chunks


async def test_mock_engine_deterministic_and_substitutes():
    engine = MockEngine()
    req = TranslationRequest(source_text="我是林", source_lang="zh", glossary=_glossary())
    out1 = "".join(c.content for c in await _collect(engine, req))
    out2 = "".join(c.content for c in await _collect(engine, req))
    assert out1 == out2  # deterministic
    assert out1.startswith("[MOCK]")  # marker
    assert "我是Lin" in out1  # glossary substitution applied
    chunks = await _collect(engine, req)
    assert chunks[-1].done is True


async def test_mock_engine_no_glossary():
    engine = MockEngine()
    req = TranslationRequest(source_text="hello", source_lang="ja")
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
        req = TranslationRequest(source_text="你好", source_lang="zh")
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


async def test_mock_engine_list_models():
    assert await MockEngine().list_models() == ["mock"]


async def test_mock_engine_extract_glossary():
    """Mock extract_glossary pairs candidate source terms to English words in the output."""
    engine = MockEngine()
    raw = "林尘走进大厅。苏青点头。林尘微笑。"
    output = "Lin Chen walked in. Su Qing nodded. Lin Chen smiled."
    pairs = await engine.extract_glossary(
        raw, output, "zh", candidates=["林尘", "苏青"]
    )
    assert len(pairs) == 2
    # Each pair has a source_term from the candidates and a surface_form from the output.
    assert all(p.source_term for p in pairs)
    assert all(p.surface_form for p in pairs)
    # Deterministic: same inputs → same outputs.
    pairs2 = await engine.extract_glossary(raw, output, "zh", candidates=["林尘", "苏青"])
    assert [(p.source_term, p.surface_form) for p in pairs] == \
           [(p.source_term, p.surface_form) for p in pairs2]


async def test_mock_engine_extract_glossary_no_candidates():
    """With no candidates, mock returns empty (nothing to pair)."""
    engine = MockEngine()
    assert await engine.extract_glossary("text", "Text output", "zh") == []


def test_parse_glossary_pairs_valid():
    raw = (
        '{"pairs": [{"source_term": "林尘", "surface_form": "Lin Chen", '
        '"category": "character", "gender": "male", "note": "protagonist"}]}'
    )
    pairs = _parse_glossary_pairs(raw)
    assert len(pairs) == 1
    p = pairs[0]
    assert p.source_term == "林尘"
    assert p.surface_form == "Lin Chen"
    assert p.category == "character"
    assert p.gender == "male"
    assert p.note == "protagonist"


def test_parse_glossary_pairs_embedded_json_and_defaults():
    # JSON embedded in prose; missing/invalid category+gender default sanely.
    raw = (
        'Here you go:\n{"pairs": [{"source_term": "苏青", "surface_form": "Su Qing", '
        '"category": "bogus", "gender": "unknown"}]}\nDone.'
    )
    pairs = _parse_glossary_pairs(raw)
    assert len(pairs) == 1
    assert pairs[0].category == "term"  # invalid category falls back
    assert pairs[0].gender is None  # "unknown" normalized to None


def test_parse_glossary_pairs_drops_incomplete_and_dedupes():
    raw = (
        '{"pairs": ['
        '{"source_term": "", "surface_form": "X"},'          # no source_term -> dropped
        '{"source_term": "A", "surface_form": ""},'          # no surface_form -> dropped
        '{"source_term": "林", "surface_form": "Lin"},'
        '{"source_term": "林", "surface_form": "lin"}'        # dup (case-insensitive) -> dropped
        ']}'
    )
    pairs = _parse_glossary_pairs(raw)
    assert len(pairs) == 1
    assert pairs[0].source_term == "林"


def test_parse_glossary_pairs_garbage_returns_empty():
    assert _parse_glossary_pairs("not json at all") == []
    assert _parse_glossary_pairs("") == []
    assert _parse_glossary_pairs('{"wrong_key": []}') == []


async def test_ollama_list_models_parses_tags():
    # Mock Ollama's GET /api/tags response; names come back sorted, blanks dropped.
    body = json.dumps(
        {"models": [{"name": "qwen3.5:4b"}, {"name": "qwen3.5:0.8b"}, {"name": ""}, {}]}
    ).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, content=body)

    transport = httpx.MockTransport(handler)
    engine = OllamaEngine(base_url="http://x:11434", model="qwen3.5:0.8b")

    import app.engines.ollama_engine as oe

    orig = oe.httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return orig(transport=transport, **kwargs)

    oe.httpx.AsyncClient = client_factory  # type: ignore[assignment]
    try:
        models = await engine.list_models()
    finally:
        oe.httpx.AsyncClient = orig  # type: ignore[assignment]
    assert models == ["qwen3.5:0.8b", "qwen3.5:4b"]  # sorted, "" and {} dropped


async def test_ollama_list_models_unreachable_returns_empty():
    engine = OllamaEngine(base_url="http://127.0.0.1:1", model="m")  # nothing listening

    import app.engines.ollama_engine as oe

    orig = oe.httpx.AsyncClient

    def failing(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    def client_factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return orig(transport=httpx.MockTransport(failing), **kwargs)

    oe.httpx.AsyncClient = client_factory  # type: ignore[assignment]
    try:
        assert await engine.list_models() == []  # degrades, never raises
    finally:
        oe.httpx.AsyncClient = orig  # type: ignore[assignment]


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


# ---------------------------------------------------------------------------
# Cloud engines: OpenRouter + Gemini (factory wiring, config validation, offline
# degradation, and Gemini's message-format conversion). No network — the HTTP paths
# are not exercised here; health/list_models degrade to False/[] without a key.
# ---------------------------------------------------------------------------

from app.engines.gemini_engine import GeminiEngine, _to_gemini_messages
from app.engines.openrouter_engine import OpenRouterEngine


def test_factory_selects_openrouter():
    s = Settings(nb_engine="openrouter", openrouter_api_key="sk-test")
    engine = get_engine(s)
    assert isinstance(engine, OpenRouterEngine)
    assert engine.name == "openrouter"


def test_factory_rejects_openrouter_without_key():
    s = Settings(nb_engine="openrouter", openrouter_api_key="")
    with pytest.raises(EngineConfigError):
        get_engine(s)


def test_factory_selects_gemini():
    s = Settings(nb_engine="gemini", gemini_api_key="g-test")
    engine = get_engine(s)
    assert isinstance(engine, GeminiEngine)
    assert engine.name == "gemini"


def test_factory_rejects_gemini_without_key():
    s = Settings(nb_engine="gemini", gemini_api_key="")
    with pytest.raises(EngineConfigError):
        get_engine(s)


async def test_cloud_engines_degrade_without_key():
    # health() is False and list_models() is [] when no key is set — never raises.
    for engine in (OpenRouterEngine(api_key=""), GeminiEngine(api_key="")):
        assert await engine.health() is False
        assert await engine.list_models() == []


def test_gemini_message_conversion_system_and_roles():
    # "system" → system_instruction; "assistant" → "model"; "user" stays "user".
    messages = [
        {"role": "system", "content": "You translate."},
        {"role": "user", "content": "Translate this."},
        {"role": "assistant", "content": "Prior output."},
    ]
    sys_inst, contents = _to_gemini_messages(messages)
    assert sys_inst == {"parts": [{"text": "You translate."}]}
    assert contents[0] == {"role": "user", "parts": [{"text": "Translate this."}]}
    assert contents[1] == {"role": "model", "parts": [{"text": "Prior output."}]}


def test_gemini_message_conversion_merges_consecutive_same_role():
    # Gemini rejects consecutive same-role messages; they must be merged into one.
    messages = [
        {"role": "user", "content": "A"},
        {"role": "user", "content": "B"},
    ]
    sys_inst, contents = _to_gemini_messages(messages)
    assert sys_inst is None
    assert len(contents) == 1
    assert contents[0]["parts"] == [{"text": "A"}, {"text": "B"}]


def test_gemini_extract_text():
    obj = {"candidates": [{"content": {"parts": [{"text": "Hello "}, {"text": "world"}]}}]}
    assert GeminiEngine._extract_text(obj) == "Hello world"
    assert GeminiEngine._extract_text({"candidates": []}) == ""
    assert GeminiEngine._extract_text({}) == ""


def test_default_model_per_engine():
    # /api/health + /api/models report the right `current` per engine.
    from app.main import _default_model

    assert _default_model(Settings(nb_engine="ollama", ollama_model="qwen3.5:4b")) == "qwen3.5:4b"
    assert _default_model(Settings(nb_engine="openrouter", openrouter_model="openrouter/free")) == "openrouter/free"
    assert _default_model(Settings(nb_engine="gemini", gemini_model="gemini-3.5-flash-lite")) == "gemini-3.5-flash-lite"
    assert _default_model(Settings(nb_engine="mock")) == "mock"
