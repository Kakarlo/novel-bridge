"""Engine selection and startup validation (Requirements 5.5, 5.6)."""

from __future__ import annotations

from app.config import Settings
from app.engines.base import TranslationEngine
from app.engines.mock_engine import MockEngine
from app.engines.ollama_engine import OllamaEngine


class EngineConfigError(RuntimeError):
    """Raised at startup when the selected engine is misconfigured."""


def get_engine(settings: Settings) -> TranslationEngine:
    engine = (settings.nb_engine or "").strip().lower()

    if engine == "mock":
        return MockEngine()

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

    raise EngineConfigError(
        f"Unknown NB_ENGINE '{settings.nb_engine}'. Expected 'ollama' or 'mock'."
    )
