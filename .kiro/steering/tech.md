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
  A `ReferenceChapter` carries `summary` (string|null), `candidate_terms` (string[], from the
  engine), and `detected_names` (string[], from a deterministic rule-based proper-noun pass —
  field-fix #2 — kept separate from the AI terms). POST runs the rule pass + engine extraction
  synchronously; the detected names are also fed to the extraction prompt as hints.
- `POST /api/references/{refId}/resummarize` — re-run extraction for one reference; returns the
  updated `ReferenceChapter` (200), 404 if missing, 502 if the engine extraction fails.
- `GET/POST /api/projects/{id}/glossary`; `PUT/DELETE /api/glossary/{entryId}`.
  Glossary is **English-first** (task 14): entries have `surface_form` (English, required),
  `source_term` (nullable), `status` (`candidate|approved|rejected`), `category`
  (`character|title|term`), `gender` (`male|female|unknown`, nullable), `note`, `created_at`.
  POST upserts on `surface_form` (case-insensitive): a paired entry (`source_term` set) defaults
  to `approved`, an English-only add defaults to `candidate`; an explicit `status` wins.
- `PATCH /api/glossary/{entryId}/status` — approve/reject a term (`{status}`); 200 with the
  updated entry, 404 if missing. This is the in-context review action.
- `POST /api/projects/{id}/translate` — **SSE** `text/event-stream`. Request body may set
  `review_terms: true` (opt-in in-context review; default false). Events:
  `data: {"content":"..."}` repeated, optional `data: {"info":"..."}` (truncation notice, or
  `"waiting for a free translation slot"` when queued behind the concurrency cap), terminal
  `data: {"done":true,"translation_id":"...","matches":[...]}` (the `matches` array is present
  only when `review_terms` was true — each is a `TermMatch`: `term_id`, `surface_form`,
  `status`, `category`, `count`, `snippets`), or `data: {"error":"..."}` on failure. When the
  concurrency cap is saturated and no slot frees within `NB_QUEUE_TIMEOUT_SECONDS`, the stream
  emits a busy `error` event ("Server busy: too many translations in progress...") and closes
  (HTTP stays 200 for the event-stream).
  **Stateless (local-first) body fields — task 23.4b, backward-compatible:** the body may also
  carry `glossary` (a full `GlossaryEntry[]`), `style_profile` (string, `""` = none), and
  `save` (bool, default `true`). When `glossary`/`style_profile` are present the server uses
  them verbatim and does **no** storage read (references are skipped on that path too); omitted
  → the server loads the glossary + style profile from the DB by `{id}` as before. `save:false`
  → the server auto-saves **nothing** and `done.translation_id` is **`null`** (the IndexedDB
  client persists the result client-side per 23.4a). The API-storage frontend sends none of
  these, so its behavior is unchanged (DB load + server auto-save, non-null `translation_id`).
  The `{id}` path segment and the pure-CRUD routes remain for now; dropping them is task 23.4e.
- `GET /api/projects/{id}/translations`; `GET /api/translations/{tid}`
- `GET /api/translations/{tid}/matches` — re-run occurrence detection against a saved
  translation using the project's **current** glossary; returns `TermMatch[]` (200), 404 when
  missing. Recomputed on demand (not stored); detection only, never rewrites the translation.
- `DELETE /api/translations/{tid}` — 204 on success, 404 when missing. Backed by
  `delete_translation` on `StorageService` + the SQLite impl.
- `GET /api/health` — returns `{status, reachable, engine, model}`. **Now probes the actual
  engine** (`engine.health()`: Ollama pings `/api/tags`, mock returns True) rather than echoing
  config, so a disconnected LLM server reports `reachable=false` / `status="unreachable"`. The
  frontend polls this; the indicator shows engine-reachable (green) / backend-up-but-LLM-down
  (amber) / backend-down (red), and surfaces `engine=="mock"` prominently so a leaked
  `NB_ENGINE=mock` is obvious.
- `GET /api/models` — **shipped (listing only)**. Returns `{models, current}`: `models` from
  `engine.list_models()` (Ollama parses `/api/tags`, sorted, `[]` when unreachable; mock
  `["mock"]`), `current` is the configured `OLLAMA_MODEL`. Not gated. The engine already honors
  a per-request `TranslationRequest.model`, but the translate REQUEST BODY does not yet carry a
  `model` field — picking a model per request is a pending small backend add (see Model picker
  below). Contract is single-provider today; see the multi-provider target under BYO-token.

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
- **English-first glossary with in-context approval (ACTIVE MAJOR FEATURE — spec task 14 —
  table stakes, not the novelty):** references are English, so extracted candidate terms are
  English surface forms. The user adds a name by its **English form alone**; occurrences in a
  translation are flagged for **approve/reject**, and approved terms steer the prompt as
  preferred spellings (a _guide_, not a find-and-replace — matching only detects, never
  rewrites). Settled decisions (Phase 0, confirmed with the author):
  - Redefine `glossary_entries` English-first: `surface_form` (req), `source_term` (nullable),
    `status` (`candidate|approved|rejected`, default `candidate`), **`category`
    (`character|title|term`, default `term`)**, **`gender` (`male|female|unknown`, nullable —
    meaningful for `character`)**, `note`, `created_at`; `UNIQUE(project_id, surface_form
COLLATE NOCASE)`. **No migration — no production data; redefine `schema.sql` and recreate
    the dev DB.** `category`/`gender` are borrowed from OpenNovel: gender steers zh→en pronoun
    drift; title preference is per-reader.
  - Classic paired entries still fit (`source_term` set, `status='approved'`). One table.
  - Extracted terms start as **`candidate`**; user approval required before a term reaches the
    prompt. `rejected` = kept out of the prompt (handles meaningless noise candidates). A
    dedicated **"avoid" category** (steer _away_ from a bad spelling) is a separate future
    track, NOT the same as `rejected`.
  - Occurrence matching: stdlib **exact whole-word, case-insensitive** (fuzzy/alias is a flagged
    follow-up). Pure function in `services/term_match.py`; detection only.
  - **Term review is opt-in** (a settings toggle); the streaming translate path is untouched
    when review is off.
  - **Atomic engine tasks:** key-term extraction and source↔translation term matching are
    separate, small-context engine calls so a weak local model (`qwen3.5:0.8b`-class) does one
    narrow job at a time, rather than one big combined prompt.
  - Matches fold into the translate `done` event; `GET /translations/{tid}/matches` serves
    retro-review of saved translations.
  - Keep the in-context review UI **lightweight** (highlighting + a review panel), not a full
    inline-edit review studio — that's where OmniTranslate already spends.
  - Phased build in `tasks.md` (14.1–14.7). Flag major decisions before building.
- **User-editable prompts per task (NEXT NOVELTY TRACK — not yet specced in detail):** a
  settings area to customize the prompt for each engine task (translation, glossary/key-term
  extraction, reference summary). This is the clearest differentiator for the local-LLM goal
  (the prompt is the only tuning surface when you can't fine-tune the model). Design note:
  overridable prompt templates layered over the `services/prompt.py` defaults, stored per
  project (or global), behind the existing builders so engines don't change. Sequence it right
  after the glossary data layer. An optimized flow for paid/hosted models is a later follow-up.
- **Model status probe (DONE):** `GET /api/health` now calls `engine.health()` and reports real
  reachability (see the API section). The frontend indicator keys off `reachable`.
- **Model picker (listing DONE; per-request switch PENDING):** `GET /api/models` + the engine's
  `list_models()` shipped. What's left for an actual per-request switch: add a `model` field to
  `TranslateRequest` and pass it into `TranslationRequest.model` in `api/translate.py` (the
  engine already honors it). That's a small backend task to do WHEN the frontend picker is built,
  so the SSE contract changes once. Frontend picker UI is `FRONTEND_TODO.md` #5/#5a.
- **Bring-your-own LLM API token + multi-provider (future track — do not build yet):** add
  hosted-model engines (Gemini, OpenAI, Claude, OpenRouter) behind the `TranslationEngine`
  interface so users can translate with an API key instead of local Ollama. The engine ABC is
  the seam and already works (`stream`/`extract_reference`/`health`/`list_models`) — a new engine
  is additive, no route change. Design implications to honor when this lands (so the
  single-provider surfaces shipped now evolve cleanly rather than get rewritten):
  - **`/api/models` becomes provider-aware.** Target shape (not built yet):
    `{ providers: [{ id, label, reachable, needs_key, models: string[] }], ... }`. The current
    flat `{models, current}` is the single-provider special case. `current` is Ollama-centric
    (one global default); multi-provider needs a per-provider (likely per-project) "current".
  - **Reachability splits per provider.** `health()`/the status indicator assume one engine; a
    cloud provider's state is "key present? key valid? provider up?" — distinct from "unreachable".
    An empty model list must be disambiguable: unreachable vs. no-key-configured.
  - **Per-request override becomes `provider` + `model`**, not just `model`. When wiring the
    translate-body `model` field (Model picker above), model it as a `{provider, model}` pair even
    though provider is fixed to Ollama today, so the cloud addition is a data change.
  - **Credential storage** (API keys) goes behind `StorageService`, not just env — a security
    decision to flag then (env-only vs. encrypted store; never log/echo key values). Local-first
    still holds; accounts/cloud only if adoption warrants it. Don't block task 14.
  - Frontend groundwork for all this is pre-noted in `FRONTEND_TODO.md` #5a (build the picker
    provider-aware now).

Hard rule for all of the above: flag major decisions for confirmation even in autopilot, keep
storage/engine behind their interfaces, keep tests offline on the mock engine, one commit per
task.
