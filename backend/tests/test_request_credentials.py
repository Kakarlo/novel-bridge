"""Per-request bring-your-own-key engine resolution (multi-user path).

Offline-only: everything runs against the mock engine and the stub cloud engines are never
actually called over the network — we only assert that the FACTORY builds the right engine
type from request credentials, and that the ROUTES map credential/provider errors onto the
right HTTP status. No key value is ever persisted or echoed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.deps import get_storage, get_translation_engine
from app.engines.base import TranslationEngine
from app.engines.factory import (
    EngineCredentialError,
    UnknownProviderError,
    get_engine_for_request,
)
from app.engines.mock_engine import MockEngine
from app.main import create_app
from app.storage.sqlite_store import SQLiteStorage


# --- factory unit tests -----------------------------------------------------


def _ollama_settings() -> Settings:
    # A server configured for local Ollama (the common single-user default). No cloud keys.
    return Settings(nb_engine="ollama", openrouter_api_key="", gemini_api_key="")


def test_no_provider_falls_back_to_env_engine():
    """Omitting the provider reuses the env/injected engine (single-user unchanged)."""
    fallback = MockEngine()
    engine = get_engine_for_request(
        provider=None, api_key=None, model=None,
        settings=_ollama_settings(), fallback=fallback,
    )
    assert engine is fallback


def test_matching_local_provider_no_key_reuses_fallback():
    """Naming the configured local engine without a key reuses the fallback (no key needed)."""
    fallback = MockEngine()
    engine = get_engine_for_request(
        provider="mock", api_key=None, model=None,
        settings=Settings(nb_engine="mock"), fallback=fallback,
    )
    assert engine is fallback


def test_ollama_needs_no_key():
    """Ollama is local — it builds with no API key."""
    engine = get_engine_for_request(
        provider="ollama", api_key=None, model="qwen3.5:4b",
        settings=_ollama_settings(), fallback=None,
    )
    assert engine.name == "ollama"


def test_cloud_provider_with_request_key_builds_fresh_engine():
    """A cloud provider + request key builds that provider's engine from the request creds."""
    engine = get_engine_for_request(
        provider="openrouter", api_key="sk-user-123", model=None,
        settings=_ollama_settings(), fallback=MockEngine(),
    )
    assert engine.name == "openrouter"
    # The request key is what the engine was constructed with (not an env key, which is empty).
    assert engine._api_key == "sk-user-123"


def test_cloud_provider_without_key_raises_credential_error():
    """A cloud provider with no request key and no matching env key is a 401-class error."""
    with pytest.raises(EngineCredentialError):
        get_engine_for_request(
            provider="gemini", api_key=None, model=None,
            settings=_ollama_settings(), fallback=MockEngine(),
        )


def test_cloud_provider_falls_back_to_env_key_when_configured():
    """When the server is configured for the SAME cloud provider, its env key is the fallback."""
    settings = Settings(nb_engine="openrouter", openrouter_api_key="env-key-xyz")
    engine = get_engine_for_request(
        provider="openrouter", api_key=None, model=None,
        settings=settings, fallback=None,
    )
    assert engine.name == "openrouter"
    assert engine._api_key == "env-key-xyz"


def test_unknown_provider_raises():
    with pytest.raises(UnknownProviderError):
        get_engine_for_request(
            provider="definitely-not-a-provider", api_key="x", model=None,
            settings=_ollama_settings(), fallback=MockEngine(),
        )


# --- route-level tests (mock engine, offline) -------------------------------


@pytest.fixture()
def client(tmp_path):
    # Server configured for mock, so cloud providers legitimately have no env key —
    # exactly the multi-user case where the key must come from the request.
    settings = Settings(nb_engine="mock", nb_db_path=str(tmp_path / "creds.db"))
    app = create_app(settings)
    store = SQLiteStorage(settings.nb_db_path)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_storage] = lambda: store
    app.dependency_overrides[get_translation_engine] = lambda: MockEngine()
    with TestClient(app) as c:
        yield c


