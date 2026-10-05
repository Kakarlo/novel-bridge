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

## Next major frontend work — English-first glossary with in-context approval (spec task 14)

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
