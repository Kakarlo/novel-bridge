"""FastAPI application factory for NovelBridge."""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import projects, translate
from app.config import Settings, get_settings
from app.deps import get_request_api_key, get_translation_engine, resolve_request_engine
from app.engines.base import TranslationEngine
from app.engines.factory import get_engine


def _default_model(settings: Settings, provider: str | None = None) -> str:
    """Return the configured default model name for a provider (or the active engine).

    Used by /api/health and /api/models so the frontend shows the correct `current`.
    When ``provider`` is given it reports that provider's configured default model (so a
    cred-aware request echoes the right `current` for the picker); otherwise it reports
    the server's active engine default.
    """
    engine = (provider or settings.nb_engine or "").strip().lower()
    if engine == "openrouter":
        return settings.openrouter_model
    if engine == "gemini":
        return settings.gemini_model
    if engine == "mock":
        return "mock"
    return settings.ollama_model


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    # Surface our own INFO logs (e.g. the translate context-occupancy line) under uvicorn.
    # Uvicorn configures logging via dictConfig with NO handler on the root logger, so an
    # app logger left to propagate reaches a handler-less root and prints nothing — setting
    # the level alone isn't enough, it needs its own handler. Attach one directly to the
    # "app" namespace (uvicorn-style format so it blends in) and stop propagation so it never
    # double-logs if the root later gains a handler. Idempotent across repeated create_app().
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s - %(message)s"))
        app_logger.addHandler(handler)
    app_logger.propagate = False

    # Fail fast if the selected engine is misconfigured (Requirement 5.6).
    get_engine(settings)

    app = FastAPI(
        title="NovelBridge API",
        version="0.1.0",
        description="Context-aware CN/JP to English novel-chapter translator.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health(
        provider: str | None = None,
        fallback_engine: TranslationEngine = Depends(get_translation_engine),
        api_key: str | None = Depends(get_request_api_key),
    ) -> dict:
        # Probe the actual engine (e.g. ping Ollama, validate an API key) rather than
        # echoing config, so a disconnected backend / bad key reports as unreachable. The
        # frontend status indicator keys off `reachable` for its dot.
        #
        # Cred-aware (BYO-key): a `provider` query param + X-LLM-Api-Key header let the
        # picker validate a user's own key against their chosen provider. With no creds it
        # probes the server's env-configured engine (unchanged single-user behavior). An
        # unknown provider (400) / missing key (401) surfaces as a normal HTTP error, which
        # the indicator can show distinctly from "reachable=false".
        engine = resolve_request_engine(
            provider=provider,
            model=None,
            api_key=api_key,
            settings=settings,
            fallback=fallback_engine,
        )
        try:
            reachable = await engine.health()
        except Exception:  # noqa: BLE001 - never let the probe raise
            reachable = False
        return {
            "status": "ok" if reachable else "unreachable",
            "reachable": reachable,
            "engine": engine.name,
            "model": _default_model(settings, provider),
        }

    @app.get("/api/models")
    async def models(
        provider: str | None = None,
        fallback_engine: TranslationEngine = Depends(get_translation_engine),
        api_key: str | None = Depends(get_request_api_key),
    ) -> dict:
        # List models the engine can serve, for the frontend picker. `current` is the
        # configured default; a per-request override already rides on TranslationRequest.model.
        # Degrades to an empty list (never raises) when the engine is unreachable.
        #
        # Cred-aware (BYO-key): a `provider` query param + X-LLM-Api-Key header let the
        # picker list a user's own provider/models using their key. With no creds it lists
        # the server's env-configured engine. Flat {models, current} is kept (the current
        # single-provider contract); the provider-aware {providers:[...]} shape in tech.md
        # is a later change to make once the frontend drives it.
        engine = resolve_request_engine(
            provider=provider,
            model=None,
            api_key=api_key,
            settings=settings,
            fallback=fallback_engine,
        )
        try:
            available = await engine.list_models()
        except Exception:  # noqa: BLE001 - never let the listing raise
            available = []
        return {"models": available, "current": _default_model(settings, provider)}

    app.include_router(projects.router)
    app.include_router(translate.router)

    return app


app = create_app()
