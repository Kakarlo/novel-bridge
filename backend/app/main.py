"""FastAPI application factory for NovelBridge."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import projects, translate
from app.config import Settings, get_settings
from app.engines.factory import get_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

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
    def health() -> dict:
        return {
            "status": "ok",
            "engine": settings.nb_engine,
            "model": settings.ollama_model,
        }

    app.include_router(projects.router)
    app.include_router(translate.router)

    return app


app = create_app()
