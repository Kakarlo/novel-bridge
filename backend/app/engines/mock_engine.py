"""Deterministic, network-free engine for offline dev and tests (Requirement 5.3).

Does NOT translate. It applies glossary substitutions to the raw text, prefixes a
[MOCK] marker, and streams the echo in small slices so the full UI/stream path can
be exercised without a real model.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

from app.engines.base import (
    ReferenceExtraction,
    TranslationChunk,
    TranslationEngine,
    TranslationRequest,
)
from app.models import SourceLang


class MockEngine(TranslationEngine):
    name = "mock"

    def __init__(self, chunk_size: int = 24) -> None:
        self._chunk_size = chunk_size

    def _apply_glossary(self, text: str, req: TranslationRequest) -> str:
        for entry in req.glossary:
            if entry.source_term:
                text = text.replace(entry.source_term, entry.translation)
        return text

    async def stream(self, req: TranslationRequest) -> AsyncIterator[TranslationChunk]:
        applied = sorted(
            {f"{e.source_term}->{e.translation}" for e in req.glossary}
        )
        header = (
            f"[MOCK] source={req.source_lang}"
            + (f" | glossary-applied: {', '.join(applied)}" if applied else "")
            + "\n"
        )
        body = self._apply_glossary(req.raw_text, req)
        full = header + body

        for i in range(0, len(full), self._chunk_size):
            yield TranslationChunk(content=full[i : i + self._chunk_size], done=False)

        yield TranslationChunk(
            content="",
            done=True,
            meta={"engine": self.name, "model": "mock"},
        )

    async def extract_reference(
        self, content: str, source_lang: SourceLang
    ) -> ReferenceExtraction:
        """Deterministic, network-free extraction for offline dev and tests.

        Summary = a `[MOCK-SUMMARY]` marker plus the first sentence/line, truncated.
        Candidate terms = distinct capitalized words (a crude proper-noun heuristic),
        kept deterministic (sorted, de-duplicated, capped).
        """
        text = content.strip()
        first = re.split(r"(?<=[.!?。！？])\s+|\n", text, maxsplit=1)[0] if text else ""
        summary = f"[MOCK-SUMMARY] {first[:200]}".strip()
        terms = sorted({w for w in re.findall(r"\b[A-Z][a-zA-Z]+\b", text)})[:10]
        return ReferenceExtraction(summary=summary, candidate_terms=terms)

    async def health(self) -> bool:
        return True
