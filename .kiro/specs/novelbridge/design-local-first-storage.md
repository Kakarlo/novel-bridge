# Design: Local-First Storage + Local-Model Access (hosted, no user data in the cloud)

Status: PROPOSED — for review before implementation. Companion to `design.md`.

## 1. Goal

Make NovelBridge a **hosted web app that stores zero user content on the server**. All
user-owned data (projects, reference chapters, glossary, translation history) lives in the
user's browser, with **export/import** for backup and portability. The backend keeps only the
compute it must: translation and the AI/deterministic extraction passes. Users bring their own
LLM — a hosted key (already shipped) or their own local Ollama (section 6).

This is the architecture the project was built for: `StorageService` and `TranslationEngine`
are both interfaces, and the README/steering already name "swap storage later" as a goal. We
are now exercising that seam.

## 2. Target architecture

```
Browser (React)                         FastAPI (stateless compute)
├─ StorageService (frontend interface)  ├─ POST /api/translate        (SSE)
│   └─ IndexedDbStorage (new)           ├─ POST /api/extract-style
│       ├─ projects                     ├─ POST /api/extract-glossary
│       ├─ references                   ├─ POST /api/detect-names
│       ├─ glossary                     └─ GET  /api/health, /api/models
│       └─ translation history
├─ export / import (JSON file)
└─ credentials (provider/model in memory + localStorage; key in memory)
```

The backend no longer owns a database. It receives everything it needs for a given operation
in the request (raw text + glossary + style profile + engine creds) and returns the result.
Nothing about one user is retained between requests.

## 3. Why a frontend `StorageService` interface comes first (not SQLite-WASM first)

The database engine is NOT the risk — the **API coupling** is. Today the React components call
`api.listProjects()`, `api.createProject()`, etc. directly against REST. If we swap persistence
without an abstraction, every component changes.

So step one introduces a frontend interface that mirrors the backend's `StorageService`
(it already exists in `backend/app/storage/base.py` — we copy its shape to TypeScript):

```ts
export interface StorageService {
  // projects
  listProjects(): Promise<Project[]>;
  createProject(name: string, sourceLang: SourceLang | null): Promise<Project>;
  getProject(id: string): Promise<ProjectDetail | null>;
  deleteProject(id: string): Promise<void>;
  updateProjectStyle(id: string, styleProfile: string | null): Promise<Project | null>;
  // references
  listReferences(pid: string): Promise<ReferenceChapter[]>;
  addReference(pid: string, title: string, content: string): Promise<ReferenceChapter>;
  setReferenceDetectedNames(refId: string, names: string[]): Promise<ReferenceChapter | null>;
  removeReferenceTerm(refId: string, term: string): Promise<ReferenceChapter | null>;
  deleteReference(refId: string): Promise<void>;
  // glossary
  listGlossary(pid: string): Promise<GlossaryEntry[]>;
  addTerm(pid: string, input: GlossaryCreate): Promise<GlossaryEntry>;
  setTermStatus(entryId: string, status: GlossaryStatus): Promise<GlossaryEntry | null>;
  updateGlossary(entryId: string, patch: GlossaryUpdate): Promise<GlossaryEntry | null>;
  deleteGlossary(entryId: string): Promise<void>;
  // translations
  saveTranslation(pid: string, t: SaveTranslationInput): Promise<Translation>;
  listTranslations(pid: string): Promise<Translation[]>;
  getTranslation(tid: string): Promise<Translation | null>;
  deleteTranslation(tid: string): Promise<void>;
  // portability
  exportAll(): Promise<ExportBundle>;
  importAll(bundle: ExportBundle, mode: "merge" | "replace"): Promise<void>;
}
```

Two implementations, swappable with a one-line provider change, UI untouched:

- `ApiStorageService` — wraps the current REST client. Lets us ship the interface with ZERO
  behavior change, then migrate incrementally.
- `IndexedDbStorage` — the browser store (section 4). The target.

This is the single most important decision in the migration: **land the interface, keep the
backend, verify nothing broke, then swap the implementation.**

## 4. IndexedDB vs SQLite-WASM (the import/export question answered)

Your reason for SQLite-WASM was **export/import**. That is exactly the thing it does NOT do
better than IndexedDB. Here is the case:

### Export/import is identical difficulty either way

