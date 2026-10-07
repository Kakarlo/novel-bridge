// Thin typed fetch wrapper over the NovelBridge REST API.
// All calls go through the Vite dev proxy (/api -> backend :8000).

import { getCredentials } from "@/hooks/use-credentials";
import { streamSse } from "./sse";
import type {
  GlossaryPairSuggestion,
  ModelsResponse,
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

// --- bring-your-own-key credential plumbing ---------------------------------
// The API key goes ONLY in the X-LLM-Api-Key header (never a JSON body/query, so it stays
// out of logs and URLs). The provider rides as a query param on GET endpoints and inside the
// `selection` body on translate. These read the live credential store at call time so the
// latest picker choice is always used.

/** The X-LLM-Api-Key header for the current key, or {} when no key is set. */
function authHeader(): Record<string, string> {
  const { apiKey } = getCredentials();
  return apiKey ? { "X-LLM-Api-Key": apiKey } : {};
}

/** `?provider=…` suffix for the current provider, or "" when using the server default. */
function providerQuery(): string {
  const { provider } = getCredentials();
  return provider ? `?provider=${encodeURIComponent(provider)}` : "";
}

export const api = {
  // --- health ---
  // Cred-aware: sends the chosen provider (query) + API key (header) so the status indicator
  // probes the user's own provider/key, not just the server default. A 401 (missing key) or
  // 400 (unknown provider) surfaces as an ApiError the caller can treat as "unreachable".
  health: () =>
    request<{ status: string; reachable: boolean; engine: string; model?: string }>(`/health${providerQuery()}`, {
      headers: authHeader(),
    }),

  // --- models ---
  // GET /api/models → { models, current }. Cred-aware (provider query + key header) so a BYO
  // user lists their own provider's models. Degrades to an empty `models` list (never errors)
  // when the engine is unreachable; the picker treats empty as "unavailable".
  listModels: () => request<ModelsResponse>(`/models${providerQuery()}`, { headers: authHeader() }),

  // --- projects ---
  listProjects: () => request<Project[]>("/projects"),
  createProject: (body: ProjectCreate) => request<Project>("/projects", { method: "POST", body: JSON.stringify(body) }),
  getProject: (id: string) => request<ProjectDetail>(`/projects/${id}`),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: "DELETE" }),

  // --- per-project style profile (task 3) ---
  // Extract a writing-style profile (LLM call). With no body, analyzes the project's newest
  // reference chapter; pass { content } to analyze a specific pasted chapter instead.
  // Returns the updated Project (style_profile set). 502 on engine failure, 404 if no content.
  extractProjectStyle: (id: string, content?: string) =>
    request<Project>(`/projects/${id}/extract-style`, {
      method: "POST",
      body: content ? JSON.stringify({ content }) : undefined,
    }),
  // Manually set/edit the style profile (user-authored). Returns the updated Project.
  setProjectStyle: (id: string, style_profile: string) =>
    request<Project>(`/projects/${id}/style`, { method: "PUT", body: JSON.stringify({ style_profile }) }),
  // Clear the style profile. Returns the updated Project (style_profile null).
  clearProjectStyle: (id: string) => request<Project>(`/projects/${id}/style`, { method: "DELETE" }),

  // --- references ---
  listReferences: (pid: string) => request<ReferenceChapter[]>(`/projects/${pid}/references`),
  addReference: (pid: string, body: ReferenceCreate) =>
    request<ReferenceChapter>(`/projects/${pid}/references`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteReference: (refId: string) => request<void>(`/references/${refId}`, { method: "DELETE" }),
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
  // EXPERIMENTAL (gated by NB_SOURCE_TERMS): zh/ja source-language proper nouns from a saved
  // translation's SOURCE chapter, most frequent first (FRONTEND_TODO #1 — moved here from
  // references, which are English). A thrown 404 = feature off → render nothing; `[]` =
  // model unavailable → render nothing.
  translationSourceTerms: (tid: string) => request<string[]>(`/translations/${tid}/source-terms`),
  // LLM-paired glossary extraction from a saved translation. Returns paired source→English
  // suggestions for the user to confirm into the glossary. Not gated (always available);
  // replaces the old deterministic term-alignment endpoint.
  translationExtractGlossary: (tid: string) =>
    request<GlossaryPairSuggestion[]>(`/translations/${tid}/extract-glossary`, { method: "POST" }),

  /**
   * Open the SSE translate stream. Returns an async iterator of parsed events;
   * the caller renders content chunks live and watches for done/error.
   */
  translateStream: (pid: string, body: TranslateRequest, signal?: AbortSignal) =>
    streamSse<TranslateEvent>({
      url: `${BASE}/projects/${pid}/translate`,
      body,
      signal,
      // BYO-key: the API key travels in the header; the provider/model are in body.selection
      // (set by the translate tab from the credential store).
      headers: authHeader(),
    }),
};
