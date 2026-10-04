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
