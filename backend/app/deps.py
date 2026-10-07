"""Shared dependency providers (storage + engine).

The engine has two resolution paths:

- ``get_translation_engine`` — the process-wide, env-configured singleton (cached). Used
  as the fallback for the single-user / local-first setup and anywhere a request carries
  no credentials.
- ``resolve_request_engine`` — the per-request path for bring-your-own-key multi-user use.
  It builds a fresh engine from the ``{provider, api_key, model}`` a request supplies and
  maps the factory's credential/provider errors onto HTTP 400/401. Storage stays cached and
  shared; only the engine is per-request.

Security: the API key arrives in the ``X-LLM-Api-Key`` header (kept out of JSON bodies and
request logs), is used only to construct the engine, and is never persisted or echoed.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Header, HTTPException

from app.config import Settings, get_settings
from app.engines.base import TranslationEngine
from app.engines.factory import (
    EngineConfigError,
    EngineCredentialError,
    UnknownProviderError,
    get_engine,
    get_engine_for_request,
)
from app.storage.base import StorageService
from app.storage.sqlite_store import SQLiteStorage


@lru_cache
def get_storage() -> StorageService:
    settings: Settings = get_settings()
    return SQLiteStorage(settings.nb_db_path)


@lru_cache
def get_translation_engine() -> TranslationEngine:
    settings: Settings = get_settings()
    return get_engine(settings)


def get_request_api_key(
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-Api-Key"),
) -> str | None:
    """FastAPI dependency: pull the per-request LLM API key from the request header.

    Returns the raw key (stripped to None when blank). Declared as a dependency so the key
    is extracted uniformly across the engine-calling routes without ever landing in a
    request/response body. Never log this value.
    """
    if x_llm_api_key is None:
        return None
    key = x_llm_api_key.strip()
    return key or None


def resolve_request_engine(
    provider: str | None,
    model: str | None,
    api_key: str | None,
    settings: Settings,
    fallback: TranslationEngine | None = None,
    ollama_base_url: str | None = None,
) -> TranslationEngine:
    """Build the per-request engine, translating factory errors into HTTP responses.

    - unknown provider  → 400
    - cloud provider without a usable key → 401
    - misconfigured server-side engine (e.g. ollama env missing) → 500

    When ``provider`` is omitted this falls back to the env-configured engine, so existing
    single-user clients keep working unchanged. ``fallback`` is the dependency-injected
    env engine (the cached singleton, or a test override) and is reused for the no-provider
    and matching-provider-no-key cases so overrides are honored.

    ``ollama_base_url`` (task 23.5): when the request carries a custom Ollama URL (from the
    user's picker on the hosted app), it overrides the server's OLLAMA_BASE_URL for this
    request only. Ignored for cloud providers.
    """
    try:
        return get_engine_for_request(
            provider, api_key, model, settings,
            fallback=fallback, ollama_base_url=ollama_base_url,
        )
    except UnknownProviderError as exc:
        raise HTTPException(400, str(exc)) from exc
    except EngineCredentialError as exc:
        raise HTTPException(401, str(exc)) from exc
    except EngineConfigError as exc:
        raise HTTPException(500, str(exc)) from exc
