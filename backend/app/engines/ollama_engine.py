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

from app.engines.base import TranslationChunk, TranslationEngine, TranslationRequest
from app.services.prompt import build_messages

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class OllamaEngine(TranslationEngine):
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        num_ctx: int = 16384,
        think: bool = False,
        timeout: float = 300.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._num_ctx = num_ctx
        self._think = think
        self._timeout = timeout

    async def stream(self, req: TranslationRequest) -> AsyncIterator[TranslationChunk]:
        payload = {
            "model": req.model or self._model,
            "messages": build_messages(req),
            "stream": True,
            "think": self._think,
            "options": {"num_ctx": self._num_ctx},
        }

        # Buffer tails to strip a <think> block if the model emits one anyway.
        in_think = False
        meta: dict | None = None

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

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
