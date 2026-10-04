"""Application configuration loaded from environment / .env.

All environment-specific values live here so the app stays local-first yet
AWS-ready (Requirements 5.4, 6.3, 6.4, 6.5).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Engine selection
    nb_engine: str = "ollama"

    # Ollama engine
    ollama_base_url: str = "http://192.168.254.22:11434"
    ollama_model: str = "qwen3.5:0.8b"
    ollama_num_ctx: int = 16384
    ollama_think: bool = False

    # Context budgeting
    nb_context_budget_tokens: int = 12000

    # Storage
    nb_db_path: str = "./novelbridge.db"

    # CORS
    nb_cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.nb_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
