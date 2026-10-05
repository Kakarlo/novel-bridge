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

- [ ] 14. English-first glossary with in-context approval (MAJOR; **table stakes**, phased build)
  - **Framing:** this is the consistency mechanism every competitor already has (OpenNovel,
    OmniTranslate) — build it solid and credible, then stop; don't over-invest in review-studio
    polish. The project's novelty is the harness itself (model-agnostic, local, open,
    user-editable prompts — see `product.md` north star and task 22).
  - **Why:** references are English, so the engine's `candidate_terms` are English surface forms
    — the user knows the English name, not the source term, and shouldn't have to hunt for it.
    The user adds a name by its **English form alone**; when it appears in a translation they
    **approve/reject** the usage in context. Approved terms steer the prompt as preferred
    spellings (a _guide_, not a find-and-replace: matching only detects occurrences, never
    rewrites output).
  - **No migration:** no production data exists, so `glossary_entries` is redefined directly in
    `schema.sql` and the dev `novelbridge.db` is deleted + recreated. No additive/backfill work.
  - **Settled decisions (Phase 0 — confirmed with the author):**
    - One glossary table redefined English-first — `surface_form` (req), `source_term`
      (nullable), `status` (`candidate|approved|rejected`, default `candidate`), **`category`
      (`character|title|term`, default `term`)**, **`gender` (`male|female|unknown`, nullable;
      meaningful for `character`)**, `note`, `created_at`,
      `UNIQUE(project_id, surface_form COLLATE NOCASE)`. Classic paired entries fit
      (`source_term` set, `status='approved'`).
    - `category`/`gender` borrowed from OpenNovel: gender steers zh→en pronoun drift; title
      preference (师兄 → "Senior Brother" vs "Shixiong") is per-reader.
    - Extracted terms start as **`candidate`**; approval required before a term reaches the
      prompt. `rejected` = kept out of the prompt (handles meaningless noise candidates). A
      dedicated **"avoid" block** (steer away from a bad spelling) is a SEPARATE future track,
      not the same as `rejected`.
    - Occurrence detection = **exact whole-word, case-insensitive** (stdlib; fuzzy is a flagged
      follow-up). Detection only — never rewrites output.
    - **Term review is opt-in** via a settings toggle; the streaming translate path is untouched
      when review is off.
    - **Atomic engine tasks:** key-term extraction and source↔translation term matching are
      separate, small-context engine calls so a weak local model does one narrow job at a time.
    - Matches fold into the translate `done` event; `GET /translations/{tid}/matches` serves
      retro-review of saved translations.
  - **Phases (each a commit; build + offline tests green):**
    - 14.1 Data + storage: redefine `schema.sql` (surface_form/source_term/status/**category**/
      **gender**/note/created_at), recreate dev DB, update `models.py`/TS types, add `add_term`
      - `set_term_status` (keep classic CRUD) + storage tests.
    - 14.2 Occurrence detection: `services/term_match.py` (`find_occurrences`, whole-word
      case-insensitive, pure stdlib) + offline unit tests.
    - 14.3 API: `POST /projects/{id}/glossary/english`, `PATCH /glossary/{id}/status`, matches
      folded into the translate `done` event (behind the opt-in review flag) +
      `GET /translations/{tid}/matches`; API tests on the mock engine.
    - 14.4 Prompt integration: approved terms → a "preferred spellings" block
      (category/gender-aware); keep the paired `source => target` block for entries with a
      `source_term`. Atomic extraction + matching engine tasks. Context-builder budgeting +
      prompt tests. (The reading-quality payoff.)
    - 14.5 Glossary UI: English-only add with category + gender, status badges, approve/reject,
      status filter; keep the classic paired editor. Opt-in review toggle.
    - 14.6 In-context review UI (**lightweight, opt-in**): translate-tab review panel +
      basic output highlighting; history retro-review via the matches endpoint. Not a full
      inline-edit review studio.
    - 14.7 Verification: end-to-end on mock + one live pass; update README/steering.

- [ ] 15. Model picker (deferred; capture only)
  - `GET /api/models` proxying Ollama `/api/tags`, plus per-request model plumbing (engine
    already accepts `TranslationRequest.model`). Build after the frontend model-status indicator.

- [ ] 21. Bring-your-own LLM API token (future track; capture only — do not build yet)
  - North-star direction: let users plug in a hosted-model API key so translation works without
    running Ollama locally. Additive new engine behind the `TranslationEngine` interface
    (alongside Ollama/mock), key stored in local config for now. **Local-first still holds** —
    no accounts/cloud yet; those come only if adoption warrants it, behind `StorageService`.
    Do not design anything in task 14 that blocks this, but don't start it.

- [ ] 22. User-editable prompts per task (NOVELTY TRACK; spec after task 14's data layer)
  - **Why it matters:** this is a core differentiator. The competitors (OpenNovel,
    OmniTranslate) run their own tuned models and hide the prompt. NovelBridge is a
    model-agnostic, local, open harness, so **the prompt is the user's only tuning surface** —
    the lever that makes a free/local LLM produce a decent read for a specific genre or model.
  - **Shape (to be specced):** a settings area to override the prompt template for each engine
    task — translation, glossary/key-term extraction, reference summary. Overrides layer over
    the `services/prompt.py` defaults (named builders already exist), stored per project and/or
    globally behind the storage interface. Engines don't change. Include a "reset to default"
    and show the effective prompt. Keep offline tests on the mock engine.
  - **Sequencing:** right after task 14's data/storage layer; it's small and high-leverage. An
    optimized flow for paid/hosted models is a later follow-up (relates to task 21).
  - Capture only for now — flag the design before building.

### Frontend

- [x] 16. Dark mode (keep simple; confirm scope)
  - Shipped: no-FOUC inline script in `index.html` (applies theme before paint), `use-theme.ts`
    hook (light/dark, localStorage + `prefers-color-scheme` first-load default, follows OS live
    until an explicit choice), sun/moon toggle in the sidebar footer, sonner `Toaster` wired to
    the theme without `next-themes`.

- [x] 17. Delete saved translations (UI)
  - Shipped: per-row trash in `history-panel.tsx` (hover/focus reveal) guarded by
    `ConfirmDialog`, calling `DELETE /api/translations/{tid}`. Resets the panes if the loaded
    translation is deleted; refreshes the project count.

- [x] 18. Fix streaming scroll-follow
  - Shipped: stick-to-bottom autoscroll in `translate-tab.tsx` (only follows when pinned near
    the bottom), a "jump to latest" affordance while streaming, and reduced-motion respected.

- [x] 19. Model-status indicator
  - Shipped: `use-health.ts` polls `GET /api/health` (mount + ~30s + window focus);
    `model-status.tsx` in the sidebar footer shows engine + model + a reachable dot and flags
    `engine=="mock"`. Paired with task 19b below (the health probe became real). Groundwork
    before the deferred model picker (task 15).

- [x] 19b. Real engine health probe (backend)
  - `GET /api/health` previously echoed config and always reported "ok". Now it's async and
    calls `engine.health()` (Ollama pings `/api/tags`; mock returns True), returning
    `reachable` + `status: ok|unreachable`. The indicator shows three states: engine reachable
    (green), backend up but LLM unreachable (amber), backend down (red).

- [x] 20. Surface reference summary + candidate terms (frontend)
  - References reader shows a "Derived context" panel (summary + candidate-term chips), a
    "Re-summarize" action (`POST /api/references/{refId}/resummarize`), and list rows show a
    term-count / "not summarized" badge. Candidate chips can be promoted into the glossary with
    an English mapping. `ReferenceChapter` type gained `summary` + `candidate_terms`.
