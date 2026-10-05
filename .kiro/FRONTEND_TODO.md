# Frontend follow-ups (handoff from backend-only sessions)

Running list of frontend changes that a later frontend session must make to match backend
changes. Each entry: what changed on the backend, the request/response shape, and what the UI
should do. Backend keeps the HTTP contract backward-compatible where it can; breaking changes
are called out explicitly.

---

## 1. Source-language terms moved from references → saved translations (BREAKING)

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

## 2. References gained a `chapter_number` field (ADDITIVE, backward-compatible)

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
