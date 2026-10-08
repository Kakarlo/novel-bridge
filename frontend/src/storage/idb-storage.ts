// IndexedDbStorage — the browser-local StorageService implementation (Dexie).
//
// Mirrors the backend SQLiteStorage behavior (backend/app/storage/sqlite_store.py) so the UI
// behaves identically whether data lives on the server or in the browser (design §4/§7 step 2):
//   • ids are uuid-ish hex, created_at is UTC ISO 8601
//   • references list oldest-first; glossary lists case-insensitive by surface_form
//   • add-term upserts/merges on surface_form (case-insensitive)
//   • resolveReferenceTerm drops a term (case-insensitive) from both detected_names and
//     candidate_terms
//   • project counts come from the three child stores
//
// Name detection is wired to the stateless backend compute endpoint (task 23.4c): addReference
// calls POST /api/detect-names to populate detected_names at upload (spaCy stays server-side,
// design §8.4), and setReferenceDetectedNames persists a refreshed list on Redetect. Detection
// degrades gracefully — if the compute endpoint is unreachable the reference still saves with
// detected_names=[]. chapter_number is now parsed client-side by parseChapterNumber() below.

import Dexie, { type Table } from "dexie";

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
  TermMatch,
  Translation,
} from "@/api/types";
import { findOccurrences } from "@/lib/term-match";
import type { ExportBundle, SaveTranslationInput, StorageService } from "./types";

function newId(): string {
  // uuid hex (no dashes), matching the backend's new_id() shape.
  const uuid =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
  return uuid.replace(/-/g, "");
}

const nowIso = () => new Date().toISOString();

/**
 * Port of backend/app/services/chapter_number.py — deterministic, pure string logic.
 * Handles "Chapter N", "Ch. N", "Ch N", decimal interludes (integer part), and bare
 * leading numbers. Returns null for volume titles and indeterminate cases.
 */
function parseChapterNumber(title: string): number | null {
  if (!title.trim()) return null;
  if (/\bvol(?:ume|\.?)?\s*\d+/i.test(title)) return null; // volume prefix → can't be a single int
  const kwMatch = title.match(/\bch(?:apter|\.?)\s*[-:.]?\s*(\d+)/i);
  if (kwMatch) return parseInt(kwMatch[1], 10);
  const leadMatch = title.match(/^\s*(\d+)\b/);
  return leadMatch ? parseInt(leadMatch[1], 10) : null;
}

class NbDexie extends Dexie {
  projects!: Table<Project, string>;
  references!: Table<ReferenceChapter, string>;
  glossary!: Table<GlossaryEntry, string>;
  translations!: Table<Translation, string>;

  constructor() {
    super("novelbridge");
    this.version(1).stores({
      // Primary key first, then secondary indexes used by list queries.
      projects: "id, created_at",
      references: "id, project_id, created_at",
      glossary: "id, project_id, surface_form",
      translations: "id, project_id, created_at",
    });
  }
}

export class IndexedDbStorage implements StorageService {
  private db = new NbDexie();

  // --- projects ---
  async listProjects(): Promise<Project[]> {
    const all = await this.db.projects.toArray();
    return all.sort((a, b) => b.created_at.localeCompare(a.created_at));
  }

  async createProject(input: ProjectCreate): Promise<Project> {
    const existing = (await this.db.projects.toArray()).find(
      (p) => p.name.trim().toLowerCase() === input.name.trim().toLowerCase()
    );
    if (existing) {
      throw new Error(`Series "${input.name}" already exists`);
    }
    const project: Project = {
      id: newId(),
      name: input.name,
      source_lang: input.source_lang ?? null,
      created_at: nowIso(),
      style_profile: null,
    };
    await this.db.projects.add(project);
    return project;
  }

  async updateProject(id: string, input: ProjectCreate): Promise<Project> {
    const duplicate = (await this.db.projects.toArray()).find(
      (p) => p.id !== id && p.name.trim().toLowerCase() === input.name.trim().toLowerCase()
    );
    if (duplicate) {
      throw new Error(`Series "${input.name}" already exists`);
    }
    const project = await this.db.projects.get(id);
    if (!project) {
      throw new Error("Project not found");
    }

    const updated: Project = {
      ...project,
      name: input.name,
      source_lang: input.source_lang ?? null,
    };
    await this.db.projects.put(updated);
    return updated;
  }

  async getProject(id: string): Promise<ProjectDetail> {
    const project = await this.db.projects.get(id);
    if (!project) throw new Error("Project not found");
    const [references, glossary, translations] = await Promise.all([
      this.db.references.where("project_id").equals(id).count(),
      this.db.glossary.where("project_id").equals(id).count(),
      this.db.translations.where("project_id").equals(id).count(),
    ]);
    return { project, counts: { references, glossary, translations } };
  }

