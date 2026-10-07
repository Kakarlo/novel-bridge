# NovelBridge — Tech Stack & Backend Conventions

## Stack

- **Backend**: Python 3.13, FastAPI 0.115.x, Uvicorn, httpx (async), Pydantic v2 + pydantic-settings, pytest + pytest-asyncio. Virtualenv at `backend/.venv`.
- **Frontend**: Vite + React + TypeScript + Tailwind v4 + shadcn/ui (Nova preset). Node 24 / npm 11.
- **Storage**: SQLite via stdlib `sqlite3`, behind `StorageService` (ABC). Frontend also implements `IndexedDbStorage` (Dexie) for the hosted/idb build.
- **Translation engines**: pluggable `TranslationEngine` (ABC); `OllamaEngine`, `GeminiEngine`, `OpenRouterEngine`, `MockEngine` (offline/tests).

## Backend layout (`backend/app/`)

- `config.py` — `Settings` (pydantic-settings), `get_settings()` cached.
- `main.py` — `create_app()` factory; CORS; `/api/health` + `/api/models`; registers routers.
- `models.py` — entities + Pydantic request/response models; `SourceLang = Literal["zh","ja"]`.
- `deps.py` — `get_storage()`, `get_translation_engine()`, `resolve_request_engine()`.
- `storage/` — `base.py` (ABC), `sqlite_store.py`, `schema.sql`.
- `engines/` — `base.py`, `mock_engine.py`, `ollama_engine.py`, `gemini_engine.py`, `openrouter_engine.py`, `factory.py`.
- `services/` — `prompt.py`, `context_builder.py`, `term_match.py`, `noun_extract.py`, `source_terms.py` (gated), `pronoun_check.py` (gated), `chapter_number.py`.
- `api/` — `projects.py` (CRUD + style/glossary/references/translations), `translate.py` (SSE).

## Config / environment variables

See `backend/.env.example` for all keys. Key ones:

| Var                              | Default                  | Notes                              |
| -------------------------------- | ------------------------ | ---------------------------------- |
| `NB_ENGINE`                      | `ollama`                 | `ollama\|mock\|openrouter\|gemini` |
| `OLLAMA_BASE_URL`                | `http://localhost:11434` | Overridable per-request via picker |
| `OLLAMA_MODEL`                   | `qwen3.5:0.8b`           |                                    |
| `NB_CORS_ORIGINS`                | `http://localhost:5173`  | Comma-separated                    |
| `NB_MAX_CONCURRENT_TRANSLATIONS` | `1`                      | asyncio.Semaphore cap              |
| `NB_QUEUE_TIMEOUT_SECONDS`       | `30`                     | Busy-error timeout                 |
| `NB_DB_PATH`                     | `./novelbridge.db`       | Only used on the api-storage path  |

Cloud engines: `OPENROUTER_API_KEY`, `GEMINI_API_KEY` (users can also supply keys per-request via `X-LLM-Api-Key` header; the picker in the frontend drives this).

**Gotcha:** `get_translation_engine()` is `@lru_cache` — a restart is required to pick up `.env` changes. A background terminal can leak `$env:NB_ENGINE="mock"` into later runs; check with `GET /api/health`.

## HTTP API (current contract)

All routes under `/api/`. Do not break without updating the frontend.

- `GET/POST /api/projects`; `GET/DELETE /api/projects/{pid}`
- `GET/POST /api/projects/{pid}/references`; `DELETE /api/references/{refId}`; `POST /api/references/{refId}/redetect`; `POST /api/references/{refId}/resolve-term`
- `GET/POST /api/projects/{pid}/glossary`; `PUT/DELETE /api/glossary/{id}`; `PATCH /api/glossary/{id}/status`
- `POST /api/projects/{pid}/extract-style` → `{style_profile}`. Stateless when `content` is in body (idb path); DB-backed otherwise.
- `POST /api/projects/{pid}/translate` — SSE. Stateless when `glossary`+`style_profile` are in body (`save=false` → no server auto-save). `selection: {provider, model, ollama_base_url}` for per-request engine override.
- `GET /api/projects/{pid}/translations`; `GET/DELETE /api/translations/{tid}`
- `POST /api/translations/{tid}/extract-glossary` → `GlossaryPairSuggestion[]`. Stateless when `raw_text`+`output_text` in body.
- `GET /api/translations/{tid}/matches` — recompute term occurrences on demand.
- `GET /api/translations/{tid}/source-terms` — gated by `NB_SOURCE_TERMS`.
- `GET /api/translations/{tid}/pronoun-drift` — gated by `NB_PRONOUN_CHECK`.
- `POST /api/detect-names` — stateless spaCy NER; body `{content}` → `{detected_names}`.
- `GET /api/health?provider=&ollama_base_url=` — probes live engine reachability.
- `GET /api/models?provider=&ollama_base_url=` — lists available models.

## Ollama specifics

- Endpoint: `POST /api/chat`, streaming NDJSON.
- Always send `"think": false`; strip `<think>...</think>` as guard.
- `num_ctx` + `num_thread` must be passed in `options` (not inherited).

## Frontend storage backends

`VITE_STORAGE_BACKEND=idb` (hosted build, `.env.production`) uses IndexedDB via Dexie — no user data on the server. `api` (default, `.env.local` dev) uses the SQLite-backed REST API. The `StorageService` interface is the seam; components never call the backend directly (except compute endpoints like translate/extract-style).

## Conventions

- Business logic stays out of route handlers — use the storage + engine interfaces.
- Tests use the mock engine + a temp SQLite file; run offline: `cd backend; .\.venv\Scripts\python.exe -m pytest -q`
- Windows PowerShell: separate commands with `;`, env vars via `$env:VAR="..."`.
- `Out-File -Encoding utf8` writes a BOM — use `[System.IO.File]::WriteAllText(path, json)` for curl body files.
- `$pid` is a reserved PowerShell variable — use another name for project ids.

## Next task

Task 22 — user-editable prompts. See `tasks.md`.
