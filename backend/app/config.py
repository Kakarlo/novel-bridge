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

    # Debug: when true, engines/prompt builders print the assembled chat messages to stdout
    # (useful while tuning prompts). Default OFF so a hosted/production run never spams logs
    # or risks leaking content. Toggle with NB_DEBUG_PROMPTS=true.
    nb_debug_prompts: bool = False

    # Ollama engine
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:0.8b"
    ollama_num_ctx: int = 16384
    ollama_num_thread: int = 2
    ollama_think: bool = False

    # --- Cloud engines (bring-your-own API key) ---------------------------------
    # Hosted providers behind the same TranslationEngine interface. Each is optional and
    # only usable when its API key is configured. Keys come from the environment here (the
    # local-first default); a future per-user credential store goes behind StorageService —
    # see tech.md "Bring-your-own LLM API token". NEVER log or echo key values.
    #
    # To set NB_ENGINE to a cloud provider, set the matching *_API_KEY. The *_MODEL is the
    # default model for that provider (overridable per-request via the translate selection).

    # OpenRouter (OpenAI-compatible gateway to 200+ models).
    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Optional attribution headers OpenRouter uses to identify the calling app (harmless if
    # blank). Not secrets.
    openrouter_referer: str = "http://localhost:5173"
    openrouter_title: str = "NovelBridge"

    # Google Gemini.
    # Use a specific model name (e.g. "gemini-3.5-flash-lite") rather than aliases like
    # "gemini-flash-latest" — aliases are prone to overload-503 since everyone hits them.
    # Run GET /api/models to see what's available for your key.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    # Shared cloud request timeout (seconds).
    cloud_timeout_seconds: float = 300.0

    # Concurrency
    # Caps simultaneous in-flight translations (PARALLEL requests). num_thread caps
    # CPU within a single request; this caps how many run at once.
    nb_max_concurrent_translations: int = 1
    # How long a queued request waits for a free slot before giving up with an
    # SSE error, so clients don't block indefinitely.
    nb_queue_timeout_seconds: float = 30.0

    # Context budgeting
    nb_context_budget_tokens: int = 12000

    # EXPERIMENTAL deterministic helpers (default OFF; cheap to remove). Each needs its
    # own spaCy model (zh/ja) or just the stdlib. See services/source_terms.py and
    # services/pronoun_check.py.
    nb_source_terms: bool = False  # zh/ja source-language proper-noun detection
    nb_pronoun_check: bool = False  # English pronoun-drift DETECTION (flags, never rewrites)

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