  async deleteProject(id: string): Promise<void> {
    await this.db.transaction(
      "rw",
      this.db.projects,
      this.db.references,
      this.db.glossary,
      this.db.translations,
      async () => {
        await this.db.projects.delete(id);
        await this.db.references.where("project_id").equals(id).delete();
        await this.db.glossary.where("project_id").equals(id).delete();
        await this.db.translations.where("project_id").equals(id).delete();
      }
    );
  }

  async updateProjectStyle(id: string, styleProfile: string | null): Promise<Project> {
    const project = await this.db.projects.get(id);
    if (!project) throw new Error("Project not found");
    const updated: Project = { ...project, style_profile: styleProfile };
    await this.db.projects.put(updated);
    return updated;
  }

  // --- references ---
  async listReferences(projectId: string): Promise<ReferenceChapter[]> {
    const all = await this.db.references.where("project_id").equals(projectId).toArray();
    return all.sort((a, b) => a.created_at.localeCompare(b.created_at)); // oldest first
  }

  async addReference(projectId: string, input: ReferenceCreate): Promise<ReferenceChapter> {
    // Populate detected_names at upload via the stateless compute endpoint (task 23.4c), so
    // the "Detected names" chips work on the browser store just like the API backend. spaCy
    // stays server-side (design §8.4). Detection is best-effort: if the endpoint is
    // unreachable the reference still saves with detected_names=[] (and Redetect can retry).
    let detectedNames: string[] = [];
    try {
      detectedNames = (await api.detectNames(input.content)).detected_names;
    } catch {
      /* detection unavailable — save the reference anyway, names can be redetected later */
    }
    const ref: ReferenceChapter = {
      id: newId(),
      project_id: projectId,
      title: input.title,
      content: input.content,
      created_at: nowIso(),
      chapter_number: parseChapterNumber(input.title),
      summary: null,
      candidate_terms: [],
      detected_names: detectedNames,
    };
    await this.db.references.add(ref);
    return ref;
  }

  async deleteReference(refId: string): Promise<void> {
    await this.db.references.delete(refId);
  }

  async setReferenceDetectedNames(refId: string, names: string[]): Promise<ReferenceChapter> {
    const ref = await this.db.references.get(refId);
    if (!ref) throw new Error("Reference not found");
    const updated: ReferenceChapter = { ...ref, detected_names: names };
    await this.db.references.put(updated);
    return updated;
  }

  async resolveReferenceTerm(refId: string, term: string): Promise<ReferenceChapter> {
    const ref = await this.db.references.get(refId);
    if (!ref) throw new Error("Reference not found");
    const low = term.toLowerCase();
    const updated: ReferenceChapter = {
      ...ref,
      detected_names: ref.detected_names.filter((t) => t.toLowerCase() !== low),
      candidate_terms: ref.candidate_terms.filter((t) => t.toLowerCase() !== low),
    };
    await this.db.references.put(updated);
    return updated;
  }

  // --- glossary ---
  async listGlossary(projectId: string): Promise<GlossaryEntry[]> {
    const all = await this.db.glossary.where("project_id").equals(projectId).toArray();
    return all.sort((a, b) => a.surface_form.localeCompare(b.surface_form, undefined, { sensitivity: "base" }));
  }

  async createGlossary(projectId: string, input: GlossaryCreate): Promise<GlossaryEntry> {
    // Upsert/merge on surface_form (case-insensitive), matching the backend add_term.
    const low = input.surface_form.toLowerCase();
    const existing = (await this.db.glossary.where("project_id").equals(projectId).toArray()).find(
      (e) => e.surface_form.toLowerCase() === low
    );
    if (existing) {
      const merged: GlossaryEntry = {
        ...existing,
        surface_form: input.surface_form,
        source_term:
          input.source_term !== undefined && input.source_term !== null ? input.source_term : existing.source_term,
        status: input.status ?? existing.status,
        category: input.category ?? existing.category,
        gender: input.gender !== undefined && input.gender !== null ? input.gender : existing.gender,
        note: input.note !== undefined && input.note !== null ? input.note : existing.note,
      };
      await this.db.glossary.put(merged);
      return merged;
    }
    const entry: GlossaryEntry = {
      id: newId(),
      project_id: projectId,
      surface_form: input.surface_form,
      source_term: input.source_term ?? null,
      status: input.status ?? "candidate",
      category: input.category ?? "term",
      gender: input.gender ?? null,
      note: input.note ?? null,
      created_at: nowIso(),
    };
    await this.db.glossary.add(entry);
    return entry;
  }

