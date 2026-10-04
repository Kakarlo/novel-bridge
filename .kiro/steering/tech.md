# NovelBridge — Tech Stack & Backend Conventions

## Stack

- **Backend**: Python 3.13, FastAPI 0.115.x, Uvicorn, httpx (async), Pydantic v2 +
  pydantic-settings, pytest + pytest-asyncio. Virtualenv at `backend/.venv`.
- **Frontend** (planned): Vite + React + TypeScript + Tailwind + shadcn/ui. Node 24 / npm 11.
- **Storage**: SQLite via stdlib `sqlite3`, behind `StorageService` (ABC).
- **Translation engine**: pluggable `TranslationEngine` (ABC); `OllamaEngine` default,
  `MockEngine` for offline/tests.

## Backend layout (`backend/app/`)

- `config.py` — `Settings` (pydantic-settings), `get_settings()` cached. All config via env/.env.
- `main.py` — `create_app()` factory; fail-fast engine validation at startup; CORS; registers routers.
- `models.py` — entities (uuid hex ids) + Pydantic request models; `SourceLang = Literal["zh","ja"]`.
- `deps.py` — cached providers `get_storage()`, `get_translation_engine()`.
- `storage/` — `base.py` (interface), `sqlite_store.py`, `schema.sql` (4 tables, FKs,
  `ON DELETE CASCADE`, `UNIQUE(project_id, source_term)`).
- `engines/` — `base.py` (TranslationRequest/Chunk/Engine), `mock_engine.py`, `ollama_engine.py`,
  `factory.py` (`EngineConfigError`).
- `services/` — `prompt.py` (system prompt + `build_messages`), `context_builder.py`
  (`estimate_tokens`, `build()`).
- `api/` — `projects.py` (CRUD), `translate.py` (SSE translate + auto-save).

## Config / environment variables

