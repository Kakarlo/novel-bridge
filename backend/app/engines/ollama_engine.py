"""Ollama engine: streams translations from a home-server Ollama instance.

Calls the native POST /api/chat with stream=true, think=false, and
options.num_ctx. Parses newline-delimited JSON chunks and strips any residual
<think>...</think> block as a safeguard (Requirements 5.2, 5.4, 4.3, 4.4).
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator

import httpx

from app.debug import dump_messages
from app.engines.base import (
    GlossaryPair,
    ReferenceExtraction,
    TranslationChunk,
    TranslationEngine,
    TranslationRequest,
)
from app.models import SourceLang
from app.services.prompts.builders import (
    build_extraction_messages,
    build_glossary_pairing_messages,
    build_style_extraction_messages,
    build_translation_messages,
)

_VALID_CATEGORIES = {"character", "title", "term", "location", "organization", "item"}
_VALID_GENDERS = {"male", "female", "unknown"}

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _parse_extraction(raw: str) -> ReferenceExtraction:
    """Parse an extraction response into a ReferenceExtraction, defensively.

    Tries strict JSON first, then a JSON object embedded in surrounding text, then
    falls back to using the whole response as the summary with no terms.
    """
    candidates: list[str] = []
    if raw:
        candidates.append(raw)
        start, end = raw.find("{"), raw.rfind("}")
        if 0 <= start < end:
            candidates.append(raw[start : end + 1])

    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        summary = str(obj.get("summary") or "").strip()
        terms_raw = obj.get("candidate_terms") or []
        terms: list[str] = []
        if isinstance(terms_raw, list):
            seen: set[str] = set()
            for t in terms_raw:
                s = str(t).strip()
                if s and s not in seen:
                    seen.add(s)
                    terms.append(s)
        return ReferenceExtraction(summary=summary, candidate_terms=terms[:20])

    # Fallback: no parseable JSON — keep a trimmed summary, no terms.
    return ReferenceExtraction(summary=raw[:500].strip(), candidate_terms=[])


def _parse_glossary_pairs(raw: str) -> list[GlossaryPair]:
    """Parse a glossary-pairing response into GlossaryPair rows, defensively.

    Expects a JSON object ``{"pairs": [...]}`` (same embedded-JSON tolerance as
    ``_parse_extraction``). Each pair must carry a non-empty source_term and surface_form;
    category/gender are validated against the allowed sets and defaulted otherwise. Any
    parse failure yields ``[]`` so a quirky model response degrades to "no suggestions".
    """
    candidates: list[str] = []
    if raw:
        candidates.append(raw)
        start, end = raw.find("{"), raw.rfind("}")
        if 0 <= start < end:
            candidates.append(raw[start : end + 1])

    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        rows = obj.get("pairs")
        if not isinstance(rows, list):
            continue
        pairs: list[GlossaryPair] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            source_term = str(row.get("source_term") or "").strip()
            surface_form = str(row.get("surface_form") or "").strip()
            if not source_term or not surface_form:
                continue
            key = (source_term, surface_form.casefold())
            if key in seen:
                continue
            seen.add(key)
            category = str(row.get("category") or "term").strip().lower()
            if category not in _VALID_CATEGORIES:
                category = "term"
            gender = str(row.get("gender") or "").strip().lower()
            gender = gender if gender in _VALID_GENDERS else None
            # "unknown" carries no signal; store it as None to match the glossary convention.
            if gender == "unknown":
                gender = None
            note = str(row.get("note") or "").strip() or None
            pairs.append(
                GlossaryPair(
                    source_term=source_term,
                    surface_form=surface_form,
                    category=category,
                    gender=gender,
                    note=note,
                )
            )
            if len(pairs) >= 30:
                break
        return pairs

    return []


class OllamaEngine(TranslationEngine):
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        num_ctx: int = 16384,
        num_thread: int = 2,
        think: bool = False,
        timeout: float = 300.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._num_ctx = num_ctx
        self._num_thread = num_thread
        self._think = think
        self._timeout = timeout

    async def stream(self, req: TranslationRequest) -> AsyncIterator[TranslationChunk]:
        payload = {
            "model": req.model or self._model,
            "messages": build_translation_messages(req),
            "stream": True,
            "think": self._think,
            "options": {"num_ctx": self._num_ctx, "num_thread": self._num_thread},
        }

        # Buffer tails to strip a <think> block if the model emits one anyway.
        in_think = False
        meta: dict | None = None

        dump_messages(payload["messages"], "OLLAMA REQUEST")

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST", f"{self._base_url}/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    piece = (obj.get("message") or {}).get("content", "")
                    done = bool(obj.get("done"))

                    if piece:
                        # Lightweight guard against a <think> preamble.
                        if "<think>" in piece:
                            in_think = True
                        if in_think:
                            if "</think>" in piece:
                                in_think = False
                                piece = _THINK_RE.sub("", piece)
                                piece = piece.split("</think>")[-1]
                            else:
                                piece = ""
                        if piece:
                            yield TranslationChunk(content=piece, done=False)

                    if done:
                        meta = {
                            "engine": self.name,
                            "model": payload["model"],
                            "total_duration": obj.get("total_duration"),
                            "eval_count": obj.get("eval_count"),
                        }

        yield TranslationChunk(content="", done=True, meta=meta or {"engine": self.name})

    async def extract_reference(
        self,
        content: str,
        source_lang: SourceLang,
        detected_names: list[str] | None = None,
    ) -> ReferenceExtraction:
        """Distill a reference chapter via a single non-streaming extraction call.

        Asks the model for a JSON object (summary + candidate_terms). Parses it
        defensively and falls back to a heuristic summary if the model returns
        non-JSON, so a quirky model response never breaks reference upload.
        ``detected_names`` (rule-based hints) are passed into the prompt to anchor it.
        """
        payload = {
            "model": self._model,
            "messages": build_extraction_messages(content, source_lang, detected_names),
            "stream": False,
            "think": self._think,
            "format": "json",
            "options": {"num_ctx": self._num_ctx, "num_thread": self._num_thread},
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        raw = (data.get("message") or {}).get("content", "") or ""
        raw = _THINK_RE.sub("", raw).strip()
        return _parse_extraction(raw)

    async def extract_glossary(
        self,
        source_text: str,
        translated_text: str,
        source_lang: SourceLang,
        candidates: list[str] | None = None,
        model: str | None = None,
    ) -> list[GlossaryPair]:
        """Pair source terms to the English spellings in a translation via one LLM call.

        Sends both the raw source chapter and its English output. The model returns a JSON
        array of ``{source_term, surface_form, category, gender, note}`` objects. Parsed
        defensively; returns ``[]`` on any failure (a flaky response never breaks the UI).

        ``model`` overrides the engine default for this call (callers may pick a stronger
        model for accuracy-sensitive pairing). ``candidates`` are deterministic pre-filter
        hints injected into the prompt to keep it focused and cheap.
        """
        payload = {
            "model": model or self._model,
            "messages": build_glossary_pairing_messages(
                source_text, translated_text, source_lang, candidates
            ),
            "stream": False,
            "think": self._think,
            "format": "json",
            "options": {"num_ctx": self._num_ctx, "num_thread": self._num_thread},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError):
            return []

        raw = (data.get("message") or {}).get("content", "") or ""
        raw = _THINK_RE.sub("", raw).strip()
        return _parse_glossary_pairs(raw)

    async def extract_style(
        self,
        content: str,
        source_lang: SourceLang,
    ) -> str:
        """Extract a writing-style profile via a single non-streaming call.

        Unlike reference extraction this returns free-form markdown prose (no JSON), so it's
        used as-is in the translate prompt. Returns "" on any failure (degraded, never
        raises) — the project simply has no style until a successful extraction.
        """
        payload = {
            "model": self._model,
            "messages": build_style_extraction_messages(content, source_lang),
            "stream": False,
            "think": self._think,
            "options": {"num_ctx": self._num_ctx, "num_thread": self._num_thread},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError):
            return ""

        raw = (data.get("message") or {}).get("content", "") or ""
        return _THINK_RE.sub("", raw).strip()

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Ollama's official root endpoint acts as the health check
                resp = await client.head(f"{self._base_url}/")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def list_models(self) -> list[str]:
        """List installed models via Ollama's GET /api/tags, filtered for text LLMs."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError):
            return []

        models = data.get("models") or []
        names: list[str] = []

        for m in models:
            if not isinstance(m, dict):
                continue
            name = m.get("name", "")
            if not name:
                continue
            # Filter: Skip dedicated local embedding models (e.g., nomic-embed-text, mxbai-embed)
            if "embed" in name.lower():
                continue

            names.append(name)

        return sorted(names)

