# Frontend follow-ups (handoff from backend-only sessions)

Running list of frontend changes that a later frontend session must make to match backend
changes. Each entry: what changed on the backend, the request/response shape, and what the UI
should do. Backend keeps the HTTP contract backward-compatible where it can; breaking changes
are called out explicitly.

---

## 1. Source-language terms moved from references → saved translations (BREAKING) — DONE

**Why:** references are English (English-first glossary), so running zh/ja source-term NER over
a reference's text produced garbage (English words tagged by a Chinese model). Source text only
exists in the translate flow, so the feature now hangs off a _saved translation_.

**Backend contract change:**

- **REMOVED:** `GET /api/references/{refId}/source-terms`
- **ADDED:** `GET /api/translations/{tid}/source-terms`
  - Still EXPERIMENTAL, gated by `NB_SOURCE_TERMS` on the backend.
  - Response: `string[]` (same shape as before) — zh/ja proper nouns from the translation's
    **source chapter** (`raw_text`), most frequent first.
  - `404` when the feature is off, when the translation is missing, **or** (now) when the
    route doesn't exist on an older backend. Treat a thrown 404 the same as before: feature
    disabled → render nothing.
  - Returns `[]` (200) when the feature is on but the spaCy source model isn't installed.
    Treat empty as "unavailable", not a hard error.

**What the UI should do:**

1. In `src/api/client.ts`: remove `referenceSourceTerms(refId)` and add
   `translationSourceTerms(tid: string) => request<string[]>(\`/translations/${tid}/source-terms\`)`.
2. In `src/components/references-tab.tsx`: remove the "Source-language terms" chip group and its
   `sourceTerms` state / `useEffect` / the `nothingToShow` term that references it. The reference
   tab should no longer show source-language terms at all.
3. Add the "Source-language terms" group where a source chapter actually exists — the natural
   home is the **Translate tab / History panel** when viewing a _saved_ translation (one with a
   `translation_id`). Fetch `translationSourceTerms(tid)` on load, same 404-is-disabled /
   empty-is-unavailable handling as the old reference version. Keep it lightweight (copy-to-
   clipboard chips, "pair with an English name in the Glossary tab"), matching the prior intent.
   It only makes sense for a persisted translation, not a live/in-progress stream.

---

## 2. References gained a `chapter_number` field (ADDITIVE, backward-compatible) — DONE (display + sort; manual override → BACKEND_TODO #1)

**Why:** reference ordering for continuity should follow chapter order, not upload time.
The backend now parses a chapter number from the reference title at upload and orders context
by it (falling back to upload order when absent).

**Backend contract change (additive):**

- `ReferenceChapter` responses now include `chapter_number: number | null`.
  - Parsed from the title by `services/chapter_number.py` on `POST /projects/{id}/references`.
  - Handles `Chapter N`, `Ch. N`, `Ch N`, decimals (integer part), and a bare leading number
    (`12. Title`). The messy real case `Chapter 1035 - 469: ...` → `1035` (first number after
    "Chapter"; the secondary source index is ignored).
  - `null` when the title has no recognizable number: volume formats (`Volume 2 Chapter 5`),
    prologues, untitled. Volume+chapter is deliberately unsupported for now (can't be a single
    int) — see the VOLUME TODO in `chapter_number.py`.
- Existing clients that ignore the field keep working unchanged.

**What the UI should do:**

1. In `src/api/types.ts`: add `chapter_number: number | null` to the `ReferenceChapter` type.
2. **Display** the chapter number in the references list/reader (e.g. a small badge). When
   `null`, show a subtle "No chapter number" state.
3. **Manual entry / override** when `null` or wrong: let the user set a chapter number. This
   needs a backend endpoint that does NOT exist yet — a `PATCH /references/{refId}` (or a
   dedicated `/references/{refId}/chapter-number`) to set `chapter_number`. Flag this back to a
   backend session so the storage setter + route get added before building the UI; the storage
   layer currently only computes the number at upload time (no override path yet).
4. (Nice-to-have) sort the references list by `chapter_number` so the user sees chapter order,
   matching how context is now assembled.

**Volume formats (future):** `Volume 2 Chapter 5` currently parses to `null`. If users need
multi-volume series ordered correctly, that's a backend design task (composite volume+chapter
ordering key), not a frontend-only fix.

---

## 3. Source↔English term-alignment proposals (NEW, experimental, additive) — DONE

**Why:** a glossary entry only becomes authoritative once it has BOTH the English
`surface_form` AND the original `source_term`. Users know the English name but not the source
term, so the backend now PROPOSES pairings deterministically (no LLM) for the user to confirm.

**Backend contract (additive, experimental — gated by `NB_SOURCE_TERMS`):**

- **ADDED:** `GET /api/translations/{tid}/term-alignment`
  - Response: `AlignmentCandidate[]`, highest `confidence` first. Each:
    `{ source_term: string, surface_form: string, source_count: number,
english_count: number, confidence: number (0..1), basis: string }`.
  - Proposes `source_term → surface_form` pairings by correlating appearance order +
    frequency in the translation's source chapter vs its English output — NOT string
    similarity / transliteration.
  - `404` when the feature is off or the translation is missing; `[]` when the source-term
    spaCy model isn't installed or nothing aligns. (Same gating/degradation as `/source-terms`.)

