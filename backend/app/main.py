"""FastAPI application factory for NovelBridge."""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import projects, translate
from app.config import Settings, get_settings
from app.deps import get_translation_engine
from app.engines.base import TranslationEngine
from app.engines.factory import get_engine


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
        engine: TranslationEngine = Depends(get_translation_engine),
    ) -> dict:
        # Probe the actual engine (e.g. ping Ollama) rather than echoing config,
        # so a disconnected LLM server reports as unreachable. The frontend's
        # status indicator keys off `reachable` for its dot.
        try:
            reachable = await engine.health()
        except Exception:  # noqa: BLE001 - never let the probe raise
            reachable = False
        return {
            "status": "ok" if reachable else "unreachable",
            "reachable": reachable,
            "engine": settings.nb_engine,
            "model": settings.ollama_model,
        }

    @app.get("/api/models")
    async def models(
        engine: TranslationEngine = Depends(get_translation_engine),
    ) -> dict:
        # List models the engine can serve, for the frontend picker. `current` is the
        # configured default; a per-request override already rides on TranslationRequest.model.
        # Degrades to an empty list (never raises) when the engine is unreachable.
        try:
            available = await engine.list_models()
        except Exception:  # noqa: BLE001 - never let the listing raise
            available = []
        return {"models": available, "current": settings.ollama_model}

    app.include_router(projects.router)
    app.include_router(translate.router)

    return app


app = create_app()
