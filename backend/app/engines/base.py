"""Translation engine interface and shared data classes (Requirement 5.1)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.models import GlossaryEntry, SourceLang


@dataclass
class TranslationRequest:
    raw_text: str
    source_lang: SourceLang
    glossary: list[GlossaryEntry] = field(default_factory=list)
    reference_context: str = ""
    model: str | None = None


@dataclass
class TranslationChunk:
    content: str
    done: bool = False
    meta: dict | None = None


class TranslationEngine(ABC):
    """All engines conform to this streaming-first interface."""

    name: str = "base"

    @abstractmethod
    async def stream(self, req: TranslationRequest) -> AsyncIterator[TranslationChunk]:
        """Yield TranslationChunks; the final chunk has done=True."""
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        """Return True if the engine is ready to serve requests."""
        raise NotImplementedError
