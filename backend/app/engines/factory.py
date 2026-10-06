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
