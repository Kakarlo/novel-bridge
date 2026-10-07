// ApiStorageService — the StorageService implementation that wraps the current REST client.
//
// This is a pure pass-through to `api` (src/api/client.ts): it introduces the persistence
// interface with ZERO behavior change, so the UI can be routed through the interface first and
// the IndexedDB implementation swapped in later (design-local-first-storage.md, step 1 → 2).

import { api } from "@/api/client";
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
import type { ExportBundle, StorageService } from "./types";

export class ApiStorageService implements StorageService {
  // --- projects ---
  listProjects(): Promise<Project[]> {
    return api.listProjects();
  }
  createProject(input: ProjectCreate): Promise<Project> {
    return api.createProject(input);
  }
  getProject(id: string): Promise<ProjectDetail> {
    return api.getProject(id);
  }
  deleteProject(id: string): Promise<void> {
    return api.deleteProject(id);
  }
  updateProjectStyle(id: string, styleProfile: string | null): Promise<Project> {
    // The server owns the project row on this backend, so persist through the REST surface:
    // a null clears the style, a string sets it. (The style value itself was computed by the
    // stateless /extract-style endpoint, which no longer persists — task 23.4c.)
    return styleProfile === null ? api.clearProjectStyle(id) : api.setProjectStyle(id, styleProfile);
  }

  // --- references ---
  listReferences(projectId: string): Promise<ReferenceChapter[]> {
    return api.listReferences(projectId);
  }
  addReference(projectId: string, input: ReferenceCreate): Promise<ReferenceChapter> {
    return api.addReference(projectId, input);
  }
  deleteReference(refId: string): Promise<void> {
    return api.deleteReference(refId);
  }
  // The API backend recomputes + persists detected names server-side via redetect, so there's
  // no endpoint to set an arbitrary client-supplied list. The references tab calls
  // api.redetectReferenceNames directly on this backend, never this method.
  setReferenceDetectedNames(): Promise<ReferenceChapter> {
    return Promise.reject(new Error("The API backend sets detected names server-side via redetect, not from a list."));
  }
  resolveReferenceTerm(refId: string, term: string): Promise<ReferenceChapter> {
    return api.resolveReferenceTerm(refId, term);
  }

  // --- glossary ---
  listGlossary(projectId: string): Promise<GlossaryEntry[]> {
    return api.listGlossary(projectId);
  }
  createGlossary(projectId: string, input: GlossaryCreate): Promise<GlossaryEntry> {
    return api.createGlossary(projectId, input);
  }
  updateGlossary(entryId: string, patch: GlossaryUpdate): Promise<GlossaryEntry> {
    return api.updateGlossary(entryId, patch);
  }
  setGlossaryStatus(entryId: string, status: GlossaryStatus): Promise<GlossaryEntry> {
    return api.setGlossaryStatus(entryId, status);
  }
  deleteGlossary(entryId: string): Promise<void> {
    return api.deleteGlossary(entryId);
  }

  // --- translations ---
  // The API backend auto-saves on the translate SSE stream, so the client never saves
  // explicitly here. Present to satisfy the interface; the translate tab only calls
  // saveTranslation on the IndexedDB backend.
  saveTranslation(): Promise<Translation> {
    return Promise.reject(new Error("The API backend auto-saves translations server-side."));
  }
  listTranslations(projectId: string): Promise<Translation[]> {
    return api.listTranslations(projectId);
  }
  getTranslation(tid: string): Promise<Translation> {
    return api.getTranslation(tid);
  }
  deleteTranslation(tid: string): Promise<void> {
    return api.deleteTranslation(tid);
  }

  // --- portability ---
  // JSON export/import belongs to the browser store (design §4). The server-backed
  // implementation can't materialize a cross-table bundle through the current REST surface, so
  // these are unsupported here; the IndexedDB implementation provides them in a later step.
  exportAll(): Promise<ExportBundle> {
    return Promise.reject(new Error("Export is only available with local (browser) storage."));
  }
  importAll(): Promise<void> {
    return Promise.reject(new Error("Import is only available with local (browser) storage."));
  }
}
