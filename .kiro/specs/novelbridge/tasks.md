# Implementation Plan

This plan builds NovelBridge incrementally, backend first, then frontend, then live
verification. Each task is small, testable, and references the requirements it satisfies.
Automated tests default to the mock engine so they run offline. Tasks are ordered so the app
is runnable (against the mock engine) as early as possible.

## Tasks

- [x] 1. Scaffold the monorepo and backend skeleton
  - Create `backend/` with `app/` package, `requirements.txt` (fastapi, uvicorn, httpx,
    pydantic, pydantic-settings), and `.env.example` with all config keys.
  - Add `app/config.py` (pydantic-settings) reading NB_ENGINE, OLLAMA_BASE_URL, OLLAMA_MODEL,
    OLLAMA_NUM_CTX, OLLAMA_THINK, NB_CONTEXT_BUDGET_TOKENS, NB_DB_PATH, NB_CORS_ORIGINS.
  - Add `app/main.py` with the FastAPI app factory, CORS, and a `GET /api/health` route.
  - _Requirements: 5.4, 6.3, 6.4, 6.5_

- [x] 2. Implement the storage layer
- [x] 2.1 Define the StorageService interface and domain models
  - Add `app/storage/base.py` (ABC) and `app/models.py` dataclasses/entities
    (Project, ReferenceChapter, GlossaryEntry, Translation) with UUID string ids.
  - _Requirements: 6.2_
- [x] 2.2 Implement the SQLite storage backend
  - Add `app/storage/schema.sql` (the four tables, foreign keys, ON DELETE CASCADE,
    unique(project_id, source_term)) and `app/storage/sqlite_store.py` implementing every
    interface method; initialize the DB from schema on first run.
  - _Requirements: 1.2, 1.3, 1.4, 2.1, 2.3, 3.1, 3.2, 3.4, 7.1, 7.2, 7.3_
- [x] 2.3 Write storage unit tests
  - Test CRUD for each entity against a temp SQLite file, cascade delete, and the glossary
    upsert/uniqueness rule.
  - _Requirements: 1.4, 3.4, 7.1_

- [x] 3. Implement the translation engine layer
- [x] 3.1 Define the TranslationEngine interface and data classes
  - Add `app/engines/base.py` with TranslationRequest, TranslationChunk, and the ABC
    (`stream`, `health`).
  - _Requirements: 5.1_
- [x] 3.2 Implement the MockEngine
  - Deterministic engine: emits a `[MOCK]` marker, applies glossary substitutions to the raw
    text, and streams the echo in small slices. No network.
  - _Requirements: 5.3_
- [x] 3.3 Implement the OllamaEngine
  - Async httpx call to `POST {base_url}/api/chat` with stream=true, think=false, and
    options.num_ctx; parse NDJSON chunks into TranslationChunk; strip residual
    `<think>...</think>`; implement `health` via `GET /api/tags`.
  - _Requirements: 5.2, 5.4, 4.3, 4.4_
- [x] 3.4 Add the engine factory and startup validation
  - `app/engines/factory.py` selects the engine from NB_ENGINE and fails fast with a clear
    message when required config is missing.
  - _Requirements: 5.5, 5.6_
- [x] 3.5 Write engine unit tests
  - MockEngine determinism; OllamaEngine parsing + think-stripping against a stubbed HTTP
    client replaying recorded NDJSON lines.
  - _Requirements: 5.2, 5.3_

- [x] 4. Implement the context builder and prompt
- [x] 4.1 Implement context_builder with token budgeting
  - `app/services/context_builder.py`: always include full glossary and full raw; fill the
    remaining budget with the tail of the most recent reference; set a truncation flag and
    prepend an omission note when trimming. Char-heuristic token estimate behind one function.
  - _Requirements: 4.1, 4.2, 2.5, 3.5_
- [x] 4.2 Implement prompt templates
  - `app/services/prompt.py`: system prompt (literary translator, glossary authoritative,
    match reference tone, output only translation) and the delimited user message builder.
  - _Requirements: 3.3, 4.1_
