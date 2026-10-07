# NovelBridge — Frontend Plan

The initial frontend (spec tasks 6-9) is **built and committed**. This doc now tracks the
settled stack decisions and the post-testing backlog.

## Stack decisions (settled, do not re-litigate)

- **Vite + React + TypeScript + Tailwind v4 + shadcn/ui**, initialized via the shadcn CLI
  (`npx shadcn@latest init`) with the **radix base + "Nova" preset**, neutral base color, and
  the `@` path alias. Tailwind v4 via `@tailwindcss/vite`. Keep styling to Tailwind + shadcn
  only — no additional heavy UI library.
- **Layout**: sidebar listing projects (create / select / delete-with-confirm) + a main area
  with tabs: **References**, **Glossary**, **Translate**.
- **Translate view**: raw input and translated output as **separate panes**; output streams
  tokens live via the SSE endpoint. A **History panel** lists auto-saved translations and loads
  one read-only into the panes.
- Vite dev server on `:5173`, dev-proxy `/api` -> `http://127.0.0.1:8000`.

## Preset conventions (this shadcn setup is non-standard — follow these)

- `cn` is imported from the bare `"cn"` package (re-exported via `@/lib/utils`); primitives
  import from the unified `"radix-ui"` package (e.g. `import { Dialog } from "radix-ui"`).
- `Button` sizes: `xs | sm | default | lg | icon | icon-xs | icon-sm`; icon placement via
  `data-icon="inline-start"`. `Select` trigger takes `size="sm"`.
- Theme tokens live in `src/index.css` (`:root` + `.dark` already fully defined). One accent:
  `--accent-brand` (amber). A `prefers-reduced-motion` guard is already in place.
- `src/components/ui/sonner.tsx` was de-coupled from `next-themes` (this is a Vite app, not
  Next) — do not reintroduce `next-themes`.

## What exists

- `src/api/` — typed client (`client.ts`), types (`types.ts`), and a fetch-based SSE consumer
  (`sse.ts`) that parses `text/event-stream` into an async iterator (EventSource can't POST a
  body). Handles `{content}`, `{info}`, `{done, translation_id}`, `{error}` events.
- `src/components/` — `project-sidebar`, `project-workspace` (tabs + counts), `references-tab`,
  `glossary-tab`, `translate-tab`, `history-panel`, `confirm-dialog` (reusable), `empty-state`.

## North star (reading quality + ease of use)

The pain point is that reading a long series via raw LLM translation breaks immersion — names
drift, tone wobbles. The frontend's job is a **smooth reading harness**. Current focus is ease
of use and reading quality, not infrastructure. Future tracks (do not build yet): a
bring-your-own LLM API-token flow, and accounts/cloud only if adoption warrants it. See
`product.md`.

## Backlog (post-testing) — shipped

1. **Dark mode** — DONE. No-FOUC inline script in `index.html`, `use-theme.ts` (light/dark,
   localStorage + `prefers-color-scheme` first-load, follows OS until explicit choice), toggle
   in the sidebar footer, `Toaster` theme wired without `next-themes`.
2. **Delete saved translations (UI)** — DONE. Per-row trash in `history-panel.tsx` via
   `ConfirmDialog`; resets panes if the loaded translation is deleted; refreshes the count.
3. **Scroll-follow fix** — DONE. Stick-to-bottom autoscroll in `translate-tab.tsx` + "jump to
   latest"; reduced-motion respected.
4. **Model-status indicator** — DONE. `use-health.ts` polls `GET /api/health`;
   `model-status.tsx` in the sidebar footer shows engine + model + a reachable dot (green /
   amber for LLM-down / red for backend-down) and flags `engine=="mock"`. The backend health
   probe is now real (`reachable`). Model picker still a backend-first TODO — don't build it.
5. **Reference derived-context UI** — DONE. References reader shows summary + candidate-term
   chips with a "Re-summarize" action; chips promote into the glossary.
6. **Field-fix #2/#4 (reference derived context, refined)** — DONE. Two separate chip groups:
   rule-based "Detected names" (backend `detected_names`) and AI "Candidate terms". Promoted
   chips are hidden by cross-checking the glossary on load, so they survive refresh and don't
   pile up across references (`ReferenceChapter.detected_names`).
