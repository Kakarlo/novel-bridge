// Types mirror the backend Pydantic models (see backend/app/models.py).
// Keep these in sync with the API contract in .kiro/steering/tech.md.

export type SourceLang = "zh" | "ja";

export interface Project {
  id: string;
  name: string;
  source_lang: SourceLang | null;
  created_at: string;
}

export interface ProjectCounts {
  references: number;
  glossary: number;
  translations: number;
}

export interface ProjectDetail {
  project: Project;
  counts: ProjectCounts;
}

export interface ReferenceChapter {
  id: string;
  project_id: string;
  title: string;
  content: string;
  created_at: string;
  // Parsed from the title at upload (backend services/chapter_number.py). null when the
  // title has no recognizable number — the list falls back to upload order for those.
  chapter_number: number | null;
  // Derived at upload time by the engine (summary + candidate glossary terms).
  // Both may be absent if extraction hasn't run yet (e.g. engine was offline).
  summary: string | null;
  candidate_terms: string[];
  // Rule-based proper-noun detections (field-fix #2), surfaced separately from the AI's
  // candidate_terms so the user can judge rules-vs-AI picks.
  detected_names: string[];
}

export type GlossaryStatus = "candidate" | "approved" | "rejected";
export type GlossaryCategory = "character" | "title" | "term";
export type Gender = "male" | "female" | "unknown";

// English-first glossary entry (task 14). `surface_form` is the English name (always
// present); `source_term` is the optional original-language term.
export interface GlossaryEntry {
  id: string;
  project_id: string;
  surface_form: string;
  source_term: string | null;
  status: GlossaryStatus;
  category: GlossaryCategory;
  gender: Gender | null;
  note: string | null;
  created_at: string | null;
}

export interface Translation {
  id: string;
  project_id: string;
  source_lang: SourceLang;
  raw_text: string;
  output_text: string;
  model_used: string;
  created_at: string;
}

// --- Request payloads ---

export interface ProjectCreate {
  name: string;
  source_lang?: SourceLang | null;
}

export interface ReferenceCreate {
  title: string;
  content: string;
  // When false, skip the slow AI summary/candidate-term extraction and run only the
  // offline name detector. Defaults true on the backend.
  extract_summary?: boolean;
}

export interface GlossaryCreate {
  surface_form: string;
  source_term?: string | null;
  status?: GlossaryStatus | null;
  category?: GlossaryCategory;
  gender?: Gender | null;
  note?: string | null;
}

export interface GlossaryUpdate {
  surface_form?: string | null;
  source_term?: string | null;
  status?: GlossaryStatus | null;
  category?: GlossaryCategory | null;
  gender?: Gender | null;
  note?: string | null;
}

export interface GlossaryStatusUpdate {
  status: GlossaryStatus;
}

// One glossary term's occurrences in a translation's output (task 14). Produced by the
// backend's occurrence detector for the in-context review loop. Detection only.
export interface TermMatch {
  term_id: string;
  surface_form: string;
  status: GlossaryStatus;
  category: GlossaryCategory;
  count: number;
  snippets: string[];
}

// EXPERIMENTAL source↔English pairing proposal for a saved translation (FRONTEND_TODO #3,
// gated by NB_SOURCE_TERMS on the backend). Deterministic — correlates appearance order +
// frequency in the source chapter vs the English output, NOT string similarity. These are
// guesses; present them as suggestions, not facts.
export interface AlignmentCandidate {
  source_term: string;
  surface_form: string;
  source_count: number;
  english_count: number;
  confidence: number; // 0..1
  basis: string;
}

export interface TranslateRequest {
  raw_text: string;
  source_lang: SourceLang;
  // Opt-in in-context term review. When true, the done event carries `matches`.
  review_terms?: boolean;
  // Optional per-request engine override (provider-aware model picker). Omit entirely to use
  // the server's configured engine + default model (backward-compatible). Both fields inside
  // are optional server-side: provider omitted → configured engine, model omitted → that
  // provider's default. Today provider is fixed to the local engine; sending a mismatching
  // provider yields a 400.
  selection?: Partial<ModelSelection>;
}

// GET /api/models — the current single-provider (local Ollama) contract. `models` is empty
// when the engine is unreachable (never errors); `current` is the configured default model.
// NOTE: this is expected to grow a provider dimension (see tech.md "Bring-your-own LLM API
// token" → `{ providers: [...] }`); the picker is already modeled provider → model so that
// future shape is a data change, not a UI rewrite.
export interface ModelsResponse {
  models: string[];
  current: string;
}

// Provider-aware view model the picker renders. Today the flat ModelsResponse is adapted into
// a single synthetic "Local (Ollama)" provider; cloud providers slot in as more entries.
export interface ModelProvider {
  id: string;
  label: string;
  models: string[];
  // The engine responded with models. Distinct from `needs_key` so an empty list can mean
  // either "unreachable" or (future cloud) "no API key configured".
  reachable: boolean;
  // Future cloud providers: a key must be configured before models are usable. Always false
  // for the local engine.
  needs_key: boolean;
}

// A selected engine target. Modeled as a {provider, model} pair even though provider is fixed
// to the local engine today, so wiring the per-request override later is a data change.
export interface ModelSelection {
  provider: string;
  model: string;
}

// --- SSE event shapes (POST /api/projects/{id}/translate) ---
// The stream emits one of these per `data:` line.

export interface SseContentEvent {
  content: string;
}
export interface SseInfoEvent {
  info: string;
}
export interface SseDoneEvent {
  done: true;
  translation_id: string;
  // Present only when the request opted into term review (task 14).
  matches?: TermMatch[];
}
export interface SseErrorEvent {
  error: string;
}

export type TranslateEvent = SseContentEvent | SseInfoEvent | SseDoneEvent | SseErrorEvent;

export function isContentEvent(e: TranslateEvent): e is SseContentEvent {
  return "content" in e;
}
export function isInfoEvent(e: TranslateEvent): e is SseInfoEvent {
  return "info" in e;
}
export function isDoneEvent(e: TranslateEvent): e is SseDoneEvent {
  return "done" in e;
}
export function isErrorEvent(e: TranslateEvent): e is SseErrorEvent {
  return "error" in e;
}