- [x] 4.3 Write context builder unit tests
  - Verify glossary + raw always retained, references trimmed to budget, truncation flag/note
    at boundary sizes, and empty-reference behavior.
  - _Requirements: 4.2, 2.5_

- [x] 5. Implement the HTTP API
- [x] 5.1 Project, reference, and glossary routes
  - `app/api/projects.py`: all CRUD routes per the API table, with Pydantic request models and
    422 validation for empty name / empty reference; glossary create as upsert.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.4_
- [x] 5.2 SSE translation route with auto-save
  - `app/api/translate.py`: `POST /api/projects/{id}/translate` returns text/event-stream,
    relays engine chunks as `data:` events, auto-saves the translation on completion, emits a
    terminal event with the translation id, and emits an `error` event (without losing input)
    on engine failure.
  - _Requirements: 4.1, 4.4, 4.5, 4.6, 13 (auto-save)_
- [x] 5.3 Translation history routes
  - `GET /api/projects/{id}/translations` and `GET /api/translations/{tid}`.
  - _Requirements: 4.6, 7.1_
- [x] 5.4 Write API tests
  - FastAPI TestClient: CRUD + validation errors; translate endpoint against MockEngine
    asserting the SSE event sequence and that a translation row is auto-saved.
  - _Requirements: 1.5, 2.4, 4.5, 4.6_

- [x] 6. Scaffold the frontend
  - Create `frontend/` via Vite (React + TypeScript), configure Tailwind + shadcn/ui and the
    `@` path alias, and set the Vite dev proxy for `/api` to the backend.
  - Add a typed API client and an SSE consumer utility in `src/api/`.
  - _Requirements: 6.1, 6.3_

- [x] 7. Build the project + sidebar shell
  - Sidebar listing projects with create/select/delete (confirm on delete); main area with
    tabs (References, Glossary, Translate). Empty states handled.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 8. Build the References and Glossary tabs
  - References: paste title + content to add, list, view, delete, with empty-input validation.
  - Glossary: add/edit/delete source_term + translation + optional note, with duplicate handling.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.4_

- [x] 9. Build the Translate workspace with live streaming
  - Separate raw-input and translated-output panes; source-language selector (zh/ja); submit to
    the SSE endpoint and render tokens live; in-progress indicator; preserve raw text on error;
    show saved state and surface "no context available" when the project has no references.
  - _Requirements: 4.1, 4.3, 4.4, 4.5, 4.6, 2.5_

- [x] 10. End-to-end verification and cleanup
  - Run backend + frontend locally; run the full test suite (mock engine); perform one live
    translation against the Ollama server (`qwen3.5:0.8b`) to confirm the real streaming path;
    add a top-level README with run instructions; remove any scratch files.
  - _Requirements: 4.1, 4.4, 5.2, 6.1_

## Post-PoC backlog (from testing feedback)

These extend the original plan after hands-on testing. Keep storage/engine behind their
interfaces, keep tests offline on the mock engine, flag major decisions for confirmation even
in autopilot, and make one local commit per task. Full context in
`.kiro/steering/tech.md` ("Planned work & known issues") and `frontend-plan.md`.

Note: `num_thread` (per-request CPU cap) is already implemented in config + the Ollama engine.

### Backend

- [x] 11. Max concurrent translations
  - Add `NB_MAX_CONCURRENT_TRANSLATIONS` to `config.py` (default 1) + `.env.example`/`.env`.
  - Enforce in `api/translate.py` with an `asyncio.Semaphore`; release on completion, error,
    and client disconnect. Decision (confirmed with author): **queue by awaiting the semaphore,
    with an `NB_QUEUE_TIMEOUT_SECONDS` (default 30) cap** that emits a busy SSE `error` instead
    of blocking forever. Also emits a `waiting for a free translation slot` info event.
  - Added `tests/test_concurrency.py` (mock engine with a delay) asserting the cap serializes
    (overlap==1 at cap 1, overlap==2 at cap 2) and that the queue timeout emits a busy error.

