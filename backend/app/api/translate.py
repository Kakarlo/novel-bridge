"""SSE translation endpoint with auto-save (Requirements 4.1, 4.4, 4.5, 4.6)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.config import Settings, get_settings
from app.deps import get_storage, get_translation_engine
from app.engines.base import TranslationEngine, TranslationRequest
from app.models import TranslateRequest
from app.services import context_builder as cb
from app.storage.base import StorageService

router = APIRouter(prefix="/api", tags=["translate"])


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/projects/{pid}/translate")
def translate(
    pid: str,
    body: TranslateRequest,
    store: StorageService = Depends(get_storage),
    engine: TranslationEngine = Depends(get_translation_engine),
    settings: Settings = Depends(get_settings),
):
    project = store.get_project(pid)
    if not project:
        raise HTTPException(404, "Project not found")

    glossary = store.list_glossary(pid)
    references = store.list_references(pid)
    built = cb.build(
        glossary, references, body.raw_text, settings.nb_context_budget_tokens
    )

    req = TranslationRequest(
        raw_text=body.raw_text,
        source_lang=body.source_lang,
        glossary=glossary,
        reference_context=built.reference_context,
    )

    async def event_stream() -> AsyncIterator[str]:
        collected: list[str] = []
        model_used = settings.ollama_model if engine.name == "ollama" else engine.name
        if built.truncated:
            yield _sse({"info": "reference context truncated to fit the model window"})
        try:
            async for chunk in engine.stream(req):
                if chunk.content:
                    collected.append(chunk.content)
                    yield _sse({"content": chunk.content})
                if chunk.done:
                    if chunk.meta and chunk.meta.get("model"):
                        model_used = chunk.meta["model"]
                    break
        except Exception as exc:  # engine unreachable / mid-stream failure
            yield _sse({"error": f"Translation failed: {exc}"})
            return

        output_text = "".join(collected).strip()
        # Auto-save on completion (Requirement 4.6 / decision Q13).
        saved = store.save_translation(
            pid, body.source_lang, body.raw_text, output_text, model_used
        )
        yield _sse({"done": True, "translation_id": saved.id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
