"""Engine selection and startup validation.

## How to add a new engine
## -----------------------------------------------------------------------
## 1. Create `engines/<name>_engine.py` implementing `TranslationEngine`.
##    See `openrouter_engine.py` (OpenAI-compatible) or `gemini_engine.py`
##    (custom API) as templates — they're heavily commented.
## 2. Add config keys in `config.py` (API key, model, base URL).
## 3. Add a branch in `get_engine()` below, following the existing pattern.
## 4. Update `.env.example` with the new keys.
## 5. Add the engine name to the error message's "Expected" list.
##
## Conventions:
## - Each engine's `name` attribute matches the NB_ENGINE value (lowercase).
## - The API key is validated at startup (fail-fast, not at first request).
## - Non-streaming helpers reuse the Ollama parsers (_parse_extraction,
##   _parse_glossary_pairs) so JSON parsing is consistent across engines.
## - The engine singleton is cached by deps.py (lru_cache on get_translation_engine).
"""

from __future__ import annotations

from app.config import Settings
from app.engines.base import TranslationEngine
from app.engines.mock_engine import MockEngine
from app.engines.ollama_engine import OllamaEngine


class EngineConfigError(RuntimeError):
    """Raised at startup when the selected engine is misconfigured."""


class EngineCredentialError(RuntimeError):
    """Raised per-request when a cloud provider is requested without a usable key.

    Distinct from EngineConfigError (a startup/config problem). This is a 401-class
    situation: the server is fine, the *request* didn't carry the credential a cloud
    provider needs. Route handlers translate this into HTTP 401.
    """


class UnknownProviderError(RuntimeError):
    """Raised per-request when the requested provider name isn't one we support.

    Route handlers translate this into HTTP 400 (the client asked for something that
    doesn't exist, as opposed to a missing credential).
    """


# Providers that are cloud/hosted and therefore REQUIRE an API key. mock/ollama are
# local and need none. Kept here so the per-request resolver and the routes agree on
# what "needs a key" means without duplicating the list.
CLOUD_PROVIDERS = frozenset({"openrouter", "gemini"})
KNOWN_PROVIDERS = frozenset({"mock", "ollama"}) | CLOUD_PROVIDERS


