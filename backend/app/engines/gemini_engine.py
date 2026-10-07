"""Gemini engine: streams translations via Google's Generative Language REST API.

The Gemini API is NOT OpenAI-compatible — it has its own message format:
  - Contents use `{role, parts: [{text}]}` instead of `{role, content}`.
  - System instructions go in a top-level `system_instruction` field, not as a "system" role.
  - Streaming uses `streamGenerateContent?alt=sse` with SSE events shaped as
    `data: {"candidates":[{"content":{"parts":[{"text":"..."}]}}]}`.
  - Non-streaming uses `generateContent` returning the same shape (no SSE).
  - Auth is a header `x-goog-api-key` (or a query param `key=`), not Bearer tokens.
  - Model listing is `GET /v1beta/models`.

## How to add another non-OpenAI provider (e.g. Anthropic Claude direct)
## -----------------------------------------------------------------------
## 1. Copy this file; rename the class and `name`.
## 2. Adapt `_to_gemini_messages` → your provider's message format.
## 3. Adapt `_parse_stream_line` → your provider's SSE chunk shape.
## 4. Adjust the auth header (Claude uses `x-api-key`).
## 5. Add config keys in config.py, register in factory.py.
## The rest (engine ABC methods, prompt builders, parsers) stays the same.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator

import httpx

from app.engines.base import (
    GlossaryPair,
    ReferenceExtraction,
    TranslationChunk,
    TranslationEngine,
    TranslationRequest,
)
from app.engines.ollama_engine import _parse_extraction, _parse_glossary_pairs
from app.models import SourceLang
from app.services.prompt import (
    build_extraction_messages,
    build_glossary_pairing_messages,
    build_style_extraction_messages,
    build_translation_messages,
)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _to_gemini_messages(
    messages: list[dict[str, str]],
) -> tuple[dict | None, list[dict]]:
    """Convert OpenAI-style messages to Gemini's format.

    Returns (system_instruction, contents) where:
    - system_instruction: `{"parts": [{"text": "..."}]}` or None.
    - contents: `[{"role": "user"|"model", "parts": [{"text": "..."}]}, ...]`.

    Gemini quirks:
    - "system" role → separate `system_instruction` top-level field.
    - "assistant" → "model".
    - Consecutive messages from the same role must be merged (Gemini rejects them).
    """
    system_text: list[str] = []
    contents: list[dict] = []
    for msg in messages:
        role = msg["role"]
        text = msg.get("content", "")
        if role == "system":
            system_text.append(text)
            continue
        gem_role = "model" if role == "assistant" else "user"
        # Merge consecutive same-role entries.
        if contents and contents[-1]["role"] == gem_role:
            contents[-1]["parts"].append({"text": text})
        else:
            contents.append({"role": gem_role, "parts": [{"text": text}]})

    sys_inst = None
    if system_text:
        sys_inst = {"parts": [{"text": t} for t in system_text]}

    return sys_inst, contents


class GeminiEngine(TranslationEngine):
    """Google Gemini engine via the REST Generative Language API.

    ## Adding another Google-style provider
    ## 1. Subclass this or copy it.
    ## 2. Override `name`, `_base_url`, and `_headers()`.
    ## 3. If the provider uses a different SSE shape, override `_parse_stream_chunk`.
    """

    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = 300.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }

    def _model_url(self, model: str | None, action: str) -> str:
        """Build the Gemini model endpoint URL."""
        m = model or self._model
        return f"{self._base_url}/models/{m}:{action}"

    # --- streaming translation -----------------------------------------------

    async def stream(self, req: TranslationRequest) -> AsyncIterator[TranslationChunk]:
        """Gemini SSE streaming via streamGenerateContent?alt=sse.

        Each SSE `data:` line is JSON:
          {"candidates": [{"content": {"parts": [{"text": "..."}]}}]}
        The stream ends when the connection closes. We strip `<think>` blocks as a guard.
        """
        messages = build_translation_messages(req)
        sys_inst, contents = _to_gemini_messages(messages)
        payload: dict = {"contents": contents}
        if sys_inst:
            payload["system_instruction"] = sys_inst

        model_used = req.model or self._model
        in_think = False

        for i, msg in enumerate(messages):
            print(f"\n--- MESSAGE {i} ({msg['role']}) ---")
            print(msg["content"])

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            url = self._model_url(req.model, "streamGenerateContent") + "?alt=sse"
            async with client.stream(
                "POST", url, json=payload, headers=self._headers()
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    try:
                        obj = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    # Error in the response body.
                    if "error" in obj:
                        err = obj["error"]
                        raise RuntimeError(
                            f"Gemini error: {err.get('message', str(err))}"
                        )
                    piece = self._extract_text(obj)
                    if piece:
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

        yield TranslationChunk(
            content="", done=True, meta={"engine": self.name, "model": model_used}
        )

    @staticmethod
    def _extract_text(obj: dict) -> str:
        """Pull text from a Gemini response/chunk object."""
        candidates = obj.get("candidates") or []
        if not candidates:
            return ""
        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        return "".join(p.get("text", "") for p in parts if isinstance(p, dict))

    # --- non-streaming helpers ------------------------------------------------

    async def _chat(
        self, messages: list[dict[str, str]], *, json_mode: bool = False
    ) -> str:
        """Non-streaming Gemini call. Returns the text content.

        ``json_mode`` sets `responseMimeType` to `application/json`.
        Returns "" on any error (degraded, never raises).
        """
        sys_inst, contents = _to_gemini_messages(messages)
        payload: dict = {"contents": contents}
        if sys_inst:
            payload["system_instruction"] = sys_inst
        if json_mode:
            payload["generationConfig"] = {"responseMimeType": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                url = self._model_url(None, "generateContent")
                resp = await client.post(url, json=payload, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError):
            return ""
        raw = self._extract_text(data)
        return _THINK_RE.sub("", raw).strip()

    async def extract_reference(
        self,
        content: str,
        source_lang: SourceLang,
        detected_names: list[str] | None = None,
    ) -> ReferenceExtraction:
        raw = await self._chat(
            build_extraction_messages(content, source_lang, detected_names),
            json_mode=True,
        )
        return _parse_extraction(raw) if raw else ReferenceExtraction(summary="")

    async def extract_glossary(
        self,
        raw_text: str,
        output_text: str,
        source_lang: SourceLang,
        candidates: list[str] | None = None,
        model: str | None = None,
    ) -> list[GlossaryPair]:
        raw = await self._chat(
            build_glossary_pairing_messages(raw_text, output_text, source_lang, candidates),
            json_mode=True,
        )
        return _parse_glossary_pairs(raw) if raw else []

    async def extract_style(
        self, content: str, source_lang: SourceLang
    ) -> str:
        return await self._chat(build_style_extraction_messages(content, source_lang))

    async def health(self) -> bool:
        """Ping the models list endpoint to confirm API key + reachability."""
        if not self._api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self._base_url}/models",
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def list_models(self) -> list[str]:
        """List available Gemini models.

        Gemini's GET /v1beta/models returns `{models: [{name: "models/gemini-...", ...}]}`.
        We strip the "models/" prefix so the ID matches what's passed to generateContent.
        [] if unreachable or key is missing.
        """
        if not self._api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._base_url}/models",
                    headers=self._headers(),
                )
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
            # Gemini returns "models/gemini-2.0-flash" — strip the prefix.
            if name.startswith("models/"):
                name = name[len("models/"):]
            # Only include generative models (skip embedding models, etc.).
            methods = m.get("supportedGenerationMethods") or []
            if "generateContent" in methods and name:
                names.append(name)
        return sorted(names)
