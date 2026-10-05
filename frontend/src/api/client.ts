// Thin typed fetch wrapper over the NovelBridge REST API.
// All calls go through the Vite dev proxy (/api -> backend :8000).

import { streamSse } from "./sse";
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
  TranslateEvent,
  TranslateRequest,
  Translation,
} from "./types";

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit & { parse?: boolean }): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: init?.body != null ? { "Content-Type": "application/json", ...(init?.headers ?? {}) } : init?.headers,
    ...init,
  });

  if (!res.ok) {
    throw new ApiError(await errorMessage(res), res.status);
  }

  // 204 No Content (deletes) and other empty bodies.
  if (res.status === 204 || init?.parse === false) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    if (Array.isArray(data?.detail)) {
      // FastAPI 422 validation error array.
      const first = data.detail[0];
      if (first?.msg) return String(first.msg);
    }
    if (data?.detail) return JSON.stringify(data.detail);
  } catch {
    /* fall through */
  }
  return `Request failed (${res.status})`;
}

export const api = {
  // --- health ---
  health: () => request<{ status: string; reachable: boolean; engine: string; model: string }>("/health"),

  // --- projects ---
  listProjects: () => request<Project[]>("/projects"),
  createProject: (body: ProjectCreate) => request<Project>("/projects", { method: "POST", body: JSON.stringify(body) }),
  getProject: (id: string) => request<ProjectDetail>(`/projects/${id}`),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: "DELETE" }),

  // --- references ---
  listReferences: (pid: string) => request<ReferenceChapter[]>(`/projects/${pid}/references`),
  addReference: (pid: string, body: ReferenceCreate) =>
    request<ReferenceChapter>(`/projects/${pid}/references`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteReference: (refId: string) => request<void>(`/references/${refId}`, { method: "DELETE" }),
  // Re-run summary + candidate-term extraction for one reference (e.g. after the
  // engine was offline at upload). Returns the updated reference.
  resummarizeReference: (refId: string) =>
    request<ReferenceChapter>(`/references/${refId}/resummarize`, { method: "POST" }),
  // Re-run ONLY the offline name detector (no AI) to refresh detected_names quickly.
  redetectReferenceNames: (refId: string) =>
    request<ReferenceChapter>(`/references/${refId}/redetect`, { method: "POST" }),
  // Remove a resolved suggestion (after promote/reject) from a reference's pools so it
  // leaves the chips and won't be resurfaced by redetect.
  resolveReferenceTerm: (refId: string, term: string) =>
    request<ReferenceChapter>(`/references/${refId}/resolve-term`, {
      method: "POST",
      body: JSON.stringify({ term }),
    }),

  // --- glossary ---
  listGlossary: (pid: string) => request<GlossaryEntry[]>(`/projects/${pid}/glossary`),
  createGlossary: (pid: string, body: GlossaryCreate) =>
    request<GlossaryEntry>(`/projects/${pid}/glossary`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateGlossary: (entryId: string, body: GlossaryUpdate) =>
    request<GlossaryEntry>(`/glossary/${entryId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  // Approve/reject a term in context (the in-context review loop, task 14).
  setGlossaryStatus: (entryId: string, status: GlossaryStatus) =>
    request<GlossaryEntry>(`/glossary/${entryId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  deleteGlossary: (entryId: string) => request<void>(`/glossary/${entryId}`, { method: "DELETE" }),

  // --- translations ---
  listTranslations: (pid: string) => request<Translation[]>(`/projects/${pid}/translations`),
  getTranslation: (tid: string) => request<Translation>(`/translations/${tid}`),
  // Backed by DELETE /api/translations/{tid} (204/404) — endpoint is live.
  deleteTranslation: (tid: string) => request<void>(`/translations/${tid}`, { method: "DELETE" }),
  // Retrospective term matches for a saved translation (task 14).
  getTranslationMatches: (tid: string) => request<TermMatch[]>(`/translations/${tid}/matches`),

  /**
   * Open the SSE translate stream. Returns an async iterator of parsed events;
   * the caller renders content chunks live and watches for done/error.
   */
  translateStream: (pid: string, body: TranslateRequest, signal?: AbortSignal) =>
    streamSse<TranslateEvent>({
      url: `${BASE}/projects/${pid}/translate`,
      body,
      signal,
    }),
};
