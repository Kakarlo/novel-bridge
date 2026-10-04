"""Shared dependency providers (storage + engine)."""

from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.engines.base import TranslationEngine
from app.engines.factory import get_engine
from app.storage.base import StorageService
from app.storage.sqlite_store import SQLiteStorage


@lru_cache
def get_storage() -> StorageService:
    settings: Settings = get_settings()
    return SQLiteStorage(settings.nb_db_path)


@lru_cache
def get_translation_engine() -> TranslationEngine:
    settings: Settings = get_settings()
    return get_engine(settings)