`NB_ENGINE` (ollama|mock), `OLLAMA_BASE_URL` (default `http://192.168.254.22:11434`),
`OLLAMA_MODEL`, `OLLAMA_NUM_CTX`, `OLLAMA_NUM_THREAD` (caps CPU threads per request so the box
isn't maxed and sessions can coexist), `OLLAMA_THINK` (false), `NB_CONTEXT_BUDGET_TOKENS`,
`NB_MAX_CONCURRENT_TRANSLATIONS` (default 1; caps PARALLEL in-flight translations),
`NB_QUEUE_TIMEOUT_SECONDS` (default 30; how long a queued translate request waits for a free
slot before giving up with a busy SSE error), `NB_DB_PATH` (`./novelbridge.db`),
`NB_CORS_ORIGINS` (`http://localhost:5173`). See `backend/.env.example`. The committed `.env`
may run a larger model (e.g. `qwen3.5:4b`) with a bigger context window; `.env.example`
documents every key.

**Concurrency cap (shipped):** `NB_MAX_CONCURRENT_TRANSLATIONS` is enforced in the translate
route with a per-cap `asyncio.Semaphore`. A request queues (awaits the semaphore) and, if a slot
frees in time, streams normally; if the wait exceeds `NB_QUEUE_TIMEOUT_SECONDS` it emits a busy
`error` event instead of blocking forever. The slot is released on completion, error, timeout,
and client disconnect.

## HTTP API (contract — do not break without updating the frontend)

- `GET/POST /api/projects`; `GET/DELETE /api/projects/{id}` (GET returns `{project, counts}`)
- `GET/POST /api/projects/{id}/references`; `DELETE /api/references/{refId}`
- `GET/POST /api/projects/{id}/glossary`; `PUT/DELETE /api/glossary/{entryId}`
  (POST upserts on duplicate `source_term`)
- `POST /api/projects/{id}/translate` — **SSE** `text/event-stream`. Events:
  `data: {"content":"..."}` repeated, optional `data: {"info":"..."}` (truncation notice, or
  `"waiting for a free translation slot"` when queued behind the concurrency cap), terminal
  `data: {"done":true,"translation_id":"..."}`, or `data: {"error":"..."}` on failure. When the
  concurrency cap is saturated and no slot frees within `NB_QUEUE_TIMEOUT_SECONDS`, the stream
  emits a busy `error` event ("Server busy: too many translations in progress...") and closes
  (HTTP stays 200 for the event-stream).
- `GET /api/projects/{id}/translations`; `GET /api/translations/{tid}`
- `DELETE /api/translations/{tid}` — 204 on success, 404 when missing. Backed by
  `delete_translation` on `StorageService` + the SQLite impl.
- `GET /api/health` — returns `{status, engine, model}`. The frontend polls this for a
  model-status indicator; surface `engine=="mock"` prominently so a leaked `NB_ENGINE=mock`
  is obvious.
- `GET /api/models` — **planned**, proxy of Ollama `GET /api/tags`, for the future model picker.

## Ollama specifics (verified)

- Native endpoint `POST /api/chat`, streaming NDJSON: `{"message":{"content":...},"done":false}`
  … final `{"done":true, ...stats}`.
- Always send `"think": false` (suppresses Qwen reasoning); strip `<think>...</think>` as a guard.
- `num_ctx` MUST be passed in `options`; it is not inherited from Open WebUI. `num_thread` is
  also passed in `options` to cap CPU usage per request.
- Models available on the server: `qwen3.5:0.8b` (fast/rough), `qwen3.5:4b` (good; ~75s/chapter
  CPU), `qwen3.5:9b` (best; ~112s/chapter CPU). Swap via `OLLAMA_MODEL`, no code change. The
  engine already accepts a per-request `model` (`TranslationRequest.model`) — the future model
  picker only needs a listing endpoint + request plumbing, no engine change.

## Conventions

- Keep business logic out of route handlers; use the storage + engine interfaces.
- Tests default to the **mock engine** and a temp SQLite file so the suite runs offline.
- Run tests: `cd backend; .\.venv\Scripts\python.exe -m pytest -q`.
- Windows/PowerShell: separate commands with `;`; for curl JSON use `--data-binary @file`
  (inline `-d` breaks on quoting). Use `$env:VAR="..."` for env vars.
- Do not start long-running servers in a blocking shell; run uvicorn as a background process.
- **Gotcha:** `Out-File -Encoding utf8` writes a BOM that breaks Ollama's JSON parser; write
  curl body files with `[System.IO.File]::WriteAllText(path, json)` instead.
- **Gotcha:** `$pid` is a reserved PowerShell variable — use another name for a project id.
- **Gotcha:** a background terminal can leak `$env:NB_ENGINE="mock"` into later runs; confirm
  the running engine via `GET /api/health` (look for `engine`).

## Planned work & known issues (next sessions)

Treat `.kiro/specs/novelbridge/tasks.md` as the live task list; these are the agreed directions.

- **Concurrency cap (DONE):** `NB_MAX_CONCURRENT_TRANSLATIONS` (default 1) enforced with an
  `asyncio.Semaphore` in `api/translate.py`, released on completion/error/timeout/disconnect.
  Queues with a `NB_QUEUE_TIMEOUT_SECONDS` cap (default 30) that emits a busy SSE error rather
  than blocking indefinitely. `num_thread` (already shipped) limits CPU _per request_; this
  limits _parallel_ requests.
- **Delete saved translations (DONE):** `delete_translation` on the storage interface + SQLite
  impl, and `DELETE /api/translations/{tid}` (204/404). The frontend delete UI (task 17) can
  now build on it.
- **Reference-echo bug (prompting):** when a reference chapter is attached, the model tends to
  echo/continue the reference instead of translating the raw input. Fix in `services/prompt.py`
  - `services/context_builder.py`. Direction: restructure into a small set of named, labeled
    prompts with a strong goal/output-format preamble — translate ONLY the raw chapter; the
    reference is for style/consistency and must never be reproduced; output only the translation.
- **References as summary + candidate glossary:** rather than dumping raw reference text,
  derive a short summary and candidate glossary entries from a reference. Approach (separate
  engine call vs. heuristic) and any new storage field/endpoint need a design note + author
  confirmation before building.
- **Glossary = validation, not entry (English-first matching):** the author's model is that the
  glossary tab validates terms; users often know the English name, not the source term. Explore
  storing English surface forms and fuzzy/alias-matching against model output (English↔source
  pairs, possibly harvested from reference summaries). Design discussion first; depends on the
  reference-summary work. No heavy NLP deps in the PoC.
- **Model picker (deferred):** choose the Ollama model per request from a list. Backend-first
  (`GET /api/models` proxying Ollama `/api/tags` + request plumbing); the frontend adds a
  health/model-status indicator before any picker.

Hard rule for all of the above: flag major decisions for confirmation even in autopilot, keep
storage/engine behind their interfaces, keep tests offline on the mock engine, one commit per
task.
