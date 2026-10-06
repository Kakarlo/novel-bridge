# NovelBridge

A local-first web app that translates raw Chinese or Japanese web-novel chapters into
English, keeping names, terminology, tone, and flow consistent across a series. It does this
by feeding the model two things alongside the raw chapter: a **manual glossary** of
authoritative terms and a **reference chapter** (a previously translated chapter you paste in)
so new chapters match the established voice.

It exists because official English translations of long-running novels often get dropped
partway through a series. NovelBridge lets a reader keep going with consistent output.

> Proof-of-concept for learning and portfolio use. It runs fully locally with no cloud
> dependency, but the storage and translation layers sit behind interfaces so SQLite could be
> swapped for DynamoDB and Ollama for Bedrock/Gemini without a rewrite.

## Features

- **Projects (series)** — create a series, pick its source language (Chinese or Japanese).
- **Glossary** — authoritative name/term mappings; the model is instructed to follow them
  exactly. Re-adding a term upserts it rather than duplicating.
- **References** — paste previously translated chapters. Upload is lightweight (stores the text
  and runs an offline proper-noun detector). Their real value is the **writing style**: extract
  a per-project **style profile** from a reference chapter (one LLM pass), which is injected into
  every translation prompt so the voice, register, and conventions stay consistent across the
  series. The style profile can also be written or edited by hand.
- **Translate** — paste a raw chapter and watch the English stream in token-by-token over SSE.
  Translations auto-save on completion and are browsable from a history panel.
- **Engines** — local **Ollama** (default) or cloud **OpenRouter** / **Gemini** (bring your own
  API key), all behind one `TranslationEngine` interface. Select via `NB_ENGINE`.

## Architecture

A monorepo with two parts that talk over HTTP (JSON + Server-Sent Events):

```text
frontend/   Vite + React + TypeScript + Tailwind v4 + shadcn/ui   (dev server :5173)
backend/    FastAPI + httpx, SQLite storage, pluggable engine      (API server :8000)
```

- **Storage** sits behind a `StorageService` interface. Default implementation: SQLite via the
  stdlib `sqlite3`, with foreign keys and `ON DELETE CASCADE`.
- **Translation** sits behind a `TranslationEngine` interface. Two implementations:
  - `OllamaEngine` (default) — streams from an Ollama instance via native `POST /api/chat`.
  - `MockEngine` — deterministic, no network; echoes the raw text with glossary substitutions
    applied. Used for offline development and the automated test suite.
- In development, the Vite server proxies `/api` to the backend on port 8000, so the browser
  only ever talks to `:5173`.

Full requirements, design, and the task plan live in `.kiro/specs/novelbridge/`.

## Prerequisites

- **Python 3.13** (backend)
- **Node 24 / npm 11** (frontend)
- **Ollama** reachable on your network for real translations (optional — the mock engine needs
  nothing). The defaults target a home server at `http://192.168.254.22:11434` running
  `qwen3.5:0.8b`; override via environment variables (see below).

## Running it

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env   # then edit if your Ollama server differs
```

Then start it with the run script:

```powershell
.\run.ps1          # real translation (default engine, needs Ollama)
.\run.ps1 -Mock    # offline / no Ollama (deterministic mock engine)
.\run.ps1 -Port 9000   # custom port
```

The API serves at `http://127.0.0.1:8000` — Swagger UI at `/docs`, health at `/api/health`.

> On macOS/Linux use `./run.sh` (and `./run.sh --mock`). The scripts just wrap
> `.venv/.../python -m uvicorn app.main:app`, so that longer form still works if you prefer it.

### 2. Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The dev server proxies `/api` to the backend, so start the
backend first.

## Configuration

All backend config is environment-driven (see `backend/.env.example`):

