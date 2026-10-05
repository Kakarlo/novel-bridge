# NovelBridge — Session Handoff (bug-fix round 3)

Read this first, then start with Issue 1. Steering files (`.kiro/steering/product.md`,
`tech.md`, `frontend-plan.md`) and the spec (`.kiro/specs/novelbridge/`) are the source of
truth; this note is the short, current to-do.

## Working style for this session

Activate the `ponytail` steering file (`.kiro/steering/ponytail.md`, inclusion: manual) for
this bug-fix round — pull it in via the context tool / disclose_context at the start. It fits
this work: root-cause bug fixes (fix the shared function once, not per caller), stdlib/existing
patterns before new code, deletion over addition, one runnable check behind non-trivial logic.
It does NOT veto Issue 1's spaCy dependency: stdlib regex was already tried and FAILED to judge
grammatical role (that is Issue 1), so spaCy is the ladder's "an installed/available dependency
solves it" rung done correctly — a ~8MB offline NER instead of hand-rolling one. Still confirm
the install with the author before committing the dep. Note: this project's engine/storage
interfaces are intentional, author-requested abstractions (see `tech.md`) — keep them; the
"no abstractions" rule applies to NEW unrequested ones.

## State at handoff

- Branch `main`, clean tree, HEAD `05f54cd`. Local only, no remote. One commit per task.
- Backend: 82 tests pass — `cd backend; .\.venv\Scripts\python.exe -m pytest -q`.
- Frontend: builds clean — `cd frontend; npm run build`.
- English-first glossary (spec task 14) is fully built: data/storage, occurrence detection
  (`services/term_match.py`), API (status PATCH, opt-in `review_terms` → matches in the SSE
  `done` event, `GET /translations/{tid}/matches`), prompt integration (approved/paired terms
  only, category/gender-aware blocks), and the glossary UI (add/edit with category+gender,
  status badges, approve/reject, status filter).
- **Not yet built:** spec Phase 14.6 (in-context review UI on the Translate tab) and 14.7
  (verification). Also task 22 (user-editable prompts — the novelty track) is captured, not built.

## Working agreement (unchanged)

Local-first; storage behind `StorageService`, engine behind `TranslationEngine`; tests offline
on the mock engine; flag major decisions even on autopilot; one local commit per task; no git
remote/push without asking. Windows PowerShell: separate commands with `;`, env vars via
`$env:VAR="..."`. Dev DB `backend/novelbridge.db` can be deleted + recreated (no prod data).

## Issue 1 (URGENT) — replace the rule-based noun extractor with spaCy NER

The regex extractor (`backend/app/services/noun_extract.py`) still leaks "I'm", "Ah",
"Although", "Unfortunately", "I'll" into detected names. Regex + stopwords can't judge
grammatical role, so this approach has hit its ceiling.

**Decision (confirmed with author): adopt spaCy NER.** Research notes:

- Use **NER entity spans** (PERSON/ORG/GPE/FAC/LOC/NORP), NOT raw POS `PROPN` tags — PROPN
  misclassifies ("Thursday" like "John") and spaCy's own team says PROPN-vs-NOUN is the
  tagger's weakest spot. NER yields clean multiword spans ("Li Changshou") and naturally drops
  sentence-openers.
- `en_core_web_sm` ~12–15MB on disk (~8MB if stripped to the `ner` pipe only). Loads fast,
  runs offline — fits local-first.
- Caveat: trained on web/news, so it NAILS character/place names (the real pain) but MISSES
  xianxia jargon ("Qi Refinement", "Primordial World"). That's fine — pair it with the LLM.

**Plan:**

1. Add `spacy` to `backend/requirements.txt`; install `en_core_web_sm`
   (`python -m spacy download en_core_web_sm`). **Confirm the install with the author before
   committing the dep** (new runtime dependency + model download).
2. Rewrite `extract_proper_nouns(text, *, limit=30) -> list[str]` INTERNALS to use spaCy NER,
   keeping the SAME signature so API/storage/UI/`build_extraction_messages` don't change. Load
   the model once (module-level singleton, `exclude=[...]` to keep only NER). Collect entity
   texts of the name-like labels, strip possessives, dedupe case-insensitively, rank by
   frequency, cap at `limit`.
