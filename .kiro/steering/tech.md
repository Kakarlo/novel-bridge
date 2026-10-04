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
`OLLAMA_MODEL` (default `qwen3.5:0.8b`), `OLLAMA_NUM_CTX` (16384), `OLLAMA_THINK` (false),
`NB_CONTEXT_BUDGET_TOKENS` (12000), `NB_DB_PATH` (`./novelbridge.db`),
`NB_CORS_ORIGINS` (`http://localhost:5173`). See `backend/.env.example`.

## HTTP API (contract — do not break without updating the frontend)

- `GET/POST /api/projects`; `GET/DELETE /api/projects/{id}` (GET returns `{project, counts}`)
- `GET/POST /api/projects/{id}/references`; `DELETE /api/references/{refId}`
- `GET/POST /api/projects/{id}/glossary`; `PUT/DELETE /api/glossary/{entryId}`
  (POST upserts on duplicate `source_term`)
- `POST /api/projects/{id}/translate` — **SSE** `text/event-stream`. Events:
  `data: {"content":"..."}` repeated, optional `data: {"info":"..."}` (truncation notice),
  terminal `data: {"done":true,"translation_id":"..."}`, or `data: {"error":"..."}` on failure.
- `GET /api/projects/{id}/translations`; `GET /api/translations/{tid}`
- `GET /api/health`

## Ollama specifics (verified)

- Native endpoint `POST /api/chat`, streaming NDJSON: `{"message":{"content":...},"done":false}`
  … final `{"done":true, ...stats}`.
- Always send `"think": false` (suppresses Qwen reasoning); strip `<think>...</think>` as a guard.
- `num_ctx` MUST be passed in `options`; it is not inherited from Open WebUI.
- Models available on the server: `qwen3.5:0.8b` (fast/rough), `qwen3.5:4b` (good; ~75s/chapter
  CPU), `qwen3.5:9b` (best; ~112s/chapter CPU). Swap via `OLLAMA_MODEL`, no code change.

## Conventions

- Keep business logic out of route handlers; use the storage + engine interfaces.
- Tests default to the **mock engine** and a temp SQLite file so the suite runs offline.
- Run tests: `cd backend; .\.venv\Scripts\python.exe -m pytest -q`.
- Windows/PowerShell: separate commands with `;`; for curl JSON use `--data-binary @file`
  (inline `-d` breaks on quoting). Use `$env:VAR="..."` for env vars.
- Do not start long-running servers in a blocking shell; run uvicorn as a background process.