Both engines store structured records. Export = read every record and serialize to JSON.
Import = parse JSON and write every record. A JSON bundle is the right portable format
**regardless of engine** because:

- It is human-readable, diffable, and mergeable (so "share a glossary" / "merge projects"
  work — a raw SQLite `.db` file is an opaque binary you can only replace, not merge).
- It is engine-agnostic: a JSON export today imports into IndexedDB, and still imports into a
  SQLite-WASM build later if you ever switch, with no migration tool.
- It is tiny code: `JSON.stringify(await db.getAll())` to export; a loop of `put()` to import.

With SQLite-WASM the "export the whole .db file" path exists, but it ships a binary blob that
is harder to inspect, impossible to merge, and version-locked to the SQLite file format. For a
backup/share feature, JSON wins. **SQLite-WASM gives you nothing extra for export/import.**

### What SQLite-WASM actually costs

- ~1 MB+ wasm payload downloaded on first load.
- OPFS requires a Web Worker + cross-origin isolation headers (COOP/COEP) on the host, or it
  silently falls back to slower/limited storage. That is real hosting config.
- A SQL layer (and its bundle) to run queries over what is, in practice, a few hundred rows
  per user — all simple key/index lookups.

### What SQLite-WASM would actually buy

- Real SQL (joins, `WHERE`, aggregates). NovelBridge's access patterns are: list by project,
  get by id, upsert glossary by `surface_form`. These are plain key + one index — no joins,
  no ad-hoc queries. IndexedDB object stores + indexes cover every one.

### Recommendation

**IndexedDB**, accessed through the `StorageService` interface, with **JSON export/import**.
It is lighter, needs no special hosting headers, and delivers the exact import/export story you
want (and a _better_ one for merge/share). Because it is behind the interface, if a future
feature genuinely needs in-browser SQL, swapping to SQLite-WASM is an implementation change
with no UI or data-format churn — the JSON bundle still imports.

Practical note: use a thin wrapper (`idb`, ~1 KB, promise-based) rather than raw IndexedDB,
which has a famously awkward callback API. One small dependency, well-maintained.

### Export bundle shape

```jsonc
{
  "format": "novelbridge-export",
  "version": 1,
  "exported_at": "2026-...Z",
  "projects": [
    /* Project */
  ],
  "references": [
    /* ReferenceChapter (carries project_id) */
  ],
  "glossary": [
    /* GlossaryEntry (carries project_id) */
  ],
  "translations": [
    /* Translation (carries project_id) */
  ],
}
```

- Export: one file, download via a Blob + object URL.
- Import `replace`: wipe stores, write bundle. Import `merge`: upsert by id; for glossary,
  reuse the existing `surface_form` (case-insensitive) upsert rule so merging two glossaries
  dedupes cleanly.
- Validation: check `format`/`version`, tolerate missing arrays, reject unknown versions with
  a clear message. Treat an imported file as untrusted input.

## 5. Backend becomes stateless (contract changes)

Today several routes read storage server-side. In the target, the browser is the source of
truth, so the data rides in the request. Endpoints that change:

| Endpoint                            | Today                                           | Stateless target                                                                                                                 |
| ----------------------------------- | ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `POST /api/projects/{id}/translate` | loads glossary + style from DB by `pid`         | request body carries `glossary`, `style_profile`, `raw_text`, `selection`; no `pid`, no auto-save (the browser saves the result) |
| `POST /api/.../extract-style`       | reads newest reference from DB                  | body carries the reference `content`                                                                                             |
| `POST /api/.../extract-glossary`    | reads a saved translation from DB               | body carries `raw_text` + `output_text`                                                                                          |
| name detection                      | `POST /api/references/{id}/redetect` (reads DB) | `POST /api/detect-names` with `{ content }`, returns names (pure compute, no storage)                                            |
| `GET /api/health`, `/api/models`    | unchanged                                       | unchanged                                                                                                                        |

Routes that are pure storage CRUD (`GET/POST/DELETE /projects`, `/references`, `/glossary`,
`/translations`, `/translations/{tid}/matches`, etc.) are **removed from the backend** — they
move to `IndexedDbStorage`. Occurrence matching (`term_match`) and pronoun/source-term passes
are pure functions; the ones that are deterministic (no model) move to the frontend as plain
TS, or stay as stateless compute endpoints that take content in the body — decided per pass
during implementation.

