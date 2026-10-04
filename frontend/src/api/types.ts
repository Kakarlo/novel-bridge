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
}

export interface GlossaryEntry {
  id: string;
  project_id: string;
  source_term: string;
  translation: string;
  note: string | null;
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
  source_term: string;
  translation: string;
  note?: string | null;
}

export interface GlossaryUpdate {
  translation?: string | null;
  note?: string | null;
}

export interface TranslateRequest {
  raw_text: string;
  source_lang: SourceLang;
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
}
export interface SseErrorEvent {
  error: string;
}

export type TranslateEvent =
  | SseContentEvent
  | SseInfoEvent
  | SseDoneEvent
  | SseErrorEvent;

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