| Variable                   | Purpose                                  | Default                       |
| -------------------------- | ---------------------------------------- | ----------------------------- |
| `NB_ENGINE`                | Engine to use (`ollama` or `mock`)       | `ollama`                      |
| `OLLAMA_BASE_URL`          | Ollama server base URL                   | `http://192.168.254.22:11434` |
| `OLLAMA_MODEL`             | Model tag                                | `qwen3.5:0.8b`                |
| `OLLAMA_NUM_CTX`           | Context window passed in request options | `16384`                       |
| `OLLAMA_THINK`             | Allow the model's thinking preamble      | `false`                       |
| `NB_CONTEXT_BUDGET_TOKENS` | Token budget for the assembled context   | `12000`                       |
| `NB_DB_PATH`               | SQLite file path                         | `./novelbridge.db`            |
| `NB_CORS_ORIGINS`          | Comma-separated allowed frontend origins | `http://localhost:5173`       |

Swap models with no code change: `qwen3.5:0.8b` (fast/rough), `qwen3.5:4b` (good),
`qwen3.5:9b` (best) via `OLLAMA_MODEL`.

## Testing

Backend tests default to the mock engine and a temporary SQLite file, so the suite runs fully
offline:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Frontend typecheck / build:

```powershell
cd frontend
npm run build
```

## HTTP API

| Method | Path                                       | Purpose                                  |
| ------ | ------------------------------------------ | ---------------------------------------- |
| GET    | `/api/health`                              | Liveness + configured engine             |
| GET    | `/api/projects`                            | List projects                            |
| POST   | `/api/projects`                            | Create project                           |
| GET    | `/api/projects/{id}`                       | Project detail with counts               |
| DELETE | `/api/projects/{id}`                       | Delete project (cascade)                 |
| GET    | `/api/projects/{id}/references`            | List references                          |
| POST   | `/api/projects/{id}/references`            | Add reference (lightweight; names only)  |
| POST   | `/api/references/{refId}/redetect`         | Re-run the offline name detector         |
| DELETE | `/api/references/{refId}`                  | Delete reference                         |
| POST   | `/api/projects/{id}/extract-style`         | Extract a style profile (LLM)            |
| PUT    | `/api/projects/{id}/style`                 | Set the style profile manually           |
| DELETE | `/api/projects/{id}/style`                 | Clear the style profile                  |
| GET    | `/api/projects/{id}/glossary`              | List glossary entries                    |
| POST   | `/api/projects/{id}/glossary`              | Create entry (upserts duplicate term)    |
| PUT    | `/api/glossary/{entryId}`                  | Update entry                             |
| DELETE | `/api/glossary/{entryId}`                  | Delete entry                             |
| POST   | `/api/translations/{tid}/extract-glossary` | LLM-paired source→English glossary       |
| POST   | `/api/projects/{id}/translate`             | SSE: stream a translation, then autosave |
| GET    | `/api/projects/{id}/translations`          | List saved translations                  |
| GET    | `/api/translations/{tid}`                  | Get one saved translation                |
| DELETE | `/api/translations/{tid}`                  | Delete one saved translation             |

The translate endpoint returns `text/event-stream`: repeated `data: {"content":"..."}` chunks,
an optional `data: {"info":"..."}` notice (reference truncation, or waiting for a free slot when
the concurrency cap is saturated), and a terminal `data: {"done":true,"translation_id":"..."}` —
or `data: {"error":"..."}` on failure, including a busy error when the queue wait exceeds
`NB_QUEUE_TIMEOUT_SECONDS` (the client preserves your input in that case).

## Project layout

```text
backend/
  app/
    api/         project/reference/glossary routes + SSE translate route
    engines/     TranslationEngine interface, Ollama + mock, factory
    storage/     StorageService interface, SQLite impl, schema
    services/    context builder (token budgeting) + prompt templates
    config.py    env-driven settings
    main.py      app factory, CORS, startup engine validation
  tests/
frontend/
  src/
    api/         typed client + fetch-based SSE consumer
    components/   sidebar, workspace, References/Glossary/Translate tabs
    hooks/, lib/
.kiro/specs/novelbridge/   requirements, design, tasks
```