def _create_project(client, name="S", lang="zh"):
    r = client.post("/api/projects", json={"name": name, "source_lang": lang})
    assert r.status_code == 201
    return r.json()["id"]


def _collect_sse(resp) -> list[dict]:
    import json
    events: list[dict] = []
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


def test_translate_no_selection_uses_fallback(client):
    """No selection → the injected mock engine translates (backward compatible)."""
    pid = _create_project(client)
    r = client.post(
        f"/api/projects/{pid}/translate",
        json={"raw_text": "你好", "source_lang": "zh"},
    )
    assert r.status_code == 200
    events = _collect_sse(r)
    assert any(e.get("done") for e in events)


def test_translate_unknown_provider_400(client):
    pid = _create_project(client)
    r = client.post(
        f"/api/projects/{pid}/translate",
        json={
            "raw_text": "你好",
            "source_lang": "zh",
            "selection": {"provider": "bogus"},
        },
    )
    assert r.status_code == 400


def test_translate_cloud_provider_without_key_401(client):
    """Requesting a cloud provider with no key (server has none either) is a 401."""
    pid = _create_project(client)
    r = client.post(
        f"/api/projects/{pid}/translate",
        json={
            "raw_text": "你好",
            "source_lang": "zh",
            "selection": {"provider": "openrouter"},
        },
    )
    assert r.status_code == 401
    # The error message must not echo any key value (there is none, but guard the shape).
    assert "api key" in r.json()["detail"].lower()


def test_translate_mock_provider_no_key_ok(client):
    """Explicitly naming the local provider needs no key and still streams."""
    pid = _create_project(client)
    r = client.post(
        f"/api/projects/{pid}/translate",
        json={
            "raw_text": "你好",
            "source_lang": "zh",
            "selection": {"provider": "mock"},
        },
    )
    assert r.status_code == 200
    assert any(e.get("done") for e in _collect_sse(r))


def test_health_unknown_provider_400(client):
    assert client.get("/api/health", params={"provider": "bogus"}).status_code == 400


def test_health_cloud_provider_with_header_key_probed(client, monkeypatch):
    """A cloud provider + a key via the X-LLM-Api-Key header resolves and probes (reachable
    may be False offline, but it must NOT 401 since a key was supplied).

    The real engine's health() would hit the network; stub it so the suite stays offline.
    """
    from app.engines.openrouter_engine import OpenRouterEngine

    async def _fake_health(self) -> bool:
        return True

    monkeypatch.setattr(OpenRouterEngine, "health", _fake_health)
    r = client.get(
        "/api/health",
        params={"provider": "openrouter"},
        headers={"X-LLM-Api-Key": "sk-user-abc"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["engine"] == "openrouter"
    assert body["reachable"] is True
    # No key value leaks into the health payload.
    assert "sk-user-abc" not in str(body)


def test_health_cloud_provider_without_key_401(client):
    r = client.get("/api/health", params={"provider": "gemini"})
    assert r.status_code == 401


def test_models_cred_aware_current_reflects_provider(client, monkeypatch):
    """/api/models honors the provider: `current` reflects that provider's default model."""
    from app.engines.openrouter_engine import OpenRouterEngine

    async def _fake_list(self) -> list[str]:
        return ["deepseek/deepseek-chat"]

    monkeypatch.setattr(OpenRouterEngine, "list_models", _fake_list)
    r = client.get(
        "/api/models",
        params={"provider": "openrouter"},
        headers={"X-LLM-Api-Key": "sk-user-abc"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["current"] == Settings().openrouter_model
    assert body["models"] == ["deepseek/deepseek-chat"]


def test_models_no_provider_lists_fallback(client):
    """No creds → lists the server's configured (mock) engine."""
    r = client.get("/api/models")
    assert r.status_code == 200
    assert r.json()["models"] == ["mock"]
