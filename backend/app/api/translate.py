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
    # Stateless signal (task 23.4b/c): a client-supplied `glossary` means the browser
    # (IndexedDB backend) owns the data and drives this request, so there is NO server-side
    # project to read — skip the project lookup and its 404 guard entirely. On the DB-backed
    # path (glossary omitted) we still require the project to exist and read its style profile.
    stateless = body.glossary is not None
    project = None if stateless else store.get_project(pid)
    if not stateless and not project:
        raise HTTPException(404, "Project not found")

    # --- Per-request engine resolution (BYO-key multi-user path) ----------------
    # Provider/model come from the body selection (already modeled as {provider, model}).
    # The API key comes from the X-LLM-Api-Key header (never in the body).
    # resolve_request_engine handles validation (400 unknown provider, 401 missing key)
    # and falls back to the env-configured/test-injected engine when no creds are supplied.
    requested_provider = body.selection.provider if body.selection else None
    requested_model = body.selection.model if body.selection else None
    requested_ollama_url = body.selection.ollama_base_url if body.selection else None
    engine = resolve_request_engine(
        provider=requested_provider,
        model=requested_model,
        api_key=api_key,
        settings=settings,
        fallback=fallback_engine,
        ollama_base_url=requested_ollama_url,
    )

    # --- Stateless context resolution (task 23.4b) -----------------------------
    # The local-first (IndexedDB) client owns the data and ships it in the body, so the server
    # does no storage read when `glossary`/`style_profile` are supplied. When they're omitted
    # (today's API-backend clients) the server falls back to loading from storage by `pid`.
    glossary = body.glossary if body.glossary is not None else store.list_glossary(pid)
    # On the stateless path `project` is None, but the idb client always ships `style_profile`
    # (23.4b); fall back to "" if it somehow didn't. On the DB path read it off the project.
    style_profile = (
        body.style_profile
        if body.style_profile is not None
        else ((project.style_profile or "") if project else "")
    )
    # References only feed the DERIVED reference context used for budgeting/notice. On the
    # stateless (body-driven) path the browser doesn't ship references — the project-level
    # style profile replaced per-reference summaries — so skip the storage read entirely when
    # the client drove the glossary. Only the API-storage path still consults references.
    references = [] if stateless else store.list_references(pid)
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
        # reference_context=built.reference_context,
        model=requested_model,
        style_profile=style_profile,
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
            # Auto-save on completion (Requirement 4.6 / decision Q13), UNLESS the client
            # drives persistence itself (local-first idb backend sends save=false and writes
            # the result to IndexedDB from the `done` event — task 23.4a/b). When save=false
            # the server stays stateless: no storage write, and translation_id is null.
            translation_id = None
            if body.save:
                saved = store.save_translation(
                    pid, body.source_lang, body.raw_text, output_text, model_used
                )
                translation_id = saved.id
            done_event: dict = {"done": True, "translation_id": translation_id}
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
