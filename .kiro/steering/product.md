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

### What makes NovelBridge different (the novelty)

The closest comparables are **OpenNovel** (opennovel.co) and **OmniTranslate** (readomni.com,
the original inspiration). Both are polished, closed products running their own
translation-tuned models on free/paid tiers, with browser extensions that scrape a novel's
table of contents for batch processing. Crucially, **both already do glossary + in-context
term editing well** (OmniTranslate even highlights terms in the reader and lets you edit them
inline; OpenNovel has characters/titles/terms plus per-character gender). So the glossary and
in-context approval are **table stakes, not our novelty** — features we must do competently to
be credible, but which don't by themselves win anyone over.

Our actual differentiators, and where effort should go:

- **Model-agnostic harness.** The competitors lock you to their model. NovelBridge is a pure
  harness that makes _any_ model — especially a **free/local LLM** — produce a decent,
  consistent read. The immediate goal is "good enough translation from a local model"; an
  optimized flow for paid/hosted models is a follow-up.
- **Open-source and local-first.** No account, no per-chapter cost, data stays on the user's
  machine. That's a category difference from the closed SaaS competitors.
- **User-editable prompts per task.** Because the user can't fine-tune the model, the **prompt
  is the tuning surface.** A settings area will let users customize the prompts for each task
  (translation, glossary/key-term extraction, reference summary) for different genres and
  models. A closed product hides its prompt because the model is its moat; for us, exposing and
  tuning the prompt _is_ the moat.

Where this is heading (do not build ahead of these, but don't block them either):

- **Bring-your-own LLM API token.** Beyond local Ollama, let a user plug in an API key for a
  hosted model so translation "just works" without running anything locally. Engine stays
  behind the `TranslationEngine` interface so adding a hosted-API engine is additive.
- **Browser/batch ingestion (far future, maybe never — scraping is explicitly out for now).**
  Competitors scrape tables of contents; we stay paste-only per the hard constraint below.
- **Local-first now, accounts + cloud later.** Everything runs locally today (SQLite, local
  storage). _If_ adoption happens, accounts + cloud-stored projects become worthwhile. Keep
  storage behind `StorageService` so that swap is cheap. **Do not build accounts/cloud now.**
- **Current focus: ease of use and reading quality**, not infrastructure. The English-first
  glossary keeps names consistent across a series (the consistency mechanism / table stakes);
  the harness novelty above is what the project is actually betting on.

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
- **Active major feature: English-first glossary with in-context approval (table stakes).**
  References are English, so extracted candidate terms are English surface forms; the user adds
  a name by its English form alone and **approves/rejects** it when it appears in a translation
  (no hunting for the source term). Approved terms steer the prompt as _preferred spellings_ (a
  guide, not a hard find-and-replace — see the glossary constraint below). Settled decisions
  (Phase 0, agreed with the author):
  - Redefine `glossary_entries` English-first, **no migration** (no production data; recreate
    the dev DB). Scope add: a `category` (`character|title|term`) and a nullable `gender`
    (characters) — borrowed from OpenNovel because gender steers the pronoun drift common in
    zh→en, and title preference (师兄 → "Senior Brother" vs "Shixiong") is per-reader.
  - Extracted terms start as **`candidate`** and require user **approval** before they reach the
    prompt. `rejected` terms are simply kept out of the prompt for now; a dedicated "avoid"
    category (steer the model _away_ from a spelling) is a **separate future track**, not the
    same as rejecting meaningless noise candidates.
  - **Term review (occurrence matching + approve/reject) is opt-in**, toggled in settings — some
    users just want a translation without the review loop.
  - **Atomic engine tasks:** key-term extraction and source↔translation term matching are
    separate, small-context-friendly engine calls so a weak local model does one narrow job at a
    time. Keeps the harness usable on `qwen3.5:0.8b`-class models.
  - Keep the in-context review UI **lightweight** — basic occurrence highlighting + a review
    panel, not a full inline-edit "review studio" (that's where OmniTranslate already spends;
    matching it pixel-for-pixel wins nothing).
  - Match results fold into the translate `done` event; saved translations get a
    `GET /translations/{tid}/matches` endpoint for retro-review.
    Plan + phases live in spec task 14 and `tech.md`. **Flag major decisions before building,
    even on autopilot.**
- **Next novelty track after the glossary: user-editable prompts (settings).** A settings area
  to customize the prompt per task (translation, extraction, summary). This is the clearest
  differentiator for the local-LLM goal; sequence it right after the glossary data layer.
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
- **Glossary is a _guide_, not a hard substitution.** Approved terms are fed to the model as
  preferred spellings so it stays consistent while remaining free to prioritize flow and
  context (this mirrors OmniTranslate's own stance that terms are suggestions, not strict
  rules). We do **not** post-process the output with find-and-replace. In-context matching only
  _detects_ occurrences for the approve/reject loop; it never rewrites the translation.
- **Glossary + in-context approval are table stakes, not the novelty.** The competitors already
  ship them. Build them solid and credible, then stop — don't over-invest in review-studio
  polish. The novelty (model-agnostic, local, open, user-editable prompts) is where effort
  compounds. See the north star.
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
