"""Deterministic, network-free engine for offline dev and tests (Requirement 5.3).

Does NOT translate. It applies glossary substitutions to the raw text, prefixes a
[MOCK] marker, and streams the echo in small slices so the full UI/stream path can
be exercised without a real model.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

from app.engines.base import (
    GlossaryPair,
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
                text = text.replace(entry.source_term, entry.surface_form)
        return text

    async def stream(self, req: TranslationRequest) -> AsyncIterator[TranslationChunk]:
        applied = sorted(
            {f"{e.source_term}->{e.surface_form}" for e in req.glossary if e.source_term}
        )
        header = (
            f"[MOCK] source={req.source_lang}"
            + (f" | glossary-applied: {', '.join(applied)}" if applied else "")
            + "\n"
        )
        body = self._apply_glossary(req.source_text, req)
        full = header + body

        for i in range(0, len(full), self._chunk_size):
            yield TranslationChunk(content=full[i : i + self._chunk_size], done=False)

        yield TranslationChunk(
            content="",
            done=True,
            meta={"engine": self.name, "model": "mock"},
        )

    async def extract_reference(
        self,
        content: str,
        source_lang: SourceLang,
        detected_names: list[str] | None = None,
    ) -> ReferenceExtraction:
        """Deterministic, network-free extraction for offline dev and tests.

        Summary = a `[MOCK-SUMMARY]` marker plus the first sentence/line, truncated.
        Candidate terms = distinct capitalized words (a crude proper-noun heuristic),
        kept deterministic (sorted, de-duplicated, capped). Any ``detected_names`` hints
        are merged in so the mock mirrors the real engine's hint-aware behavior.
        """
        text = content.strip()
        first = re.split(r"(?<=[.!?。！？])\s+|\n", text, maxsplit=1)[0] if text else ""
        summary = f"[MOCK-SUMMARY] {first[:200]}".strip()
        terms = {w for w in re.findall(r"\b[A-Z][a-zA-Z]+\b", text)}
        terms.update(detected_names or [])
        return ReferenceExtraction(summary=summary, candidate_terms=sorted(terms)[:10])

    async def extract_glossary(
        self,
        source_text: str,
        translated_text: str,
        source_lang: SourceLang,
        candidates: list[str] | None = None,
        model: str | None = None,
    ) -> list[GlossaryPair]:
        """Deterministic, network-free pairing for offline dev and tests.

        A real engine binds source terms to the translation's actual spellings. With no LLM
        the mock can't translate, so it fabricates a stable, verifiable mapping: each source
        candidate that actually occurs in ``source_text`` is paired with the first English word
        found in ``translated_text``, cycling through the English words. The point is to exercise
        the full pairing path (route → storage upsert → candidate rows), not to be correct.
        """
        src_terms = [c for c in (candidates or []) if c and c in source_text]
        english_words = re.findall(r"\b[A-Z][a-zA-Z]+\b", translated_text)
        pairs: list[GlossaryPair] = []
        seen: set[str] = set()
        for i, term in enumerate(src_terms):
            if term in seen:
                continue
            seen.add(term)
            surface = english_words[i % len(english_words)] if english_words else term
            pairs.append(
                GlossaryPair(source_term=term, surface_form=surface, category="term")
            )
        return pairs

    async def extract_style(
        self,
        content: str,
        source_lang: SourceLang,
    ) -> str:
        """Deterministic, network-free style profile for offline dev and tests.

        A real engine analyzes the prose; the mock can't, so it emits a stable marker guide
        derived from trivial measurements (word count, avg sentence length) so the full
        extract-style path can be exercised deterministically.
        """
        text = content.strip()
        words = text.split()
        sentences = [s for s in re.split(r"[.!?。！？]+", text) if s.strip()]
        avg_len = (len(words) / len(sentences)) if sentences else 0
        return (
            "[MOCK-STYLE]\n"
            f"- Source language: {source_lang}\n"
            f"- Approx. {len(words)} words, {len(sentences)} sentences "
            f"(avg {avg_len:.1f} words/sentence).\n"
            "- Use a neutral, consistent register.\n"
            "- Keep honorifics and titles consistent with the glossary."
        )

    async def health(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return [self.name]
