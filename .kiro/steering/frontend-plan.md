# NovelBridge — Frontend Plan

## Stack (settled)

- **Vite + React + TypeScript + Tailwind v4 + shadcn/ui** (radix base, Nova preset, `@` alias).
- Tailwind + shadcn only — no additional UI libraries.
- Vite dev proxy: `/api` → `http://127.0.0.1:8000`.

## shadcn conventions (non-standard setup)

- `cn` from the bare `"cn"` package via `@/lib/utils`; primitives from the unified `"radix-ui"` package.
- `Button` sizes: `xs | sm | default | lg | icon | icon-xs | icon-sm`.
- Theme tokens in `src/index.css`. One accent: `--accent-brand` (amber). `prefers-reduced-motion` guard in place.
- `sonner.tsx` decoupled from `next-themes` — do not reintroduce it.

## What's shipped

Full feature list in `tasks.md`. In brief: sidebar + References/Glossary/Translate tabs, live SSE streaming, dark mode, history panel, English-first glossary with in-context review (`translation-review.tsx`), model picker + BYO-key (Ollama/Gemini/OpenRouter), custom Ollama URL field, idb (IndexedDB/Dexie) storage backend with export/import, data manager.

`src/storage/` — `StorageService` interface, `ApiStorageService` (REST), `IndexedDbStorage` (Dexie). Active backend selected by `VITE_STORAGE_BACKEND` (`idb` for hosted, `api` for local dev).

## Open frontend TODOs

- **`BACKEND_TODO.md` #1** — chapter-number override endpoint not yet built; the `Ch N` inline edit in `references-tab.tsx` is still a display-only UI.
- **Task 22** — user-editable prompts settings UI (next novelty track, not yet built).

## Rules

- `npm run build` (tsc + vite) must be clean before calling a task done.
- No new deps beyond Tailwind/shadcn.
- Flag major decisions before building.
- One local commit per task; no git remote without asking.
