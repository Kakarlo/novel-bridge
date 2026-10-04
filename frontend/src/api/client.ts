// Thin typed fetch wrapper over the NovelBridge REST API.
// All calls go through the Vite dev proxy (/api -> backend :8000).

import { streamSse } from "./sse";
import type {
  GlossaryCreate,
  GlossaryEntry,
  GlossaryUpdate,
  Project,
  ProjectCreate,
  ProjectDetail,
  ReferenceChapter,
  ReferenceCreate,
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
  deleteGlossary: (entryId: string) => request<void>(`/glossary/${entryId}`, { method: "DELETE" }),

  // --- translations ---
  listTranslations: (pid: string) => request<Translation[]>(`/projects/${pid}/translations`),
  getTranslation: (tid: string) => request<Translation>(`/translations/${tid}`),
  // Backed by DELETE /api/translations/{tid} (204/404) — endpoint is live.
  deleteTranslation: (tid: string) => request<void>(`/translations/${tid}`, { method: "DELETE" }),

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
