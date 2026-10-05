# Frontend follow-ups (handoff from backend-only sessions)

Running list of frontend changes that a later frontend session must make to match backend
changes. Each entry: what changed on the backend, the request/response shape, and what the UI
should do. Backend keeps the HTTP contract backward-compatible where it can; breaking changes
are called out explicitly.

---

## 1. Source-language terms moved from references → saved translations (BREAKING)

**Why:** references are English (English-first glossary), so running zh/ja source-term NER over
a reference's text produced garbage (English words tagged by a Chinese model). Source text only
exists in the translate flow, so the feature now hangs off a *saved translation*.

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
   home is the **Translate tab / History panel** when viewing a *saved* translation (one with a
   `translation_id`). Fetch `translationSourceTerms(tid)` on load, same 404-is-disabled /
   empty-is-unavailable handling as the old reference version. Keep it lightweight (copy-to-
   clipboard chips, "pair with an English name in the Glossary tab"), matching the prior intent.
   It only makes sense for a persisted translation, not a live/in-progress stream.
