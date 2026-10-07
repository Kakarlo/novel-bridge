// Frontend StorageService interface — the persistence seam for the local-first migration
// (see .kiro/specs/novelbridge/design-local-first-storage.md, step 1).
//
// This mirrors the SHAPE of the backend's StorageService (backend/app/storage/base.py): it is
// the set of CRUD / persistence operations the UI performs on user-owned data (projects,
// references, glossary, translation history). Compute operations — translate (SSE), style /
// glossary extraction, name (re)detection, health, model listing — are deliberately NOT part
// of this interface: they are stateless backend calls that survive the migration and stay on
// the `api` client (design §5).
//
// Two implementations sit behind it, swappable with a one-line provider change:
//   • ApiStorageService  — wraps the current REST client (today's behavior, zero change).
//   • IndexedDbStorage   — the browser store (a later step).
// Landing the interface + routing all component data access through it is the safety net the
// migration is built on: swap the implementation later, UI untouched.

import type {
  GlossaryCreate,
  GlossaryEntry,
  GlossaryStatus,
  GlossaryUpdate,
  Project,
  ProjectCreate,
  ProjectDetail,
  ReferenceChapter,
  ReferenceCreate,
  Translation,
} from "@/api/types";

// Fields the client provides when saving a completed translation (design §5: auto-save moves
// to the client). id/created_at are assigned by the store.
export interface SaveTranslationInput {
  source_lang: Translation["source_lang"];
  raw_text: string;
  output_text: string;
  model_used: string;
}

// A portable backup/restore bundle (JSON export/import, design §4). Not produced by the API
// backend — the IndexedDB implementation fills this in a later step.
export interface ExportBundle {
  format: "novelbridge-export";
  version: number;
  exported_at: string;
  projects: Project[];
  references: ReferenceChapter[];
  glossary: GlossaryEntry[];
  translations: Translation[];
}

export interface StorageService {
  // --- projects ---
  listProjects(): Promise<Project[]>;
  createProject(input: ProjectCreate): Promise<Project>;
  getProject(id: string): Promise<ProjectDetail>;
  deleteProject(id: string): Promise<void>;
  // Persist a project's writing-style profile (null clears it). The style itself is computed
  // by the stateless POST /extract-style compute endpoint (which no longer persists — task
  // 23.4c); the CALLER saves the result here. Returns the updated project.
  updateProjectStyle(id: string, styleProfile: string | null): Promise<Project>;

  // --- references ---
  listReferences(projectId: string): Promise<ReferenceChapter[]>;
  addReference(projectId: string, input: ReferenceCreate): Promise<ReferenceChapter>;
  deleteReference(refId: string): Promise<void>;
  // Persist refreshed proper-noun detections for a reference (names come from the stateless
  // POST /detect-names compute endpoint — task 23.4c). Returns the updated reference.
  setReferenceDetectedNames(refId: string, names: string[]): Promise<ReferenceChapter>;
  // Remove a resolved suggestion (after promote/reject) from a reference's detected pool so it
  // leaves the chips and won't be resurfaced.
  resolveReferenceTerm(refId: string, term: string): Promise<ReferenceChapter>;

  // --- glossary ---
  listGlossary(projectId: string): Promise<GlossaryEntry[]>;
  createGlossary(projectId: string, input: GlossaryCreate): Promise<GlossaryEntry>;
  updateGlossary(entryId: string, patch: GlossaryUpdate): Promise<GlossaryEntry>;
  setGlossaryStatus(entryId: string, status: GlossaryStatus): Promise<GlossaryEntry>;
  deleteGlossary(entryId: string): Promise<void>;

  // --- translations ---
  // Persist a completed translation client-side (used by the IndexedDB backend; the API
  // backend auto-saves server-side on the translate stream and ignores this).
  saveTranslation(projectId: string, input: SaveTranslationInput): Promise<Translation>;
  listTranslations(projectId: string): Promise<Translation[]>;
  getTranslation(tid: string): Promise<Translation>;
  deleteTranslation(tid: string): Promise<void>;

  // --- portability (JSON backup / restore / merge) ---
  exportAll(): Promise<ExportBundle>;
  importAll(bundle: ExportBundle, mode: "merge" | "replace"): Promise<void>;
}