- [x] 12. Delete saved translations (endpoint)
  - `delete_translation(tid) -> bool` on `StorageService` + SQLite impl.
  - `DELETE /api/translations/{tid}` (204 / 404) in `api/projects.py`; tests added in
    `test_storage.py` (storage-level) and `test_api.py` (route-level).
  - Updated API tables in `tech.md`, `design.md`, and the root `README.md`.

- [x] 13. Fix reference-echo bug + restructure prompts (design + confirm first)
  - Diagnosed live (`qwen3.5:0.8b`): raw reference text dumped before a weak trailing
    instruction made the model continue/echo the reference. Restructured `services/prompt.py`
    into named builders (`build_translation_*`, `build_extraction_*`) with a strong preamble:
    translate ONLY the fenced raw chapter; reference is style-only and must never be reproduced;
    output only the translation.
  - References distilled at upload (confirmed design: engine call + columns on
    `reference_chapters` + resummarize endpoint). `TranslationEngine.extract_reference` returns
    a `ReferenceExtraction(summary, candidate_terms)` — deterministic in the mock, a non-stream
    `format=json` call in Ollama with a defensive parser. `context_builder.build()` now budgets
    summaries newest-first instead of raw tails. New `POST /api/references/{refId}/resummarize`;
    extraction runs synchronously on add (degrades gracefully on engine failure).
  - Tests: `test_prompt.py` (new), context-builder suite rewritten, mock/ollama extraction +
    parser tests, api add-reference + resummarize tests. Verified live on 4b (clean) and 0.8b
    (clean after a hardened raw-chapter instruction). Full suite offline: 44 pass.
  - Contract change flagged for frontend: `ReferenceChapter` gains `summary` + `candidate_terms`;
    new resummarize route.

- [ ] 14. English-first glossary matching (design discussion done; implementation pending author pick)
  - Glossary is for validation; users often know the English name, not the source term. Store
    English surface forms and fuzzy/alias-match against output (English↔source pairs, possibly
    harvested from task 13 `candidate_terms`). No heavy NLP deps. Depends on task 13 (shipped).
  - **Design options produced** (session design note). Axes + leaning recommendation:
    - Data model: A1 add optional `english_name` / **A2 make English the key, source optional** /
      A3 add `aliases` list for drift.
    - Matching (stdlib only): B1 substring / **B2 normalized exact** → **B3 `difflib` fuzzy**
      fallback with a tunable `NB_GLOSSARY_MATCH_THRESHOLD`.
    - When: **C1 on-demand `POST /api/projects/{id}/glossary/validate`** (raw text or
      `translation_id`) / C2 inline in translate SSE / C3 frontend-only.
    - Reference seeding: **D1 suggest-only chips** from `candidate_terms` / D3 harvest English
      only; avoid D2 auto-pair (small models align CN/JP↔EN poorly).
  - **Open decisions before building:** (1) data model A1/A2/A3; (2) do English entries steer the
    prompt or only validate after; (3) normalized-exact vs fuzzy from day one + threshold; (4)
    on-demand vs inline; (5) seed from references now or defer. Best landed with the frontend
    glossary-tab rework so the HTTP contract changes once.

- [ ] 15. Model picker (deferred; capture only)
  - `GET /api/models` proxying Ollama `/api/tags`, plus per-request model plumbing (engine
    already accepts `TranslationRequest.model`). Build after the frontend model-status indicator.

### Frontend

- [ ] 16. Dark mode (keep simple; confirm scope)
  - Toggle `dark` class on `<html>` with localStorage + `prefers-color-scheme` on first load;
    wire the sonner toaster theme without `next-themes`; unobtrusive toggle. No flash on load.

- [ ] 17. Delete saved translations (UI)
  - Per-row delete in `history-panel.tsx` via `ConfirmDialog`, calling task 12's endpoint.
    Reset panes if the loaded translation is deleted; refresh the project count.

- [ ] 18. Fix streaming scroll-follow
  - In `translate-tab.tsx`, only autoscroll when pinned near the bottom so users can scroll up
    mid-stream; optional "jump to latest"; respect reduced-motion.

- [ ] 19. Model-status indicator
  - Poll `GET /api/health`; show engine + model + reachable dot; make `engine=="mock"` obvious.
    Groundwork before the deferred model picker (task 15).
