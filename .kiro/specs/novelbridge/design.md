# Design Document

## Overview

NovelBridge is a local-first web application that translates raw Chinese or Japanese novel
chapters into English while preserving consistency with previously translated chapters and a
user-maintained glossary. This document describes the technical design of the proof-of-concept
(PoC): a monorepo with a FastAPI backend, a Vite + React + shadcn/ui frontend, SQLite storage
behind a storage interface, and a pluggable translation engine whose default implementation
targets an Ollama instance on the user's home server.

The design is deliberately layered so that the two environment-specific concerns, the
**storage backend** and the **translation engine**, sit behind interfaces. This keeps the PoC
fully local (no cloud dependency) while leaving a clean path to swap SQLite for DynamoDB and
Ollama for Amazon Bedrock or Gemini later, satisfying Requirements 5 and 6 without a rewrite.

### Goals addressed

- Consistent, context-aware CN/JP to English translation (Requirements 2, 3, 4).
- Fully local operation with an AWS-ready structure (Requirement 6).
- Pluggable, configurable translation engine (Requirement 5).
- Durable per-series data across restarts (Requirements 1, 7).

### Verified assumptions

The following were confirmed against the live environment during design:

- Ollama is reachable at `http://192.168.254.22:11434`; model `qwen3.5:0.8b` is installed
  (max context length 262144; capabilities include completion and thinking).
- `/api/chat` streams newline-delimited JSON chunks shaped
  `{"message":{"content":"..."},"done":false}`, terminating with a `"done":true` chunk that
  carries timing statistics.
- Passing `"think": false` suppresses the model's reasoning preamble so only prose is streamed.
- `num_ctx` must be supplied in the request `options`; it is not inherited from Open WebUI.

## Architecture

### High-level topology

```
+-------------------+        HTTP (JSON + SSE)        +------------------------+
|   Frontend (SPA)  |  <--------------------------->  |   Backend (FastAPI)    |
|  Vite + React +   |                                 |  REST API + SSE relay  |
|  shadcn/ui + TS   |                                 |                        |
+-------------------+                                 |  +------------------+  |
                                                      |  | StorageService   |  |
                                                      |  |  (SQLite impl)   |  |
                                                      |  +------------------+  |
                                                      |  +------------------+  |
                                                      |  | TranslationEngine|  |
                                                      |  |  Ollama | Mock   |  |
                                                      |  +---------+--------+  |
                                                      +------------|-----------+
                                                                   | HTTP /api/chat (NDJSON)
                                                                   v
                                                      +------------------------+
                                                      |  Ollama home server    |
                                                      |  192.168.254.22:11434  |
                                                      +------------------------+
```

### Monorepo layout

```
kiro-challenge/
  backend/
    app/
      main.py                # FastAPI app factory, CORS, router registration
      config.py              # Settings loaded from environment (.env)
      api/
        projects.py          # project + nested reference/glossary/translation routes
        translate.py         # SSE translation endpoint
      storage/
        base.py              # StorageService interface (ABC)
        sqlite_store.py      # SQLite implementation
        schema.sql           # table DDL
      engines/
        base.py              # TranslationEngine interface + data classes
        ollama_engine.py     # default engine (native /api/chat, streaming)
        mock_engine.py       # offline deterministic engine
        factory.py           # engine selection from config
      services/
        context_builder.py   # assembles glossary + reference + raw within token budget
        prompt.py            # system/user prompt templates
      models.py              # Pydantic request/response models
    tests/
    requirements.txt
    .env.example
  frontend/
    src/
      api/                   # typed fetch client + SSE consumer
      components/            # shadcn-based UI pieces
      pages/                 # project view, translate (raw) + result (translated) panes
      lib/                   # types, utilities
    package.json
    vite.config.ts
  .kiro/
```

### Request flow for a translation

1. User pastes a raw chapter in the Translate pane and submits.
2. Frontend opens an SSE connection to `POST /api/projects/{id}/translate` with
   `{ raw_text, source_lang }`.
3. Backend loads the project glossary and reference chapters via `StorageService`.
4. `context_builder` assembles the prompt: full glossary, the raw chapter, and the tail of the
   most recent reference chapter, trimmed to fit the configured token budget (a note is added
   when truncation occurs).
5. The selected `TranslationEngine` streams output chunks; the backend relays each as an SSE
   `data:` event.
6. On completion the backend persists the translation (auto-save) and emits a final SSE event
   containing the saved translation's id.
7. Frontend renders tokens live in the translated pane, then marks the result as saved.

### Configuration (environment variables)

| Variable                   | Purpose                                  | Default                       |
| -------------------------- | ---------------------------------------- | ----------------------------- |
| `NB_ENGINE`                | Which engine to use (`ollama` or `mock`) | `ollama`                      |
| `OLLAMA_BASE_URL`          | Ollama server base URL                   | `http://192.168.254.22:11434` |
| `OLLAMA_MODEL`             | Model tag                                | `qwen3.5:0.8b`                |
| `OLLAMA_NUM_CTX`           | Context window passed in request options | `16384`                       |
| `OLLAMA_THINK`             | Whether to allow model thinking          | `false`                       |
| `NB_CONTEXT_BUDGET_TOKENS` | Total token budget for assembled context | `12000`                       |
| `NB_DB_PATH`               | SQLite file path                         | `./novelbridge.db`            |
| `NB_CORS_ORIGINS`          | Allowed frontend origins                 | `http://localhost:5173`       |

