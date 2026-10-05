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

export interface TranslateRequest {
  raw_text: string;
  source_lang: SourceLang;
  // Opt-in in-context term review. When true, the done event carries `matches`.
  review_terms?: boolean;
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