Auto-save moves to the client: the translate SSE still streams tokens, and on the `done` event
the frontend writes the Translation to IndexedDB itself (it already has the raw input and the
streamed output).

This is a real contract break, so it is sequenced LAST, after the interface + IndexedDB land
behind `ApiStorageService` and we've confirmed parity.

## 6. Local-model access from a hosted web app (the private-IP problem)

### The constraint

A hosted page (served over HTTPS from a public origin) **cannot fetch a user's private-range
Ollama** (`http://192.168.x.x:11434`, `10.x`, etc.):

- **Mixed content**: an HTTPS page cannot make plain-HTTP requests; the browser blocks them.
- **Private Network Access**: browsers increasingly block/guard requests from a public site to
  private-IP and localhost targets.
- **CORS**: Ollama must send permissive CORS headers for a browser cross-origin call anyway.

Net: from a hosted origin, the only reliably reachable local target is the user's **own
`localhost`** (and even that is subject to the HTTPS/PNA rules below). We cannot reach their LAN
IP. So the supported path is: the user exposes Ollama on their `localhost` and the app talks to
`localhost`.

> Architecture note: today the BROWSER never talks to Ollama directly — the FastAPI backend
> does (`OllamaEngine` → `OLLAMA_BASE_URL`). In a hosted deploy the backend runs on the server,
> so "the backend reaches the user's Ollama" is impossible for a private IP. Reaching the
> user's local model therefore means the request originates from the USER'S machine. Two shapes
> below; this needs a decision.

### Options (needs your decision)

- **A. Direct browser → `http://localhost:11434`.** The frontend calls Ollama directly for the
  local-model case (and uses the hosted backend only for cloud providers). Requires the user to
  set `OLLAMA_ORIGINS` so Ollama returns CORS headers for the app's origin, and still runs into
  the HTTPS→HTTP mixed-content rule (localhost is treated as a secure context by modern
  browsers, which is what makes this viable at all). Keeps local-model data fully on the user's
  machine. Biggest engine-layer change (a browser Ollama client).
- **B. User runs the backend locally.** The user runs NovelBridge's FastAPI themselves
  (`localhost:8000`), pointed at their Ollama; the hosted site is only for the cloud-key path.
  This is really "self-host for local models." Least code, most user setup.
- **C. Tunnel.** The user exposes local Ollama via a tunnel to a public HTTPS URL (ngrok,
  Cloudflare Tunnel) and pastes that URL as the base URL. Works with today's server-side
  `OllamaEngine` and the planned per-request base-url field. Easiest to support in code; puts
  the burden (and the exposure) on the user.

My lean: support **C now** (it needs only a per-request Ollama base-URL field, which pairs with
the Ollama-config-in-UI task you asked for) and document **B** for privacy purists. Treat **A**
as a later enhancement because a browser-side Ollama engine is a separate build. Flagging for
your call — this decides how much engine work the local-model story needs.

### Ollama-config-in-UI (the task you asked for)

Surface `base_url`, `model`, `num_ctx`, `num_thread`, `think` as editable fields in the picker,
persisted in the browser (non-sensitive → localStorage) and sent per request. This requires a
per-request Ollama-options field on the translate contract — which we are changing anyway in
section 5, so it lands there to avoid breaking the contract twice.

### Security warning to show users (pros/cons)

Any "expose your local Ollama" guide MUST surface these, because the user is widening their
attack surface:

- **Ollama has no authentication.** Anything that can reach the port can run/pull models and
  send prompts on the user's hardware (compute theft, resource exhaustion).
- **`OLLAMA_ORIGINS=*` or a public tunnel exposes that unauthenticated port** beyond the user's
  machine. A tunnel URL is effectively public; a leaked/guessed URL = open access.
- **Bind to `127.0.0.1`, never `0.0.0.0`,** unless the user truly intends LAN exposure. Scope
  `OLLAMA_ORIGINS` to the exact app origin, not `*`.
- **Prefer an authenticated tunnel** (Cloudflare Tunnel with access control) over a raw public
  one; stop the tunnel when not in use.
- **Pros:** free, private (data stays local in options A/B), no per-token cost, any local model.
- **Cons:** real setup, an exposed unauthenticated service while active, and tunnel latency.