3. Keep the current regex implementation as a FALLBACK if spaCy/model import fails, so the app
   still runs without the model (log a warning). Tests must stay offline-safe: if the model
   isn't present, skip the spaCy-specific assertions (pytest.importorskip) and keep the fallback
   tests.
4. Narrow the LLM's job: `build_extraction_messages` can tell the model names are already
   handled by rules — focus on the SUMMARY and lowercase/concept terms spaCy won't catch.
   `extract_reference` already receives `detected_names` as a hint; keep feeding it.
5. Update `backend/tests/test_noun_extract.py` for the NER behavior. Existing regression cases
   (possessives, contractions, sentence openers) must pass.

Current `extract_proper_nouns` is called in `backend/app/api/projects.py` `add_reference` and
`resummarize_reference`; result stored in `reference_chapters.detected_names` (JSON column),
surfaced in the frontend `references-tab.tsx` DerivedContext as the "Detected names" group.

## Issue 2 — reference summarization: no guardrail; "runs in background"

`POST /api/projects/{id}/references` runs extraction SYNCHRONOUSLY in the request handler
(`add_reference` in `api/projects.py` awaits `engine.extract_reference`). The frontend
(`references-tab.tsx`) fires the add and the component stays mounted across tab switches
(tabs are `forceMount` now), so it "finishes in the background" — which is actually fine.
Decide the cleaner model and make it intentional:

- Option A (recommended, simplest): keep it synchronous, but show a clear per-reference
  "Summarizing…" pending state in the UI while the POST is in flight, and a `beforeunload`
  guard if a summarize/add is in flight (mirror the translate guardrail in
  `hooks/use-active-stream.ts` — maybe generalize that store to "work in progress").
- Option B: make extraction a background step after the reference is saved (save immediately,
  summarize async, poll/refetch). More moving parts; only if A feels wrong.
  Confirm with the author which model before building.

## Issue 3 — chip dismissal visual flash (all tags show, then dismissed ones vanish)

In `references-tab.tsx` `DerivedContext`: `dismissed` is lazy-init from localStorage (good),
but `inGlossary` is populated in an async `useEffect` (glossary fetch), so on first paint all
chips render, then the fetched/dismissed ones disappear → flash. Fix: compute the visible set
without a post-mount state flip for the dismissed part (already synchronous), and avoid showing
chips until the glossary set is known for THIS reference — e.g. gate the chip lists on a
"glossaryLoaded" flag, or seed `inGlossary` synchronously if cached. Keep it simple; the
dismissed-flash specifically is the lazy-init vs effect-order issue.

## Issue 4 — dark mode too dark to read

Tune `.dark` tokens in `frontend/src/index.css` toward a common, readable reference (GitHub
dark: text ≈ `#e6edf3` on bg ≈ `#0d1117`; Linear is similar). Raise foreground contrast and
lift the background off pure black. Keep the single amber `--accent-brand`. The
`prefers-reduced-motion` guard and no-FOUC inline script in `index.html` stay as-is.

## Issue 5 — source text lost on project switch + refresh

Draft persistence lives in `translate-tab.tsx` (localStorage `nb:draft:{projectId}`,
load/save/clear). The save effect runs on `[projectId, raw, lang, output, status]`. After the
`forceMount` change, re-verify: (a) switching projects re-runs the mount/restore effect
(dependency `[projectId, defaultLang]`) and restores the draft; (b) the save commits BEFORE the
switch unmounts/swaps (it should, since state changes trigger the effect synchronously, but the
report says text is lost on project switch AND refresh — so investigate whether the save is
actually firing, e.g. a too-early `return` on `status==="viewing"`, or the key mismatch). Add a
quick manual trace: type → check `localStorage` has `nb:draft:{id}` → switch → confirm restore.
This is a small logic bug, not a redesign.

## Suggested order

1 (spaCy, confirm dep) → 5 (draft bug, small) → 3 (flash, small) → 2 (summarize UX, confirm) →
4 (dark mode polish). Commit each separately. Keep backend tests + frontend build green.