7. **Field feedback round 2 (desktop polish)** — DONE. (a) `project-workspace` tabs are
   `forceMount` + CSS-hidden so switching tabs never unmounts content — a streaming translation
   and the draft survive a tab switch. (b) Active tab is controlled + persisted per project
   (`nb:tab:{id}`); selected project persisted (`nb:active-project`) so a refresh returns to the
   same place. (c) Reference reader widened to ~78% / max-w-5xl. (d) Candidate/detected chips
   gained a dismiss (✕) action persisted per reference (`nb:dismissed-terms:{refId}`), separate
   from add-to-glossary. (e) Glossary row actions enlarged to `icon-sm` and always visible.
8. **Field-fix #1 (draft persistence + stream guardrails)** — DONE. `translate-tab` persists a
   per-project draft (raw + lang + partial output) to localStorage, restored on mount/project
   switch; an interrupted stream is restored as a recoverable draft. While streaming: a
   `beforeunload` native warning (refresh/close) and a confirm dialog on project switch, via a
   tiny app-wide `use-active-stream` store (`setStreaming`/`useIsStreaming`). Switching tabs
   keeps the stream alive (TranslateTab stays mounted). Server-side stream resume is out of
   scope (live HTTP connection; no job registry — documented).

## English-first glossary with in-context approval (spec task 14) — Phase 14.5 DONE

Glossary tab rebuilt English-first: add/edit a name by its English `surface_form` (required) with
a **category** select (character|title|term), a **gender** select (enabled only for characters),
an optional source term, and a note. Rows show a **status badge** (candidate|approved|rejected)
and a **category/gender badge**, with hover **approve/reject** controls (`api.setGlossaryStatus`)
and a **status filter** (all/candidate/approved/rejected with counts). Classic paired entries
still work (source term + English name → approved). Note: a manually added English-only name
starts as `candidate` (same rule as promoted terms) — approve it to make it steer the model.
Remaining: Phase 14.6 in-context review UI (translate tab) + the opt-in review toggle.

**Local-first review on the idb backend (task 23.4d) — DONE.** `TranslationReview` (translate
tab, source-side panel over a saved translation) is no longer gated to the API backend — it
renders on both. Term-occurrence detection moved client-side: `findOccurrences`
(`src/lib/term-match.ts`, a port of `services/term_match.py`) powers a `getTranslationMatches`
method on the `StorageService` (API impl → server endpoint, idb impl → local compute), so the
backend-switch lives in one place. The panel's "Suggest pairs" LLM call ships the saved
translation's `raw_text`/`output_text`/`source_lang` in the body on idb (stateless
`extract-glossary`, no server row); `confirmPair` writes through `getStorage().createGlossary`,
so approve works locally. Source-language terms stay API-only/experimental and degrade to empty
on idb.

### Earlier plan (kept for reference)

This is **table stakes** (the competitors already have it) — build it clean and credible, keep
the review UI **lightweight**, and don't pour effort into an inline-edit review studio.
References are English, so candidate terms are English surface forms. The user adds a name by
its English form alone and **approves/rejects** it when it appears in a translation. Frontend
surface:

- **Glossary tab:** "Add name (English only)" with **category** (`character|title|term`) and an
  optional **gender** (characters), status badges (`candidate|approved|rejected`),
  approve/reject controls, status filter. Keep the classic paired-entry editor working.
- **Translate tab:** term review is **opt-in** (a settings toggle). When on, after a translation
  completes a **term-review panel** lists matched terms with Approve / Reject and occurrences
  are highlighted in the output pane (basic highlight, not click-to-edit).
- **History:** viewing a saved translation re-runs matching (via a matches endpoint) for
  retrospective review.

Phased with the backend (see `tasks.md` 14.1–14.7) so the HTTP contract changes once. Flag the
open design decisions before building.

## After that — user-editable prompts (settings) — the novelty track (spec task 22)

A settings surface to customize the prompt per engine task (translation, extraction, summary),
with "reset to default" and a view of the effective prompt. This is the clearest frontend lever
on the local-LLM reading-quality goal. Spec it after task 14's data layer; flag the design
first.

## Working rules

Flag major decisions for confirmation even in autopilot. `npm run build` (tsc + vite) must be
clean. No new deps beyond Tailwind/shadcn. One local commit per task; no git remote without
asking.