The guide should frame this as an informed trade-off ("here's what you open and how to close
it"), not a one-click action.

## 7. Migration order (incremental, each step shippable)

1. **Frontend `StorageService` interface + `ApiStorageService`.** Route all component data
   access through it. No behavior change. (Safety net established.)
2. **`IndexedDbStorage` + a provider switch.** Implement the interface against IndexedDB.
   Add export/import. Flip the app to it behind a flag; verify parity.
3. **Export/import UI.** Backup/restore/merge; "share a glossary" falls out of merge.
4. **Thin the backend.** Change the AI endpoints to take content in the body; remove the
   storage CRUD routes; move deterministic passes + auto-save to the client. (The contract
   break — last, once the browser is authoritative.)
5. **Local-model access.** Implement the chosen option from section 6 + the Ollama-config UI +
   the user guide with the security warnings.

Each step is a separate commit/PR and leaves the app working.

## 8. Decisions (CONFIRMED by the author)

1. **IndexedDB via Dexie.js.** Use Dexie as the IndexedDB wrapper for clean, typed queries
   (`db.projects.where(...)`, `.toArray()`, bulk put for import). JSON export/import as in
   section 4. No SQLite-WASM.
2. **Local-model access — no tunnel, no desktop app.** Two documented setups:
   - **Simple:** the user configures their local Ollama to accept the app's browser origin
     (`OLLAMA_ORIGINS=<app origin>`, `OLLAMA_HOST=127.0.0.1`) and the app calls
     `http://localhost:11434` directly from the browser for the local-model case. Cloud
     providers keep using the hosted backend.
     NOTE/constraint to verify in implementation: a hosted HTTPS origin calling plain-HTTP
     `localhost` is subject to mixed-content + Private Network Access rules; localhost is a
     secure context, which is what makes this path viable, but the exact behavior must be
     tested per browser. If a hosted HTTPS page cannot reach http://localhost, the fallback is
     to serve the app itself locally for the local-model path.
   - **Advanced:** a LAN machine runs Ollama bound to its LAN IP; the webapp (served from a
     local/HTTP context, not the public HTTPS origin) connects to that IP. Document that this
     does NOT work from the hosted HTTPS site (private-IP + mixed-content blocks), so it's for
     users running the app locally on their network.
   - Explicitly OUT: tunnels (ngrok/Cloudflare) and any downloaded/desktop app.
3. **Import modes = replace | merge.** "Merge" = upsert by id; glossary additionally dedupes on
   `surface_form` (case-insensitive) using the existing upsert rule, so importing/sharing a
   glossary combines cleanly instead of duplicating. "Replace" = wipe then load (restore).
4. **Backend stays stateless and keeps the spaCy NER + all LLM calls.** The AI/NER compute
   endpoints remain server-side (translate, extract-style, extract-glossary, name detection via
   spaCy); they take content in the request body and persist nothing. All CRUD + history move
   to the browser (Dexie). Deterministic stdlib-only passes may move client-side case by case,
   but spaCy-dependent detection stays a backend endpoint.

## 9. Local-model access (Ollama) — setup + security (resolved per decision 2)

### Simple setup (browser → localhost)

The user runs Ollama on their own machine and allows the app origin:

```
# Windows (PowerShell), per session:
$env:OLLAMA_HOST="127.0.0.1:11434"
$env:OLLAMA_ORIGINS="<the app's exact origin, e.g. https://app.example>"
ollama serve
```

The frontend, for the local-model case, calls `http://localhost:11434` directly (a browser
Ollama client — a later task). Data for local translation never leaves the user's machine.

### Advanced setup (LAN server)

Another machine on the LAN runs Ollama bound to its LAN address and the webapp (served locally,
not from the hosted HTTPS origin) points at it. Does not work from the public hosted site.

### Security warning users MUST see

- **Ollama has no authentication.** Anything that can reach the port can run/pull models and
  send prompts on the user's hardware.
- Scope `OLLAMA_ORIGINS` to the **exact** app origin, never `*`. Bind `OLLAMA_HOST` to
  `127.0.0.1` for the simple setup; only use a LAN IP in the advanced setup, knowingly.
- Exposing the port widens the attack surface while it's running — stop `ollama serve` when
  done.
- **Pros:** free, private, no per-token cost, any local model. **Cons:** setup effort and an
  unauthenticated service reachable by the configured origins while active.

```

```
