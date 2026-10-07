# NovelBridge — Product & Project Context

## What this is

A local-first web app that translates Chinese/Japanese web-novel chapters into English, keeping names, terminology, and tone consistent across a series via a glossary and reference chapters.

## Differentiators

- **Model-agnostic harness.** Works with any LLM (local Ollama, Gemini, OpenRouter). Competitors lock you to theirs.
- **Open-source and local-first.** No account, no per-chapter cost, data stays in the browser.
- **User-editable prompts (next novelty track, task 22).** The prompt is the only tuning surface for a local model — exposing it is the moat.

Glossary + in-context approval are **table stakes** (competitors have them). Build them solid, don't over-invest.

## Current state

All original spec tasks (1–10) done. Post-PoC features shipped: concurrency cap, dark mode, English-first glossary (14.1–14.7), model picker + BYO-key (tasks 15, 21), local-first idb storage (tasks 23.1–23.4d), custom Ollama URL in picker (23.5). 189 backend tests pass. Deployment guide at `DEPLOYMENT.md`.

Next: task 22 (user-editable prompts). See `tasks.md` for the full live list.

## Hard constraints

- Monorepo: `backend/` (FastAPI) + `frontend/` (Vite). Vite dev-proxies `/api` to the backend.
- Storage behind `StorageService` ABC; engine behind `TranslationEngine` ABC — keep them.
- References are **pasted text only**. No scraping.
- Glossary is a **guide**, not a substitution — approved terms steer the prompt, never find-and-replace output.
- Source languages: `zh` and `ja` only.
- No accounts/cloud yet. No git remote without asking.

## How to run

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000   # real Ollama
$env:NB_ENGINE="mock"; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000  # offline
```

Frontend dev server: `cd frontend; npm run dev`

## Working agreement

- Flag major decisions before building, even on autopilot.
- One local commit per task. No git push without asking.
- Keep tests offline on the mock engine.
