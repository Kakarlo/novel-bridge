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

## Backlog (post-testing; see `tech.md` and `tasks.md`)

1. **Dark mode (keep simple)**: `.dark` tokens already exist — add a toggle on `<html>` with
   localStorage + `prefers-color-scheme` on first load, wire the toaster theme to it, small
   unobtrusive toggle (sidebar footer). No theme-settings panel. Avoid a flash of wrong theme.
2. **Delete saved translations (UI)**: per-row trash in `history-panel.tsx` guarded by
   `ConfirmDialog`, calling `DELETE /api/translations/{tid}`. Depends on that backend endpoint
   shipping first; reset the panes if the loaded translation is deleted; refresh the count.
3. **Scroll-follow fix**: in `translate-tab.tsx`, only autoscroll the output pane when the user
   is pinned near the bottom, so they can scroll up mid-stream. Optional "jump to latest"
   affordance; respect reduced-motion.
4. **Model-status indicator**: poll `GET /api/health` ({status, engine, model}) lightly; show
   engine + model + a reachable dot; make `engine=="mock"` obvious. Groundwork before any model
   picker. **The model picker itself is a backend-first TODO — don't build it yet.**

## Working rules

Flag major decisions for confirmation even in autopilot. `npm run build` (tsc + vite) must be
clean. No new deps beyond Tailwind/shadcn. One local commit per task; no git remote without
asking.
