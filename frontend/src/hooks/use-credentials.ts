import { useSyncExternalStore } from "react";

/**
 * App-wide LLM credentials store (bring-your-own-key).
 *
 * Holds the user's chosen `{ provider, model }` and their API key. Everything the user
 * supplies to translate with their OWN hosted model lives here:
 * - provider/model ride on the translate request body (`selection`) and on the /models +
 *   /health query params so the picker and status indicator reflect the chosen provider.
 * - the API key rides ONLY on the `X-LLM-Api-Key` request header (never in a JSON body),
 *   matching the backend contract.
 *
 * Storage choice (per the project's local-first, no-cloud-personal-data stance): the key is
 * kept in **sessionStorage**, so it lives for the browser tab/session and is gone when the
 * tab closes — it is never written to disk-persisted localStorage and never sent anywhere but
 * the backend proxy. The provider/model choice is persisted in localStorage (not sensitive)
 * so the picker remembers the selection across sessions.
 *
 * Follows the same module-level `useSyncExternalStore` pattern as use-active-stream.ts so any
 * component (picker, translate tab, health/models hooks) stays in sync without prop drilling.
 */

export interface Credentials {
  /** Provider id (e.g. "ollama", "openrouter", "gemini"). Empty = use the server default. */
  provider: string;
  /** Model id within the provider. Empty = use that provider's default. */
  model: string;
  /** The user's API key for a cloud provider. Empty for local providers. Session-only. */
  apiKey: string;
}

const SELECTION_KEY = "nb:llm-selection"; // {provider, model} — localStorage (persisted)
const API_KEY_KEY = "nb:llm-api-key"; // apiKey — sessionStorage (session-only, not to disk)

function readInitial(): Credentials {
  let provider = "";
  let model = "";
  let apiKey = "";
  try {
    const raw = localStorage.getItem(SELECTION_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<Credentials>;
      provider = typeof parsed.provider === "string" ? parsed.provider : "";
      model = typeof parsed.model === "string" ? parsed.model : "";
    }
  } catch {
    /* ignore corrupt/unavailable storage */
  }
  try {
    apiKey = sessionStorage.getItem(API_KEY_KEY) ?? "";
  } catch {
    /* ignore */
  }
  return { provider, model, apiKey };
}

let state: Credentials = readInitial();
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

function persist(next: Credentials) {
  try {
    localStorage.setItem(SELECTION_KEY, JSON.stringify({ provider: next.provider, model: next.model }));
  } catch {
    /* best-effort */
  }
  try {
    if (next.apiKey) sessionStorage.setItem(API_KEY_KEY, next.apiKey);
    else sessionStorage.removeItem(API_KEY_KEY);
  } catch {
    /* best-effort */
  }
}

/** Read the current credentials synchronously (for non-React call sites). */
export function getCredentials(): Credentials {
  return state;
}

/** Merge-update the credentials and notify subscribers. */
export function setCredentials(patch: Partial<Credentials>) {
  const next: Credentials = { ...state, ...patch };
  if (next.provider === state.provider && next.model === state.model && next.apiKey === state.apiKey) {
    return;
  }
  state = next;
  persist(next);
  emit();
}

/** Clear the API key (e.g. a "forget key" action). Keeps the provider/model choice. */
export function clearApiKey() {
  setCredentials({ apiKey: "" });
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** React hook: re-renders when any credential changes. */
export function useCredentials(): Credentials {
  return useSyncExternalStore(subscribe, getCredentials, getCredentials);
}
