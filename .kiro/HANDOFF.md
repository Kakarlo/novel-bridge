# NovelBridge — Session Handoff

Read this first, then wait for the author to pick a task. Steering files
(`.kiro/steering/product.md`, `tech.md`, `frontend-plan.md`) and the spec
(`.kiro/specs/novelbridge/`) are the source of truth; this note is the short, current state.

## Working style

Activate the `ponytail` steering file (`.kiro/steering/ponytail.md`, inclusion: manual) at the
start — pull it in via `disclose_context`. Root-cause fixes (fix the shared function once),
stdlib/existing patterns before new code, deletion over addition, and ONE runnable check behind
non-trivial logic. The `StorageService` / `TranslationEngine` ABCs are intentional,
author-requested abstractions — keep them; the "no new abstractions" rule is only for
UNrequested ones. Confirm any new runtime dependency or model download with the author before
installing/committing it.

## Scope for the next session: BACKEND ONLY

The author is deliberately keeping the next session backend-only (juggling backend + frontend
together ballooned context last time). Work only in `backend/`. If a change needs a matching
frontend update, do NOT make it — append a specific note to `.kiro/FRONTEND_TODO.md` (endpoint/
contract that changed, request/response shape, what the UI should do) and keep the HTTP contract
backward-compatible where possible. See the "Next Session Starter Prompt" artifact for the full
rules; the author will paste it to open the session.

## Verification expectation

Every non-trivial change ships a runnable pytest in `backend/tests/` that fails without the
change and passes with it. Tests stay OFFLINE on the mock engine; anything needing a spaCy model
skips gracefully when the model is absent (`importorskip` / feature-flag guard). Run the full
suite and report the pass count before calling a task done.

Run tests: `cd backend; .\.venv\Scripts\python.exe -m pytest -q`
Scratch helpers (untracked, for eyeballing — never a substitute for a test):
`backend/scratch_noun_extract.py` (paste a chapter, see detected names),
`backend/scratch_db.py` (read-only DB inspector).

## State at handoff

- Branch `main`, HEAD `d5b7c09`. Local only, no remote. One commit per task.
- Backend: **114 tests pass**. Frontend: builds clean (not in scope next session).
- spaCy installed: `en_core_web_sm` (English names) and `zh_core_web_sm` (Chinese source terms).
  `ja_core_news_sm` NOT installed.
- Local `backend/.env` has `NB_SOURCE_TERMS=true` and `NB_PRONOUN_CHECK=true` (both default
  false in `config.py`; `.env` is gitignored).

### Shipped this round (all committed)

- English name extraction via spaCy NER (`services/noun_extract.py`): narrow labels
  (PERSON/ORG/GPE/LOC/FAC), strips quotes/punctuation/interjections/trailing verbs; regex
  fallback if the model is absent. Feeds both the "Detected names" group and the extraction
  prompt as hints.
- Reference "names only" mode: `ReferenceCreate.extract_summary` (default true); false skips the
  AI summary and runs only the name detector. `POST /references/{id}/redetect` re-runs the name
  detector only (no engine) and excludes names already in the glossary.
- English-first glossary with Option B unified vocabulary: a reference-chip "reject" is a
  persistent `rejected` glossary entry (restorable); resolving a suggestion removes it from the
  reference's pools (`POST /references/{id}/resolve-term`, `storage.remove_reference_term`);
  project counts exclude rejected.
- Experimental, gated OFF by default, isolated for cheap removal:
  - `services/source_terms.py` — zh/ja source-term NER. `GET /references/{id}/source-terms`,
    flag `NB_SOURCE_TERMS`. Degrades to `[]` if the model is missing.
  - `services/pronoun_check.py` — English pronoun-drift DETECTOR (never rewrites).
    `GET /translations/{tid}/pronoun-drift`, flag `NB_PRONOUN_CHECK`. stdlib-only.

## Open problems (backend components)

Full designs to refine live in the "Remaining Work Brief" artifact. The backend-relevant ones:

1. **spaCy name split** — NER sometimes returns "Li Changshou" AND "Li"/"Changshou" separately.
   Add a deterministic fold-fragments-into-longer-name post-process in `noun_extract.py`, same
   `extract_proper_nouns` signature, with a unit test. Watch the edge case of a name used alone.
2. **Pronoun-drift precision** — the proximity detector in `pronoun_check.py` has a known
   ceiling (no coreference; false positives in dense scenes). Evaluate precision on real
   translations; decide proximity-vs-lightweight-coref and whether the answer is a detector or a
   stronger prompt hint. Detection only — never rewrite.
3. **zh/ja source-term → English alignment** — `source_terms.py` yields source terms but a
   glossary entry needs the English `surface_form`. Design the pairing (positional/frequency
   heuristic, one narrow LLM alignment call, or user-assisted). Cheap to remove, offline-safe.
4. **User-editable prompts per task (the novelty track)** — overridable prompt templates layered
   over `services/prompt.py` defaults, stored per project/global behind the existing builders so
   engines don't change. Needs storage shape + safe variable interpolation + "effective prompt"
   view. Frontend settings UI is a FRONTEND_TODO.
5. **Model picker (backend-first)** — `GET /api/models` proxying Ollama `/api/tags`; the engine
   already accepts a per-request `model` on `TranslationRequest`. Just the listing endpoint +
   request plumbing this session; the picker UI is a FRONTEND_TODO.

## Working agreement (unchanged)

Local-first; storage behind `StorageService`, engine behind `TranslationEngine`; tests offline
on the mock engine; flag major decisions even on autopilot; one local commit per task; no git
remote/push without asking. Windows PowerShell: separate commands with `;`, env vars via
`$env:VAR="..."`. Dev DB `backend/novelbridge.db` can be deleted + recreated (no prod data).
