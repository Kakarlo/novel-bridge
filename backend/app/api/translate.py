"""SSE translation endpoint with auto-save (Requirements 4.1, 4.4, 4.5, 4.6)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.config import Settings, get_settings
from app.deps import get_request_api_key, get_storage, get_translation_engine, resolve_request_engine
from app.engines.base import TranslationEngine, TranslationRequest
from app.models import TranslateRequest
from app.services import context_builder as cb
from app.services.term_match import find_occurrences
from app.storage.base import StorageService

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["translate"])

# zh/ja source -> English output token-expansion factor, for the debug occupancy estimate
# only. CJK is dense (one char ~ one word), so the English translation tends to use MORE
# tokens than the source under the char/3 heuristic; ~1.4x is a rough middle of the usual
# 1.2-1.5 range. Observability only — nothing branches on this. ponytail: a heuristic with a
# known ceiling; refine from the measured peaks the debug line now reports if it drifts.
_OUTPUT_TOKEN_RATIO = 1.4

# One semaphore per configured cap. Keyed by the limit so tests that spin up an
# app with a different NB_MAX_CONCURRENT_TRANSLATIONS get a correctly-sized gate
# without leaking state across configurations.
_semaphores: dict[int, asyncio.Semaphore] = {}


def _get_semaphore(limit: int) -> asyncio.Semaphore:
    limit = max(1, limit)
    sem = _semaphores.get(limit)
    if sem is None:
        sem = asyncio.Semaphore(limit)
        _semaphores[limit] = sem
    return sem


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/projects/{pid}/translate")
def translate(
    pid: str,
    body: TranslateRequest,
    store: StorageService = Depends(get_storage),
    fallback_engine: TranslationEngine = Depends(get_translation_engine),
    settings: Settings = Depends(get_settings),
    api_key: str | None = Depends(get_request_api_key),
):
    project = store.get_project(pid)
    if not project:
        raise HTTPException(404, "Project not found")

    # --- Per-request engine resolution (BYO-key multi-user path) ----------------
    # Provider/model come from the body selection (already modeled as {provider, model}).
    # The API key comes from the X-LLM-Api-Key header (never in the body).
    # resolve_request_engine handles validation (400 unknown provider, 401 missing key)
    # and falls back to the env-configured/test-injected engine when no creds are supplied.
    requested_provider = body.selection.provider if body.selection else None
    requested_model = body.selection.model if body.selection else None
    engine = resolve_request_engine(
        provider=requested_provider,
        model=requested_model,
        api_key=api_key,
        settings=settings,
        fallback=fallback_engine,
    )

    glossary = store.list_glossary(pid)
    references = store.list_references(pid)
    built = cb.build(
        glossary, references, body.raw_text, settings.nb_context_budget_tokens
    )

    # Debug: estimated context occupancy, so OLLAMA_NUM_CTX can be sized from real data.
    # The window is shared by PROMPT + GENERATED OUTPUT, and for a full-chapter translation
    # the output is the same order as the source (often larger). So the number that actually
    # risks overflow is the PEAK = assembled input + projected output, not the input alone.
    # Projected output ~= source tokens * _OUTPUT_TOKEN_RATIO (zh/ja -> en tends to expand in
    # token count). estimate_tokens is the same char/3 heuristic the budgeter uses.
    raw_tok = cb.estimate_tokens(body.raw_text)
    ref_tok = cb.estimate_tokens(built.reference_context)
    assembled = raw_tok + ref_tok
    projected_output = int(raw_tok * _OUTPUT_TOKEN_RATIO)
    peak = assembled + projected_output
    logger.info(
        "translate context: raw=%d ref=%d assembled~%d + projected_output~%d = peak~%d "
        "tokens (budget=%d, NUM_CTX=%d, raw_chars=%d, truncated=%s)",
        raw_tok,
        ref_tok,
        assembled,
        projected_output,
        peak,
        settings.nb_context_budget_tokens,
        settings.ollama_num_ctx,
        len(body.raw_text),
        built.truncated,
    )

    req = TranslationRequest(
        raw_text=body.raw_text,
        source_lang=body.source_lang,
        glossary=glossary,
        reference_context=built.reference_context,
        model=requested_model,
        style_profile=project.style_profile or "",
    )

    sem = _get_semaphore(settings.nb_max_concurrent_translations)
    timeout = settings.nb_queue_timeout_seconds

    async def event_stream() -> AsyncIterator[str]:
        collected: list[str] = []
        # Best pre-stream guess at the model name for auto-save: an explicit per-request
        # override wins, else the engine's configured default (per-engine). The engine's
        # `done` chunk may overwrite this below with the model it actually used (authoritative).
        _defaults = {
            "ollama": settings.ollama_model,
            "openrouter": settings.openrouter_model,
            "gemini": settings.gemini_model,
        }
        default_model = _defaults.get(engine.name, engine.name)
        model_used = requested_model or default_model

        # Cap simultaneous in-flight translations. If a slot isn't free, queue by
        # awaiting the semaphore, but give up after `timeout` so the client isn't
        # left waiting indefinitely.
        if sem.locked():
            yield _sse({"info": "waiting for a free translation slot"})
        try:
            await asyncio.wait_for(sem.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            yield _sse(
                {
                    "error": (
                        "Server busy: too many translations in progress. "
                        "Please try again shortly."
                    )
                }
            )
            return

        try:
            if built.truncated:
                yield _sse(
                    {"info": "reference context truncated to fit the model window"}
                )
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
            done_event: dict = {"done": True, "translation_id": saved.id}
            # Opt-in in-context review (task 14): detect glossary terms in the output and
            # fold them into the terminal event so the client can offer approve/reject.
            # Detection only — the translation itself is never modified.
            if body.review_terms:
                matches = find_occurrences(output_text, glossary)
                done_event["matches"] = [m.model_dump() for m in matches]
            yield _sse(done_event)
        finally:
            # Release on completion, error, or client disconnect (GeneratorExit).
            sem.release()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