**What the UI should do:**

1. In `src/api/types.ts`: add an `AlignmentCandidate` type; in `client.ts` add
   `translationTermAlignment(tid) => request<AlignmentCandidate[]>(\`/translations/${tid}/term-alignment\`)`.
2. In the translation review view, show a lightweight "Suggested source↔English pairs" panel:
   each row = `source_term  →  surface_form` with the confidence shown honestly (e.g. a
   low/med/high chip from the 0..1 value) and the counts. **These are guesses** — the small zh
   model can mis-segment and mis-pair; present them as suggestions, not facts.
3. **Confirm** sets the pairing via the EXISTING glossary write — no new endpoint needed:
   `PUT /api/glossary/{entryId}` with `{ source_term }` (the entry is found by its
   `surface_form`), or `POST /api/projects/{id}/glossary` with `{ surface_form, source_term }`
   (upserts). A confirmed pair becomes an authoritative glossary mapping that steers the next
   translation. **Reject** just dismisses the suggestion (no backend call).
4. Keep it lightweight (table stakes, not a studio) — same stance as the in-context review UI.

---

## 4. Reference tab: term count + "Detected names" description are stale — DONE

Backend-adjacent copy/display fixes in `references-tab.tsx` (no backend change needed):

1. **Term count** currently reflects `candidate_terms` (the AI-extracted terms), not
   `detected_names` (the spaCy proper-noun pass). Decide which the headline count should
   represent — the detected names are the deterministic signal the user acts on most — and
   label it clearly (e.g. separate counts for "Detected names" vs "Candidate terms").
2. **"Detected names — found by rules (capitalized proper nouns); click to add to the
   glossary"** is outdated. Detection is spaCy NER by default now. Reword to describe it as
   automatic name detection (spaCy-based). Do NOT mention the regex fallback — it's an internal
   offline-safety net, not a user-facing detail.

---

## 5. Model picker — backend listing endpoint is ready (NEW, additive)

**Why:** let the user pick which model translates, instead of being stuck on the configured
default. The engine already accepts a per-request model (`TranslationRequest.model`); the
backend now exposes the list.

**Backend contract (additive, not gated):**

- **ADDED:** `GET /api/models` → `{ "models": string[], "current": string }`.
  - `models`: model names the engine can serve (Ollama: live from `/api/tags`, sorted; mock:
    `["mock"]`). Empty list when the engine is unreachable (degrades, never errors).
  - `current`: the configured default model (`OLLAMA_MODEL`).

**What the UI should do:**

1. In `client.ts`: add `listModels() => request<{models: string[]; current: string}>("/models")`.
2. A model picker (dropdown) in the translate view / settings, seeded from `models`, defaulting
   to `current`. Disable / show "engine unreachable" when `models` is empty. The existing health
   indicator already tells you reachability.
3. **Per-request override is NOT wired through the translate endpoint yet.** `TranslateRequest`
   has no `model` field today — the SSE `POST /projects/{id}/translate` body would need a
   `model?: string` added and passed into `TranslationRequest.model`. That's a small BACKEND
   change to do when the picker is built; flag it back to a backend session so the contract
   changes once. Until then the picker can only _display_ the current model, not switch it.

### 5a. Build the picker PROVIDER-AWARE even though only one provider exists today

The current `GET /api/models` contract (`{models, current}`) is correct for the single local
engine shipped now, but the roadmap adds cloud providers (Gemini, OpenAI, Claude, OpenRouter)
behind the same `TranslationEngine` interface. To avoid rebuilding the picker, design the UI
for a **two-level provider → model** shape from day one, even while there's just "Local (Ollama)".

- Model the picker's internal state as `provider -> model`, not a flat model name. Today there's
  one provider; render it as a (possibly collapsed) group so adding providers later is additive.
- Treat an empty `models` list as **ambiguous**: it can mean "engine unreachable" OR, for a
  future cloud provider, "no API key configured". Don't hard-code "unreachable" copy — leave room
  for a "needs setup / add a key" state per provider.
- **Expect the contract to grow a provider dimension.** The planned target shape (see
  `tech.md` → "Bring-your-own LLM API token") is roughly
  `{ providers: [{ id, label, reachable, needs_key, models: string[] }], ... }` with a
  per-provider/per-project "current". When that lands, `listModels()` and the picker swap to it;
  keeping the picker provider-shaped now makes that a data change, not a rewrite.
- The per-request override (5.3 above) will likewise become a per-request **`provider` + `model`**
  pair, not just `model`. Keep the "selected engine/model" the translate call will send modeled
  as a `{provider, model}` object even if provider is fixed today.

Net: ship the single-provider picker now, but shaped so cloud providers are a later data/config
change rather than a UI rebuild.
