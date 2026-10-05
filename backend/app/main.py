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

    # Surface our own INFO logs (e.g. the translate context-occupancy line) under uvicorn,
    # which otherwise leaves app loggers at the root default of WARNING. Scoped to the "app"
    # namespace so we don't flip logging on for third-party libraries. Propagates to
    # uvicorn's root handler, so no handler is attached here.
    logging.getLogger("app").setLevel(logging.INFO)

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

    app.include_router(projects.router)
    app.include_router(translate.router)

    return app


app = create_app()
