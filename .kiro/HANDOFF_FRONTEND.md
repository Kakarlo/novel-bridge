# Frontend session handoff

Read `.kiro/HANDOFF.md`, the steering files (`product.md`, `tech.md`, `frontend-plan.md`),
and activate `ponytail` (`.kiro/steering/ponytail.md`, manual) first. This note is the short
current state for the **frontend**.

## Scope rule (unchanged)

Frontend only (`frontend/`). Do NOT edit `backend/`. If a frontend task needs a backend change,
append it to `.kiro/BACKEND_TODO.md` instead of stubbing. `npm run build` (tsc + vite) must be
clean before any task is called done. One local commit per task; no git remote/push without
asking. Windows PowerShell: `;` to separate commands, `$env:VAR="..."`.

## Done this session (all committed on `main`)

`FRONTEND_TODO.md` items 1–5 are all DONE:

- **4** `fix(references)` `26bfdbc` — term-count badges (names vs terms) + spaCy copy fix.
- **1 + 3** `feat(translate)` `03fe8ea` — removed reference source-terms; new
  `translation-review.tsx` on the saved-translation view (source-term copy chips +
  source↔English alignment confirm/dismiss). Both endpoints gated by `NB_SOURCE_TERMS`;
  404/empty → render nothing.
- review polish `2133644`, `d9ae7f2` — editable glossary `source_term`, shadcn Collapsible
  (`ui/collapsible.tsx`), moved review to the Source pane, `.pane-scroll` + `bg-card` dark-mode
  fixes.
- **2** `feat(references)` `baef36f` — `chapter_number` display (`Ch N` marker + reader badge,
  "No chapter number" state) + sort by it.
- **5 + 5a** `feat(translate)` `1b49854` — provider-aware model picker (`use-models.ts`,
  `model-picker.tsx`), **read-only** (disabled) until the translate body gets a `model` field.
- fixes `e746dc5` — picker stays read-only; ConfirmDialog guard when clicking a saved
  translation mid-stream.

`.kiro/BACKEND_TODO.md` created with two items for a backend session:
1. Manual `chapter_number` override endpoint (`PATCH /references/{refId}` + storage setter).
2. Per-request `model` field on the translate body (unblocks making the picker switchable).

## Next task: 14.6 — in-context review UI (lightweight, opt-in)

Spec: `.kiro/specs/novelbridge/tasks.md` task 14 → phase 14.6. **The backend is fully shipped**
(14.1–14.4) — this is pure frontend, no backend blocker. Build it:

1. **Opt-in review toggle** in the translate tab. The SSE request already supports
   `review_terms?: boolean` (`TranslateRequest` in `types.ts`); send it from the translate call
   in `translate-tab.tsx` (`api.translateStream`). Persist the toggle (per project, like the
   draft) is a nice-to-have.
2. **Term-review panel** after a translation completes. When `review_terms` was true, the SSE
   `done` event carries `matches: TermMatch[]` (`SseDoneEvent.matches`, already typed). Render a
   lightweight approve/reject list per match using `api.setGlossaryStatus(termId, status)`
   (already in the client). Keep it a highlight + panel, NOT an inline-edit studio.
3. **Output highlighting** — basic occurrence highlight of matched `surface_form`s in the
   English pane. `TermMatch` has `surface_form`/`count`/`snippets`.
4. **History retro-review** — viewing a saved translation re-runs matching via
   `api.getTranslationMatches(tid)` (already in the client), feeding the same panel.

Reuse `translation-review.tsx`'s pattern (per-row confirm/reject, lightweight) — 14.6's panel
is its close sibling. Mount the panel the same way (only for a persisted/just-finished
translation). Flag any real design decision (esp. how highlighting interacts with the streaming
output pane) before building.

## Verify as you go

`cd frontend; npm run build` must be clean. Backend offline for end-to-end:
`cd backend; $env:NB_ENGINE="mock"; .\run.ps1` (dev proxy `/api` → `:8000`). Experimental
endpoints 404 when their flag is off — treat 404 as "feature off, render nothing", never crash.

## Known: `npm run lint` is red (pre-existing)

Not fixed this session (deliberately — out of the feature scope). 12 errors, mostly
`react-refresh/only-export-components` on shadcn `ui/*` primitives (badge/button/tabs) and
`react-hooks/set-state-in-effect` (used across the codebase: `translate-tab`, `use-projects`,
and the new `translation-review`). Recommended as a separate `chore(lint)` pass: relax the
`react-refresh` rule for `components/ui/**` and decide a project stance on `set-state-in-effect`
— a config decision, not per-feature patches. The build gate (tsc+vite) is green.