The backend validates required engine settings at startup and fails fast with a clear message
if a selected engine is missing configuration (Requirement 5, criterion 6).

## Components and Interfaces

### TranslationEngine interface

All engines conform to one interface so the rest of the system is engine-agnostic
(Requirement 5). The interface is streaming-first; non-streaming engines yield a single chunk.

```python
@dataclass
class TranslationRequest:
    raw_text: str
    source_lang: str          # "zh" | "ja"
    glossary: list[GlossaryEntry]
    reference_context: str     # pre-trimmed by context_builder
    model: str | None = None

@dataclass
class TranslationChunk:
    content: str
    done: bool
    meta: dict | None = None   # timing/model stats on the final chunk

class TranslationEngine(ABC):
    name: str
    @abstractmethod
    async def stream(self, req: TranslationRequest) -> AsyncIterator[TranslationChunk]: ...
    @abstractmethod
    async def health(self) -> bool: ...
```

- `OllamaEngine` calls `POST {base_url}/api/chat` with `stream=true`, `think=false`, and
  `options.num_ctx`, parsing NDJSON lines into `TranslationChunk`s. It strips any residual
  `<think>...</think>` block as a safeguard.
- `MockEngine` requires no network: it echoes the raw text with glossary substitutions applied
  and a `[MOCK]` marker, streamed in small slices so the UI path is exercised offline
  (Requirement 5, criterion 3).
- `factory.get_engine(settings)` returns the configured engine instance.

### StorageService interface

Persistence sits behind an abstract service so SQLite can later be replaced by DynamoDB
(Requirement 6, criterion 2).

```python
class StorageService(ABC):
    # projects
    def list_projects(self) -> list[Project]: ...
    def create_project(self, name: str, source_lang: str | None) -> Project: ...
    def get_project(self, pid: str) -> Project | None: ...
    def delete_project(self, pid: str) -> None: ...
    # references
    def list_references(self, pid: str) -> list[ReferenceChapter]: ...
    def add_reference(self, pid: str, title: str, content: str) -> ReferenceChapter: ...
    def delete_reference(self, ref_id: str) -> None: ...
    # glossary
    def list_glossary(self, pid: str) -> list[GlossaryEntry]: ...
    def upsert_glossary(self, pid: str, source_term: str, translation: str, note: str | None) -> GlossaryEntry: ...
    def update_glossary(self, entry_id: str, **fields) -> GlossaryEntry: ...
    def delete_glossary(self, entry_id: str) -> None: ...
    # translations
    def save_translation(self, pid: str, source_lang: str, raw_text: str, output_text: str, model_used: str) -> Translation: ...
    def list_translations(self, pid: str) -> list[Translation]: ...
    def get_translation(self, tid: str) -> Translation | None: ...
```

The SQLite implementation uses `sqlite3` with foreign keys enabled and `ON DELETE CASCADE` so
deleting a project removes its references, glossary, and translations (Requirement 1,
criterion 4).

### Context builder

`context_builder.build(glossary, references, raw_text, budget)` returns the trimmed
`reference_context` string plus a `truncated: bool` flag. Strategy (Requirement 4, criteria
1-2; design decision Q9):

1. Reserve budget for the system prompt, the full glossary, the full raw chapter, and headroom
   for the model's reply.
2. Fill the remaining budget with the **tail** of the most recently added reference chapter
   (most relevant for narrative continuity).
3. If references exceed the remaining budget, truncate from the start and prepend a short
   `[earlier reference omitted]` note.

Token counting for the PoC uses a cheap heuristic (character-based estimate) rather than a
model tokenizer, kept behind a single function so it can be upgraded later.

### Prompt construction

A system prompt instructs the model to act as a literary translator, honor the glossary as
authoritative for names/terms, match the tone and style of the reference text, and output only
the translation. The user message contains the glossary block, the reference-context block,
and the raw chapter, each clearly delimited.

### HTTP API

| Method | Path                              | Purpose                                              |
| ------ | --------------------------------- | ---------------------------------------------------- |
| GET    | `/api/projects`                   | List projects                                        |
| POST   | `/api/projects`                   | Create project `{name, source_lang?}`                |
| GET    | `/api/projects/{id}`              | Project detail with counts                           |
| DELETE | `/api/projects/{id}`              | Delete project (cascade)                             |
| GET    | `/api/projects/{id}/references`   | List references                                      |
| POST   | `/api/projects/{id}/references`   | Add reference `{title, content}`                     |
| DELETE | `/api/references/{refId}`         | Delete reference                                     |
| GET    | `/api/projects/{id}/glossary`     | List glossary entries                                |
| POST   | `/api/projects/{id}/glossary`     | Create entry `{source_term, translation, note?}`     |
| PUT    | `/api/glossary/{entryId}`         | Update entry                                         |
| DELETE | `/api/glossary/{entryId}`         | Delete entry                                         |
| POST   | `/api/projects/{id}/translate`    | SSE: stream translation of `{raw_text, source_lang}` |
| GET    | `/api/projects/{id}/translations` | List saved translations                              |
| GET    | `/api/translations/{tid}`         | Get one saved translation                            |
| GET    | `/api/health`                     | Liveness + configured engine health                  |

