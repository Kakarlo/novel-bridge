"""OpenRouter engine: streams translations via the OpenAI-compatible chat completions API.

OpenRouter is a gateway to 200+ models (DeepSeek, Claude, GPT, Gemini, Mistral, etc.).
The API is OpenAI-compatible: POST /chat/completions, SSE streaming with
`data: {"choices":[{"delta":{"content":"..."}}]}` lines, ending with `data: [DONE]`.

## How to add another OpenAI-compatible provider (e.g. OpenAI, DeepSeek direct)
## -----------------------------------------------------------------------
## 1. Copy this file, rename the class and `name`.
## 2. Adjust the base_url default and any auth/header differences.
## 3. Add config keys in config.py (API key, model, base_url).
## 4. Register the new engine in factory.py's get_engine().
## 5. Update .env.example.
## The heavy lifting (streaming, non-streaming, JSON extraction, error handling)
## is identical — only the URL, auth, and optional headers change.
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
from app.engines.ollama_engine import _parse_extraction, _parse_glossary_pairs
from app.models import SourceLang
from app.services.prompt import (
    build_extraction_messages,
    build_glossary_pairing_messages,
    build_style_extraction_messages,
    build_translation_messages,
)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class OpenRouterEngine(TranslationEngine):
    """OpenAI-compatible engine via OpenRouter's gateway.

    ## Adding a new OpenAI-compatible provider
    ## 1. Subclass this or copy it.
    ## 2. Override `name`, `__init__` defaults, and `_headers()`.
    ## 3. Everything else (stream/extract_*/health/list_models) works unchanged.
    """

    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str = "openrouter/free",
        base_url: str = "https://openrouter.ai/api/v1",
        referer: str = "",
        title: str = "NovelBridge",
        timeout: float = 300.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._referer = referer
        self._title = title
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        """Auth + OpenRouter attribution headers. Override for other providers."""
        h: dict[str, str] = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        # OpenRouter-specific attribution (recommended, not required).
        if self._referer:
            h["HTTP-Referer"] = self._referer
        if self._title:
            h["X-Title"] = self._title
        return h

    # --- streaming translation -----------------------------------------------

    async def stream(self, req: TranslationRequest) -> AsyncIterator[TranslationChunk]:
        """OpenAI-compatible SSE streaming.

        Each SSE `data:` line is JSON with `choices[0].delta.content`. The stream ends
        with `data: [DONE]`. We strip `<think>` blocks as a guard (same as Ollama).
        """
        payload = {
            "model": req.model or self._model,
            "messages": build_translation_messages(req),
            "stream": True,
        }

        dump_messages(payload["messages"], "OPENROUTER REQUEST")

        in_think = False
        model_used = payload["model"]

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    # SSE comments (: ...) — OpenRouter sends these as keepalives.
                    if line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        obj = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    # Mid-stream error event.
                    if "error" in obj:
                        err_msg = obj["error"].get("message", str(obj["error"]))
                        raise RuntimeError(f"OpenRouter error: {err_msg}")

                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content") or ""
                    if obj.get("model"):
                        model_used = obj["model"]

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

    # --- non-streaming helpers ------------------------------------------------

    async def _chat(
        self, messages: list[dict[str, str]], *, json_mode: bool = False
    ) -> str:
        """Non-streaming chat completion. Returns the assistant's text content.

        ``json_mode`` sets response_format to JSON (supported by most OpenRouter models).
        Returns "" on any HTTP/parse error (degraded, never raises to the caller).
        """
        payload: dict = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError):
            return ""
        choices = data.get("choices") or []
        if not choices:
            return ""
        raw = (choices[0].get("message") or {}).get("content", "") or ""
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
        """Ping the models endpoint to confirm reachability + valid key."""
        if not self._api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.head(
                    f"{self._base_url}/models",
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def list_models(self) -> list[str]:
        """List available models. Returns model IDs sorted alphabetically.

        OpenRouter's /models returns `{data: [{id, ...}, ...]}`. We return the
        `id` field (e.g. "deepseek/deepseek-chat"). [] if unreachable.
        """
        if not self._api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._base_url}/models?output_modalities=text&sort=pricing-low-to-high",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError):
            return []
        models = data.get("data") or []
        # Kept the exact order returned by the API instead of forcing alphabetical sort
        return [m.get("id", "") for m in models if isinstance(m, dict) and m.get("id")]
