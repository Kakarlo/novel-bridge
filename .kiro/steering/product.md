# NovelBridge — Product & Project Context

## What this is

NovelBridge is a local-first web app that translates raw Chinese/Japanese web-novel
chapters into English, using previously translated chapters (pasted as reference) plus a
glossary so names, terminology, tone, and flow stay consistent. It exists because official
English translations of novels often get dropped partway through a series.

## North star & direction

The real pain point this solves: **reading a long series via raw LLM translation is an awful
experience.** Pasting chapters straight into an LLM sometimes works, but most of the time names
and terms drift and the tone wobbles, so immersion is gone. NovelBridge is a **harness that
makes a whole series read smoothly** — consistent names/terminology, reusable context, and a
clean reading UI — with minimal babysitting of the model.

Where this is heading (do not build ahead of these, but don't block them either):

- **Bring-your-own LLM API token.** Beyond local Ollama, let a user plug in an API key for a
  hosted model so translation "just works" without running anything locally. Engine stays
  behind the `TranslationEngine` interface so adding a hosted-API engine is additive.
- **Local-first now, accounts + cloud later.** Everything runs locally today (SQLite, local
  storage). _If_ adoption happens, accounts + cloud-stored projects become worthwhile. Keep
  storage behind `StorageService` so that swap is cheap. **Do not build accounts/cloud now.**
- **Current focus: ease of use and reading quality**, not infrastructure. The English-first
  glossary (names stay consistent across the series, validated in context) is the biggest lever.

## Status & scope

- This is a **portfolio-worthy project** (grown past the original PoC). The north star is a
  clean, genuinely useful reading harness — not just a demo. Keep scope local for now.
- The full spec lives in `.kiro/specs/novelbridge/` (requirements.md, design.md, tasks.md).
  Treat those as the source of truth; this steering file is a quick-orientation summary.

## Current state (keep this updated)

- **Backend: COMPLETE** (spec tasks 1-5), 24 tests passing, verified against live Ollama.
- **Frontend: COMPLETE** (spec tasks 6-9). Vite + React + TS + Tailwind v4 + shadcn/ui
  (radix base, Nova preset). Sidebar + References/Glossary/Translate tabs + live SSE translate.
  Typechecks and builds clean; verified end-to-end through the dev proxy against the mock engine.
- **Final verification + README: COMPLETE** (spec task 10). 24 backend tests pass; one live
  translation verified against Ollama `qwen3.5:0.8b` (real streaming + glossary + auto-save);
  top-level README added. All 10 original spec tasks are done.
- **Post-PoC backlog (spec tasks 11+ in `tasks.md`): mostly shipped.** Done: concurrency cap,
  delete-translation endpoint + UI, the reference-echo prompting bug + references→summary/
  candidate-terms, dark mode, scroll-follow fix, a model-status indicator backed by a **real
  engine health probe** (health now pings the engine instead of echoing config), and surfacing
  the reference summary + candidate terms in the UI (chips promotable to the glossary). Model
  picker still deferred (backend-first). See `tech.md` "Planned work & known issues".
- **Active major feature: English-first glossary with in-context approval.** References are
  English, so extracted candidate terms are English surface forms; the user adds a name by its
  English form alone and **approves/rejects** it when it appears in a translation (no hunting
  for the source term). Approved terms steer the prompt. Plan lives in the session artifact and
  spec task 14; implementation is phased. **Flag the open design decisions before building.**
- Git: local only, no remote yet. One commit per task on `main`.

## Hard constraints & decisions (do not silently change)

- **Monorepo**: `backend/` (FastAPI) + `frontend/` (Vite). Vite dev-proxies `/api` to the backend.
- **Local-first, AWS-ready**: must run fully locally with no AWS dependency. Keep storage behind
  the `StorageService` interface (SQLite now, DynamoDB later) and the engine behind the
  `TranslationEngine` interface (Ollama now, Gemini/Bedrock later). All env-specific values in config.
- **References are pasted text only. No scraping.** Evolving use: a reference is a source for a
  short summary + candidate glossary terms, not raw text to dump into the prompt (the raw dump
  causes the model to echo the reference — see the prompting bug in `tech.md`).
- **Glossary is for validation, not bulk data entry** (author's intent). References are already
  English, so the user knows the English name, not the source term. The direction is
  **English-first**: store English surface forms, match them against model output, and let the
  user **approve/reject each term in context** rather than entering source→target pairs. Classic
  paired entries stay supported; candidate terms from reference summaries seed the list.
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
