"""FastAPI application factory for NovelBridge."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

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

    return app


app = create_app()