def get_engine_for_request(
    provider: str | None,
    api_key: str | None,
    model: str | None,
    settings: Settings,
    fallback: TranslationEngine | None = None,
) -> TranslationEngine:
    """Resolve the engine for a SINGLE request from caller-supplied credentials.

    This is the multi-user / bring-your-own-key seam. Unlike ``get_engine`` (one engine
    for the whole process from env, cached in deps.py), this builds a FRESH engine per
    request from the ``{provider, api_key, model}`` the request carries, so each user can
    translate with their own provider + key while their data stays local.

    Resolution rules:
    - ``provider`` omitted → fall back to the env-configured engine (``get_engine``, or the
      injected ``fallback`` when given). This keeps local/single-user dev working with no
      request changes (mock/ollama from .env) and lets tests inject a mock.
    - ``provider`` names the SAME engine the server is configured for AND no ``api_key`` is
      supplied → reuse the env-configured/fallback engine (so a picker that echoes the active
      provider without re-sending a key still works, and ollama/mock need no key).
    - ``provider`` is a cloud provider with an ``api_key`` → build a fresh engine from the
      request credentials (the per-user path). The key is used only to construct the engine
      and never persisted or logged.
    - cloud provider WITHOUT a key → ``EngineCredentialError`` (HTTP 401).
    - unknown provider → ``UnknownProviderError`` (HTTP 400).

    ``fallback`` is the env-configured engine the caller already has in hand (e.g. the
    dependency-injected singleton, which tests override). When provided it is reused for the
    no-provider and matching-provider-no-key cases instead of rebuilding from ``get_engine``,
    so dependency overrides and the cached singleton are honored.

    ``model`` here is informational for construction (sets the engine's default model); the
    per-call override still rides on ``TranslationRequest.model`` for streaming translation.
    """
    requested = (provider or "").strip().lower()

    def _env_engine() -> TranslationEngine:
        return fallback if fallback is not None else get_engine(settings)

    # No provider named → env-configured/fallback engine (unchanged single-user behavior).
    if not requested:
        return _env_engine()

    if requested not in KNOWN_PROVIDERS:
        raise UnknownProviderError(
            f"Unknown provider '{provider}'. "
            "Expected 'ollama', 'openrouter', 'gemini', or 'mock'."
        )

    configured = (settings.nb_engine or "").strip().lower()
    # The fallback engine's actual provider (its ``name``) is what the request is really
    # matched against when deciding whether a key is needed — this is what a test override
    # or the live singleton actually is, which may differ from settings.nb_engine.
    fallback_name = fallback.name.strip().lower() if fallback is not None else configured
    key = (api_key or "").strip()

    # Local providers (mock/ollama) never need a key. If the request names the configured
    # local engine, reuse the cached env/fallback engine so ollama's base_url/model/options
    # (or a test's injected mock) hold.
    if requested not in CLOUD_PROVIDERS:
        if requested == fallback_name and not model:
            return _env_engine()
        if requested == "mock":
            return MockEngine()
        # ollama requested (possibly with a per-request model). Build from env connection
        # settings; a per-call model still overrides via TranslationRequest.model, so we
        # keep the configured default here.
        if not settings.ollama_base_url or not settings.ollama_model:
            raise EngineConfigError(
                "Ollama requires OLLAMA_BASE_URL and OLLAMA_MODEL to be set."
            )
        return OllamaEngine(
            base_url=settings.ollama_base_url,
            model=model or settings.ollama_model,
            num_ctx=settings.ollama_num_ctx,
            num_thread=settings.ollama_num_thread,
            think=settings.ollama_think,
        )

    # Cloud providers: a key is REQUIRED. Prefer the request key; fall back to the env key
    # only when the request names the SAME provider the server is configured for (so the
    # single-user env setup keeps working without sending a header).
    env_key = (
        settings.openrouter_api_key
        if requested == "openrouter"
        else settings.gemini_api_key
    )
    effective_key = key or (env_key if requested == fallback_name else "")
    if not effective_key:
        raise EngineCredentialError(
            f"Provider '{requested}' requires an API key. Supply it via the "
            "X-LLM-Api-Key request header."
        )

    if requested == "openrouter":
        from app.engines.openrouter_engine import OpenRouterEngine

        return OpenRouterEngine(
            api_key=effective_key,
            model=model or settings.openrouter_model,
            base_url=settings.openrouter_base_url,
            referer=settings.openrouter_referer,
            title=settings.openrouter_title,
            timeout=settings.cloud_timeout_seconds,
        )

    # requested == "gemini"
    from app.engines.gemini_engine import GeminiEngine

    return GeminiEngine(
        api_key=effective_key,
        model=model or settings.gemini_model,
        base_url=settings.gemini_base_url,
        timeout=settings.cloud_timeout_seconds,
    )


def get_engine(settings: Settings) -> TranslationEngine:
    engine = (settings.nb_engine or "").strip().lower()

    # --- Mock (offline dev/tests) -------------------------------------------
    if engine == "mock":
        return MockEngine()

    # --- Ollama (local LLM server) ------------------------------------------
    if engine == "ollama":
        if not settings.ollama_base_url:
            raise EngineConfigError(
                "NB_ENGINE=ollama requires OLLAMA_BASE_URL to be set."
            )
        if not settings.ollama_model:
            raise EngineConfigError(
                "NB_ENGINE=ollama requires OLLAMA_MODEL to be set."
            )
        return OllamaEngine(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            num_ctx=settings.ollama_num_ctx,
            num_thread=settings.ollama_num_thread,
            think=settings.ollama_think,
        )

    # --- OpenRouter (cloud, OpenAI-compatible gateway) ----------------------
    if engine == "openrouter":
        from app.engines.openrouter_engine import OpenRouterEngine

        if not settings.openrouter_api_key:
            raise EngineConfigError(
                "NB_ENGINE=openrouter requires OPENROUTER_API_KEY to be set. "
                "Get one at https://openrouter.ai/keys"
            )
        return OpenRouterEngine(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            base_url=settings.openrouter_base_url,
            referer=settings.openrouter_referer,
            title=settings.openrouter_title,
            timeout=settings.cloud_timeout_seconds,
        )

    # --- Gemini (Google cloud) ----------------------------------------------
    if engine == "gemini":
        from app.engines.gemini_engine import GeminiEngine

        if not settings.gemini_api_key:
            raise EngineConfigError(
                "NB_ENGINE=gemini requires GEMINI_API_KEY to be set. "
                "Get one at https://aistudio.google.com/apikey"
            )
        return GeminiEngine(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            base_url=settings.gemini_base_url,
            timeout=settings.cloud_timeout_seconds,
        )

    # --- Unknown engine → fail fast -----------------------------------------
    raise EngineConfigError(
        f"Unknown NB_ENGINE '{settings.nb_engine}'. "
        "Expected 'ollama', 'openrouter', 'gemini', or 'mock'."
    )