The translate endpoint returns `text/event-stream`. Events: repeated `data: {"content": "..."}`
chunks, then a terminal `data: {"done": true, "translation_id": "..."}` event. All other
endpoints exchange JSON.

### Frontend structure

- **Layout:** a shadcn sidebar listing projects (create/select/delete) and a main area with
  tabs: References, Glossary, Translate (Requirement layout decision Q11).
- **Translate experience:** the raw input and the translated output are presented as separate
  panes so each can be read on its own; the output pane streams tokens live via an SSE consumer.
- **API client:** a thin typed fetch wrapper plus a dedicated SSE reader that parses the event
  stream and exposes an async iterator of chunks to the component layer.
- **Styling:** Tailwind + shadcn/ui components only; no additional heavy UI library.

## Data Models

### Entity relationships

```
Project 1---* ReferenceChapter
Project 1---* GlossaryEntry   (unique per source_term within a project)
Project 1---* Translation
```

### SQLite schema

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE projects (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  source_lang TEXT,
  created_at  TEXT NOT NULL
);

CREATE TABLE reference_chapters (
  id          TEXT PRIMARY KEY,
  project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title       TEXT NOT NULL,
  content     TEXT NOT NULL,
  created_at  TEXT NOT NULL
);

CREATE TABLE glossary_entries (
  id          TEXT PRIMARY KEY,
  project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_term TEXT NOT NULL,
  translation TEXT NOT NULL,
  note        TEXT,
  UNIQUE (project_id, source_term)
);

CREATE TABLE translations (
  id          TEXT PRIMARY KEY,
  project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_lang TEXT NOT NULL,
  raw_text    TEXT NOT NULL,
  output_text TEXT NOT NULL,
  model_used  TEXT NOT NULL,
  created_at  TEXT NOT NULL
);
```

Primary keys are string UUIDs so the model maps cleanly to a future DynamoDB design
(`project_id` as partition key, entity id as sort key) without schema churn.

### Pydantic models (API layer)

Request and response bodies are typed with Pydantic (`ProjectCreate`, `ReferenceCreate`,
`GlossaryCreate`, `GlossaryUpdate`, `TranslateRequest`) and serialized response models mirror
the entities above. The `source_lang` field is constrained to `zh` or `ja`.

## Error Handling

| Condition                              | Backend behavior                                  | User-facing result                                |
| -------------------------------------- | ------------------------------------------------- | ------------------------------------------------- |
| Empty project name                     | 422 validation error                              | Inline validation message (Req 1.5)               |
| Empty reference content                | 422 validation error                              | Inline validation message (Req 2.4)               |
| Duplicate glossary term                | Upsert existing term rather than duplicate        | Entry updated, no conflict (Req 3.4)              |
| Engine unreachable / errors mid-stream | Emit SSE `error` event; do not clear client input | Error banner; pasted raw text preserved (Req 4.5) |
| Missing engine config at startup       | Raise on startup with explicit message            | Backend refuses to start (Req 5.6)                |
| Translate with no references           | Proceed; `reference_context` empty                | Works, UI notes "no context available" (Req 2.5)  |
| Unknown project / entity id            | 404                                               | Not-found message                                 |

The frontend keeps the user's raw input in component state independent of the request lifecycle,
so a failed or interrupted translation never loses pasted text (Requirement 4, criterion 5).
The SSE consumer surfaces `error` events distinctly from normal completion.

## Testing Strategy

The PoC favors a small, high-value test set over broad coverage.

- **Storage unit tests:** CRUD for each entity against a temporary SQLite file, including
  cascade delete and the glossary uniqueness/upsert rule.
- **Context builder unit tests:** verify glossary and raw are always retained, references are
  trimmed to budget, and the truncation flag/note is set correctly at boundary sizes.
- **Engine tests:** `MockEngine` streams deterministic chunks (no network).
  `OllamaEngine` is tested against a stubbed HTTP client that replays recorded NDJSON lines,
  asserting correct parsing and `<think>` stripping.
- **API tests:** FastAPI `TestClient` covers project/reference/glossary CRUD and validation
  errors; the translate endpoint is exercised with the mock engine to assert the SSE event
  sequence and that a translation row is auto-saved on completion.
- **Manual verification:** one end-to-end translation against the live Ollama server
  (`qwen3.5:0.8b`) to confirm the real streaming path, performed during the implementation's
  final verification step.

Automated tests default to the mock engine so the suite runs with no network and no Ollama
dependency, consistent with the local-first, offline-capable design.
