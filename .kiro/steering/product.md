# NovelBridge — Product & Project Context

## What this is

NovelBridge is a local-first web app that translates raw Chinese/Japanese web-novel
chapters into English, using previously translated chapters (pasted as reference) plus a
manual glossary so names, terminology, tone, and flow stay consistent. It exists because
official English translations of novels often get dropped partway through a series.

## Status & scope

- This is a **proof of concept** for learning and portfolio use. The author is based in the
  Philippines and is **not eligible** for Kiro University Challenge credits, so do NOT optimize
  for that challenge's rubric. The north star is a clean, working, demoable app.
- The full spec lives in `.kiro/specs/novelbridge/` (requirements.md, design.md, tasks.md).
  Treat those as the source of truth; this steering file is a quick-orientation summary.

## Current state (keep this updated)

- **Backend: COMPLETE** (spec tasks 1-5), 24 tests passing, verified against live Ollama.
- **Frontend: COMPLETE** (spec tasks 6-9). Vite + React + TS + Tailwind v4 + shadcn/ui
  (radix base, Nova preset). Sidebar + References/Glossary/Translate tabs + live SSE translate.
  Typechecks and builds clean; verified end-to-end through the dev proxy against the mock engine.
- **Final verification + README: COMPLETE** (spec task 10). 24 backend tests pass; one live
  translation verified against Ollama `qwen3.5:0.8b` (real streaming + glossary + auto-save);
  top-level README added. All 10 spec tasks are now done.
- Git: local only, no remote yet. One commit per spec task on `main`.

## Hard constraints & decisions (do not silently change)

- **Monorepo**: `backend/` (FastAPI) + `frontend/` (Vite). Vite dev-proxies `/api` to the backend.
- **Local-first, AWS-ready**: must run fully locally with no AWS dependency. Keep storage behind
  the `StorageService` interface (SQLite now, DynamoDB later) and the engine behind the
  `TranslationEngine` interface (Ollama now, Gemini/Bedrock later). All env-specific values in config.
- **References are pasted text only. No scraping.**
- **Glossary is manual.** Auto-suggest/extraction is an explicit stretch goal, not in the PoC.
- **Source languages: Chinese (zh) and Japanese (ja) only**, translating to English.
- **Translations auto-save** on stream completion.

## How to run

Backend (real translation via home-server Ollama, the default):

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Backend offline (no Ollama; deterministic mock engine):

```powershell
cd backend
$env:NB_ENGINE="mock"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Swagger UI at `http://127.0.0.1:8000/docs`, health at `/api/health`.

## Working agreement with the author

- Pace work deliberately to conserve Kiro tokens; prefer checkpoints over big-bang builds.
- **Flag major decision points for confirmation even in autopilot.**
- Commit locally after each meaningful task. Do not add a git remote or push without asking.
- Do not add tests beyond what's useful for the PoC unless asked.
