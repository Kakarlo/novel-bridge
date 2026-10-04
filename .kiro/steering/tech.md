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
- `GET/POST /api/projects/{id}/references`; `DELETE /api/references/{refId}`.
  A `ReferenceChapter` now also carries `summary` (string|null) and `candidate_terms`
  (string[]), derived by the engine at upload time (POST runs extraction synchronously).
- `POST /api/references/{refId}/resummarize` — re-run extraction for one reference; returns the
  updated `ReferenceChapter` (200), 404 if missing, 502 if the engine extraction fails.
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
- `GET /api/health` — returns `{status, reachable, engine, model}`. **Now probes the actual
  engine** (`engine.health()`: Ollama pings `/api/tags`, mock returns True) rather than echoing
  config, so a disconnected LLM server reports `reachable=false` / `status="unreachable"`. The
  frontend polls this; the indicator shows engine-reachable (green) / backend-up-but-LLM-down
  (amber) / backend-down (red), and surfaces `engine=="mock"` prominently so a leaked
  `NB_ENGINE=mock` is obvious.
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
- **Reference-echo bug (DONE):** attaching a reference used to make the model echo/continue it
  instead of translating the raw input (reproduced live on `qwen3.5:0.8b`). Root cause: raw
  reference text was dumped as a large block before a weak trailing instruction, so the model
  continued it. Fixed by (a) restructuring `services/prompt.py` into named builders
  (`build_translation_system_prompt`/`build_translation_messages`,
  `build_extraction_system_prompt`/`build_extraction_messages`) with a strong preamble —
  translate ONLY the fenced raw chapter, reference is style-only and must never be reproduced,
  output only the translation — and (b) feeding DERIVED context (summary + candidate terms)
  instead of raw reference text. Verified live: 4b translates cleanly; 0.8b too after a hardened
  raw-chapter instruction.
- **References as summary + candidate glossary (DONE):** references are distilled at upload time
  via `TranslationEngine.extract_reference(content, source_lang) -> ReferenceExtraction`
  (`summary`, `candidate_terms`). Mock impl is deterministic/offline; Ollama impl makes one
  non-streaming `format=json` `/api/chat` call with a defensive JSON parser + heuristic
  fallback. Stored on `reference_chapters` (`summary`, `candidate_terms` columns; additive
  migration). `context_builder.build()` now budgets summaries newest-first instead of raw tails.
  Extraction runs synchronously on POST reference and on `POST /api/references/{refId}/resummarize`;
  failures degrade gracefully (reference saved with no summary; resummarize later).
- **English-first glossary with in-context approval (ACTIVE MAJOR FEATURE — spec task 14):**
  references are English, so extracted candidate terms are English surface forms. The user adds
  a name by its **English form alone**; occurrences in a translation are flagged for
  **approve/reject**, and approved terms steer the prompt as preferred spellings. Redefine
  `glossary_entries` English-first (`surface_form` req, `source_term` nullable, `status`
  candidate|approved|rejected; unique on `surface_form COLLATE NOCASE`). **No migration — no
  production data; redefine `schema.sql` and recreate the dev DB.** Occurrence matching is
  stdlib exact whole-word, case-insensitive (fuzzy is a flagged follow-up). Phased build in
  `tasks.md` (14.1–14.7). Flag the open design decisions before building.
- **Model status probe (DONE):** `GET /api/health` now calls `engine.health()` and reports real
  reachability (see the API section). The frontend indicator keys off `reachable`.
- **Model picker (deferred):** choose the model per request from a list. Backend-first
  (`GET /api/models` proxying Ollama `/api/tags` + request plumbing). The health/model-status
  indicator (shipped) is the groundwork.
- **Bring-your-own LLM API token (future track — do not build yet):** add a hosted-model engine
  behind the `TranslationEngine` interface so users can translate with an API key instead of a
  local Ollama. Local-first still holds; accounts/cloud (behind `StorageService`) only if
  adoption warrants it. Don't block this in task 14.

Hard rule for all of the above: flag major decisions for confirmation even in autopilot, keep
storage/engine behind their interfaces, keep tests offline on the mock engine, one commit per
task.
