"""Concurrency-cap tests for the translate route.

Drives the ASGI app with httpx + ASGITransport so multiple SSE translations can be
truly in-flight at once, and asserts NB_MAX_CONCURRENT_TRANSLATIONS is honored.
Uses a slow mock engine that records how many streams overlap. Offline-only.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx

import app.api.translate as translate_mod
from app.config import Settings, get_settings
from app.deps import get_storage, get_translation_engine
from app.engines.base import (
    ReferenceExtraction,
    TranslationChunk,
    TranslationEngine,
    TranslationRequest,
)
from app.main import create_app
from app.storage.sqlite_store import SQLiteStorage


class _SlowConcurrencyEngine(TranslationEngine):
    """Mock engine that records entry/exit intervals so overlap can be detected.

    Each stream records when it starts and finishes work. We decrement the active
    counter at the end of the stream body (not in a generator ``finally``, which
    only runs on close/GC and would mis-time concurrency), so ``peak`` reflects
    how many streams were genuinely doing work at once.
    """

    name = "mock"

    def __init__(self, delay: float = 0.1) -> None:
        self._delay = delay
        self.active = 0
        self.peak = 0
        self.intervals: list[tuple[float, float]] = []

    async def stream(self, req: TranslationRequest) -> AsyncIterator[TranslationChunk]:
        start = asyncio.get_event_loop().time()
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(self._delay)
        yield TranslationChunk(content="hello", done=False)
        self.active -= 1
        self.intervals.append((start, asyncio.get_event_loop().time()))
        yield TranslationChunk(content="", done=True, meta={"model": "mock"})

    async def extract_reference(self, content, source_lang):
        return ReferenceExtraction(summary="", candidate_terms=[])

    async def extract_glossary(self, raw_text, output_text, source_lang, candidates=None, model=None):
        return []

    async def extract_style(self, content, source_lang):
        return ""

    async def health(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["slow-test"]


def _max_overlap(intervals: list[tuple[float, float]]) -> int:
    """Return the maximum number of intervals overlapping at any instant."""
    events: list[tuple[float, int]] = []
    for start, end in intervals:
        events.append((start, 1))
        events.append((end, -1))
    events.sort()
    cur = peak = 0
    for _, delta in events:
        cur += delta
        peak = max(peak, cur)
    return peak


def _build(tmp_path, *, limit: int, timeout: float, engine: TranslationEngine):
    settings = Settings(
        nb_engine="mock",
        nb_db_path=str(tmp_path / "concurrency.db"),
        nb_max_concurrent_translations=limit,
        nb_queue_timeout_seconds=timeout,
    )
    app = create_app(settings)
    store = SQLiteStorage(settings.nb_db_path)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_storage] = lambda: store
    app.dependency_overrides[get_translation_engine] = lambda: engine
    return app, store


def _make_project(store):
    return store.create_project("S", "zh").id


async def _run_translate(client: httpx.AsyncClient, pid: str) -> list[dict]:
    events: list[dict] = []
    async with client.stream(
        "POST",
        f"/api/projects/{pid}/translate",
        json={"raw_text": "x", "source_lang": "zh"},
    ) as resp:
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


def _reset_semaphores():
    translate_mod._semaphores.clear()


async def test_cap_of_one_serializes_translations(tmp_path):
    _reset_semaphores()
    engine = _SlowConcurrencyEngine(delay=0.15)
    app, store = _build(tmp_path, limit=1, timeout=5.0, engine=engine)
    pid = _make_project(store)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        results = await asyncio.gather(
            _run_translate(client, pid),
            _run_translate(client, pid),
        )

    # The engine must never have had two streams doing work at the same time.
    assert _max_overlap(engine.intervals) == 1
    # Both requests still completed successfully.
    for events in results:
        assert any(e.get("done") for e in events)
    # Both auto-saved.
    assert len(store.list_translations(pid)) == 2


async def test_cap_of_two_allows_overlap(tmp_path):
    _reset_semaphores()
    engine = _SlowConcurrencyEngine(delay=0.15)
    app, store = _build(tmp_path, limit=2, timeout=5.0, engine=engine)
    pid = _make_project(store)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        await asyncio.gather(
            _run_translate(client, pid),
            _run_translate(client, pid),
        )

    # With two slots the two streams are allowed to overlap.
    assert _max_overlap(engine.intervals) == 2


async def test_queue_timeout_emits_error(tmp_path):
    _reset_semaphores()
    # Cap 1 with a tiny timeout: the second request can't get a slot in time and
    # must receive an SSE error instead of hanging forever.
    engine = _SlowConcurrencyEngine(delay=0.4)
    app, store = _build(tmp_path, limit=1, timeout=0.05, engine=engine)
    pid = _make_project(store)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        results = await asyncio.gather(
            _run_translate(client, pid),
            _run_translate(client, pid),
        )

    # Exactly one request succeeded; the other timed out waiting for a slot.
    done_count = sum(1 for events in results for e in events if e.get("done"))
    error_count = sum(
        1
        for events in results
        for e in events
        if e.get("error") and "busy" in e["error"].lower()
    )
    assert done_count == 1
    assert error_count == 1
    # Only the successful one was auto-saved.
    assert len(store.list_translations(pid)) == 1
