# Backend follow-ups (handoff from the frontend-only session)

Running list of backend changes the frontend needs but could not make (frontend-only
session). Each entry: the endpoint/contract needed, the request/response shape, and why.
Keep the HTTP contract backward-compatible where possible.

---

## 0. Cloud engines: OpenRouter + Gemini (bring-your-own key) — DONE (backend)

Two hosted engines now live behind the `TranslationEngine` interface:

- `engines/openrouter_engine.py` — OpenAI-compatible gateway (200+ models). Streaming SSE
  (`choices[].delta.content`), non-streaming helpers for extraction, `/models` listing.
- `engines/gemini_engine.py` — Google's REST API (custom format: `contents`/`parts`,
  `system_instruction`, `streamGenerateContent?alt=sse`). Includes `_to_gemini_messages` to
  convert OpenAI-style messages. Both are heavily commented as templates for more providers.

Select via `NB_ENGINE=openrouter|gemini` + the matching `*_API_KEY` (see `.env.example`).
`factory.py` validates the key at startup (fail-fast). `/api/health` + `/api/models` now
report the correct per-engine default model (`_default_model` in `main.py`), and `health()`
pings the provider (validates key + reachability). Keys come from env today; a per-user
credential store behind `StorageService` is the future track (do NOT build yet).

**Still frontend-only (provider-aware picker):** `/api/models` is still the flat
`{models, current}` single-provider shape. The multi-provider `{providers: [...]}` shape (per
`tech.md`) is a frontend-driven follow-up — the translate `selection` body already accepts
`{provider, model}`, and the backend validates `provider` against the active engine (400 on
mismatch). When the picker goes multi-provider, `/api/models` grows the providers array.
sessionStorage API-key handling (per the research) is a frontend concern — the backend reads
keys from env for now.

---

## 1. Manual chapter-number override on a reference (FRONTEND_TODO #2.3)

**Why:** `ReferenceChapter.chapter_number` is parsed from the title at upload and is `null`
when the title has no recognizable number (volume formats, prologues, untitled) or wrong when
the title is messy. The references list now displays the number and sorts by it, but the user
has no way to set/correct it — the storage layer only computes it at upload time (no override
path), and there is no route to set it.

**What the frontend needs:**

- A write endpoint to set `chapter_number` on an existing reference. Either:
  - `PATCH /api/references/{refId}` with a partial body `{ chapter_number: number | null }`, or
  - a dedicated `PATCH /api/references/{refId}/chapter-number` with `{ chapter_number: number | null }`.
- Response: the updated `ReferenceChapter` (200), 404 when the reference is missing.
- `chapter_number` must accept an explicit `null` to clear a wrong auto-parse back to
  "unnumbered".
- Needs a storage setter (the SQLite impl currently has no update path for this column).

**Frontend plan once this lands:** add `api.setReferenceChapterNumber(refId, n)` to the typed
client, and a small inline edit (click the "Ch N" / "No chapter number" marker → number input)
in `references-tab.tsx`. UI not built yet — it would 404/have nowhere to write today.

**Volume formats (future):** `Volume 2 Chapter 5` parses to `null` today. Multi-volume
ordering is a backend design task (composite volume+chapter key), not a frontend fix. Flagged
here so the override endpoint and the eventual volume support don't get designed twice.

---

## 2. Per-request model override on the translate endpoint (FRONTEND_TODO #5.3 / #5a) — DONE

**Shipped as a provider-aware `{provider, model}` pair** (not a bare `model`), per the
provider-aware target below. The translate request body (`POST /api/projects/{id}/translate`)
now accepts an optional `selection: { provider?: string, model?: string }`:

- `model` is passed into `TranslationRequest.model` (engine already honors it).
- `provider` is validated against the configured engine (`engine.name`); a mismatch returns
  **400** (single provider today — the engine is a cached singleton). Becomes a provider→engine
  lookup once cloud engines land (task 4).
- Fully backward-compatible: omit `selection` entirely → configured engine + `OLLAMA_MODEL`.
- Auto-saved `model_used` prefers the requested model when provided, else the engine default
  (and is overwritten by the engine's `done` meta when present).
- Frontend `TranslateRequest.selection?: Partial<ModelSelection>` added to `types.ts` to match.

Models touched: `models.py` (`ModelSelection`, `TranslateRequest.selection`),
`api/translate.py` (resolve + validate + pass through), `frontend/src/api/types.ts`.

---

### Original notes (for reference)

**Why:** `GET /api/models` lists models and the engine already honors a per-request
`TranslationRequest.model`, but the SSE translate REQUEST BODY has no `model` field, so the
model picker can only _display_ the current model, not switch it per translation.

**What the frontend needs:**

- Add an optional `model?: string` to the translate request body
  (`POST /api/projects/{id}/translate`) and pass it into `TranslationRequest.model` in
  `api/translate.py`. The engine already accepts it — no engine change.
- Backward-compatible: when `model` is omitted, fall back to the configured `OLLAMA_MODEL` as
  today.

**Provider-aware target (do NOT build yet; shape the field so it's a data change later):**
Per `tech.md` "Bring-your-own LLM API token", the override will eventually become a
`{ provider, model }` pair, not just `model`. When adding the body field, consider accepting a
nested `{ provider, model }` (provider fixed to the local engine today) so the cloud-provider
addition is additive. The frontend picker is already modeled provider → model for this reason.

**Frontend plan once this lands:** the picker's selected `{ provider, model }` gets sent on the
translate call; until then the picker is display-only (shows `current`, lets the user see the
list, but the Translate button always uses the server default).