  async updateGlossary(entryId: string, patch: GlossaryUpdate): Promise<GlossaryEntry> {
    const entry = await this.db.glossary.get(entryId);
    if (!entry) throw new Error("Glossary entry not found");
    const merged: GlossaryEntry = {
      ...entry,
      surface_form: patch.surface_form ?? entry.surface_form,
      source_term: patch.source_term !== undefined ? patch.source_term : entry.source_term,
      status: patch.status ?? entry.status,
      category: patch.category ?? entry.category,
      gender: patch.gender !== undefined ? patch.gender : entry.gender,
      note: patch.note !== undefined ? patch.note : entry.note,
    };
    await this.db.glossary.put(merged);
    return merged;
  }

  async setGlossaryStatus(entryId: string, status: GlossaryStatus): Promise<GlossaryEntry> {
    const entry = await this.db.glossary.get(entryId);
    if (!entry) throw new Error("Glossary entry not found");
    const updated = { ...entry, status };
    await this.db.glossary.put(updated);
    return updated;
  }

  async deleteGlossary(entryId: string): Promise<void> {
    await this.db.glossary.delete(entryId);
  }

  // --- translations ---
  async saveTranslation(projectId: string, input: SaveTranslationInput): Promise<Translation> {
    const tr: Translation = {
      id: newId(),
      project_id: projectId,
      source_lang: input.source_lang,
      raw_text: input.raw_text,
      output_text: input.output_text,
      model_used: input.model_used,
      created_at: nowIso(),
    };
    await this.db.translations.add(tr);
    return tr;
  }

  async listTranslations(projectId: string): Promise<Translation[]> {
    const all = await this.db.translations.where("project_id").equals(projectId).toArray();
    return all.sort((a, b) => b.created_at.localeCompare(a.created_at)); // newest first
  }

  async getTranslation(tid: string): Promise<Translation> {
    const t = await this.db.translations.get(tid);
    if (!t) throw new Error("Translation not found");
    return t;
  }

  async deleteTranslation(tid: string): Promise<void> {
    await this.db.translations.delete(tid);
  }

  // Compute term-occurrence matches locally (task 23.4d): no server row exists on this
  // backend, so port the backend's on-demand recompute — load the saved translation and the
  // project's CURRENT glossary, then run the stdlib matcher (findOccurrences). Detection only.
  async getTranslationMatches(tid: string): Promise<TermMatch[]> {
    const translation = await this.db.translations.get(tid);
    if (!translation) throw new Error("Translation not found");
    const glossary = await this.listGlossary(translation.project_id);
    return findOccurrences(translation.output_text, glossary);
  }

  // --- portability (JSON backup / restore / merge) ---
  async exportAll(): Promise<ExportBundle> {
    const [projects, references, glossary, translations] = await Promise.all([
      this.db.projects.toArray(),
      this.db.references.toArray(),
      this.db.glossary.toArray(),
      this.db.translations.toArray(),
    ]);
    return {
      format: "novelbridge-export",
      version: 1,
      exported_at: nowIso(),
      projects,
      references,
      glossary,
      translations,
    };
  }

  async importAll(bundle: ExportBundle, mode: "merge" | "replace"): Promise<void> {
    if (bundle.format !== "novelbridge-export") throw new Error("Not a NovelBridge export file.");
    if (bundle.version !== 1) throw new Error(`Unsupported export version: ${bundle.version}`);
    const projects = bundle.projects ?? [];
    const references = bundle.references ?? [];
    const glossary = bundle.glossary ?? [];
    const translations = bundle.translations ?? [];

    await this.db.transaction(
      "rw",
      this.db.projects,
      this.db.references,
      this.db.glossary,
      this.db.translations,
      async () => {
        if (mode === "replace") {
          await Promise.all([
            this.db.projects.clear(),
            this.db.references.clear(),
            this.db.glossary.clear(),
            this.db.translations.clear(),
          ]);
        }
        // Upsert by id (bulkPut). Glossary dedupe-on-surface_form for merge is handled below.
        await this.db.projects.bulkPut(projects);
        await this.db.references.bulkPut(references);
        await this.db.translations.bulkPut(translations);

        if (mode === "replace") {
          await this.db.glossary.bulkPut(glossary);
        } else {
          // Merge: dedupe each incoming entry on (project_id, surface_form) case-insensitively,
          // reusing the existing row's id so a shared glossary combines instead of duplicating.
          for (const incoming of glossary) {
            const low = incoming.surface_form.toLowerCase();
            const existing = (await this.db.glossary.where("project_id").equals(incoming.project_id).toArray()).find(
              (e) => e.surface_form.toLowerCase() === low
            );
            await this.db.glossary.put(existing ? { ...incoming, id: existing.id } : incoming);
          }
        }
      }
    );
  }
}
