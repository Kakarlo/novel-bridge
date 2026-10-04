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


@dataclass
class ReferenceExtraction:
    """Result of distilling a reference chapter into reusable, non-echoable context.

    `summary` captures plot/style/tone in a few sentences; `candidate_terms` lists
    recurring proper nouns / terminology worth adding to the glossary. Both are kept
    small so they can be injected into the translate prompt without the model echoing
    raw reference text (the reference-echo bug this fixes).
    """

    summary: str
    candidate_terms: list[str] = field(default_factory=list)


class TranslationEngine(ABC):
    """All engines conform to this streaming-first interface."""

    name: str = "base"

    @abstractmethod
    async def stream(self, req: TranslationRequest) -> AsyncIterator[TranslationChunk]:
        """Yield TranslationChunks; the final chunk has done=True."""
        raise NotImplementedError

    @abstractmethod
    async def extract_reference(
        self, content: str, source_lang: SourceLang
    ) -> ReferenceExtraction:
        """Distill a reference chapter into a summary + candidate glossary terms.

        Runs once when a reference is uploaded (and on resummarize). The derived,
        compact result is what later translations consume instead of the raw text.
        """
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        """Return True if the engine is ready to serve requests."""
        raise NotImplementedError
