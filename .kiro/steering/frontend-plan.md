# NovelBridge — Frontend Plan (next work)

The backend is complete and verified. The frontend is spec tasks 6-9 in
`.kiro/specs/novelbridge/tasks.md`. Build it in that order, pausing after the scaffold+shell.

## Decisions (settled)

- **Vite + React + TypeScript + Tailwind + shadcn/ui.** shadcn is officially supported on Vite;
  use its CLI (`npx shadcn@latest init`) and the `@` path alias. Keep styling to Tailwind +
  shadcn only — no additional heavy UI library.
- **Layout**: a sidebar listing projects (create / select / delete-with-confirm) + a main area
  with tabs: **References**, **Glossary**, **Translate**.
- **Translate view**: raw input and translated output shown as **separate panes** so each reads
  on its own. Output streams tokens live via the SSE endpoint.
- Vite dev server on `:5173`, dev-proxy `/api` -> `http://127.0.0.1:8000` (matches backend CORS).

## Build order (tasks 6-9)

1. **Task 6 — scaffold**: Vite React+TS app in `frontend/`, Tailwind + shadcn init, `@` alias,
   dev proxy. Add a typed API client (`src/api/`) and an **SSE consumer** utility that parses
   `text/event-stream` into an async iterator of events. PAUSE HERE for the author to confirm it runs.
2. **Task 7 — shell**: sidebar (projects CRUD, confirm on delete) + tabbed main area + empty states.
3. **Task 8 — References & Glossary tabs**: paste title+content to add references (list/view/delete,
   empty validation); add/edit/delete glossary entries (source_term + translation + optional note;
   duplicate source_term upserts).
4. **Task 9 — Translate workspace**: source-language selector (zh/ja); submit raw text to the SSE
   endpoint; render tokens live; in-progress indicator; **preserve raw text on error**; show saved
   state; surface "no context available" when the project has no references.

## SSE consumer notes

The browser-native `EventSource` only does GET. The translate endpoint is a POST with a JSON body,
so use `fetch()` with a streaming reader (`response.body.getReader()`) and parse `data: {...}` lines
manually. Handle three event shapes: `{content}`, `{info}`, `{done, translation_id}`, `{error}`.

## API contract

See `tech.md` for the full endpoint list and the exact SSE event shapes. Do not change backend
endpoints from the frontend; if a contract change is needed, update the backend + `tech.md` together.

## Starter prompt for a fresh frontend session

> Build the NovelBridge frontend (spec tasks 6-9 in `.kiro/specs/novelbridge/tasks.md`).
> The backend is done and running on `:8000`. Follow the steering docs. Start with task 6
> (Vite + React + TS + Tailwind + shadcn scaffold, dev proxy, typed API client, SSE consumer),
> then STOP so I can confirm it runs before you build the shell and tabs. Keep the token
> budget tight and flag major decisions.
