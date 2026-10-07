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
 * Storage choice (per the project's local-first, no-cloud-personal-data stance): keys are
 * held in **memory only** — a module variable, never written to localStorage or
 * sessionStorage. They live for the lifetime of the page (gone on refresh/close) and are sent
 * only on the X-LLM-Api-Key header to the backend proxy. Keeping them out of any persistent
 * store means they aren't sitting in a devtools-inspectable location and can't be read back by
 * a later script via storage. The provider/model choice IS persisted in localStorage (not
 * sensitive) so the picker remembers the selection across sessions.
 *
 * Keys are remembered PER PROVIDER for the life of the tab: switching provider swaps in that
 * provider's remembered key (or empty), so moving away and back doesn't lose a key — but a
 * key is never carried across providers (it belongs to exactly one). Still memory-only.
 *
 * Note: memory-only is a deliberate, low-cost hardening — not full XSS protection. A script
 * running in the page can still observe the key in flight. Stronger isolation (httpOnly
 * server-side session, or a worker-held key) is a larger change tracked separately.
 *
 * Follows the same module-level `useSyncExternalStore` pattern as use-active-stream.ts so any
 * component (picker, translate tab, health/models hooks) stays in sync without prop drilling.
 */

export interface Credentials {
  /** Provider id (e.g. "ollama", "openrouter", "gemini"). Empty = use the server default. */
  provider: string;
  /** Model id within the provider. Empty = use that provider's default. */
  model: string;
  /** The ACTIVE provider's API key. Empty for local providers. Session-only. */
  apiKey: string;
  /** True if ANY provider has a key set this session (not just the active one). Drives the
   *  "you'll lose your key on refresh" guard, which must fire regardless of active provider. */
  anyKeySet: boolean;
  /** Custom Ollama base URL (task 23.5). Overrides the server's OLLAMA_BASE_URL so a hosted-
   *  app user can point to their own local Ollama. Persisted in localStorage (not sensitive).
   *  Empty = use the server's configured address. */
  ollamaUrl: string;
}

const SELECTION_KEY = "nb:llm-selection"; // {provider, model, ollamaUrl} — localStorage (persisted)
// The API key is intentionally NOT persisted anywhere: it lives only in `state` below (memory)
// for the life of the page.

function readInitial(): Credentials {
  let provider = "";
  let model = "";
  let ollamaUrl = "";
  try {
    const raw = localStorage.getItem(SELECTION_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<Credentials>;
      provider = typeof parsed.provider === "string" ? parsed.provider : "";
      model = typeof parsed.model === "string" ? parsed.model : "";
      ollamaUrl = typeof parsed.ollamaUrl === "string" ? parsed.ollamaUrl : "";
    }
  } catch {
    /* ignore corrupt/unavailable storage */
  }
  // apiKey always starts empty — a refresh clears it (memory-only), by design.
  return { provider, model, apiKey: "", anyKeySet: false, ollamaUrl };
}

let state: Credentials = readInitial();
// Per-provider API keys, memory-only. `state.apiKey` always mirrors the ACTIVE provider's key
// here, so downstream readers (client.ts, picker) keep using the flat `apiKey` field.
const keysByProvider: Record<string, string> = {};
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

function persist(next: Credentials) {
  // Only the non-sensitive provider/model/ollamaUrl choice is persisted. The API key is memory-only.
  try {
    localStorage.setItem(
      SELECTION_KEY,
      JSON.stringify({ provider: next.provider, model: next.model, ollamaUrl: next.ollamaUrl })
    );
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

  // Switching provider: swap in that provider's remembered key (not the previous provider's).
  // A caller that passes BOTH provider and apiKey (unusual) still wins for apiKey below.
  const switchingProvider = patch.provider !== undefined && patch.provider !== state.provider;
  if (switchingProvider && patch.apiKey === undefined) {
    next.apiKey = keysByProvider[next.provider] ?? "";
  }

  // A key change is stored under the ACTIVE provider so it's restored on return.
  if (patch.apiKey !== undefined) {
    if (next.apiKey) keysByProvider[next.provider] = next.apiKey;
    else delete keysByProvider[next.provider];
  }

  next.anyKeySet = Object.values(keysByProvider).some((k) => k.trim().length > 0);

  if (
    next.provider === state.provider &&
    next.model === state.model &&
    next.apiKey === state.apiKey &&
    next.anyKeySet === state.anyKeySet &&
    next.ollamaUrl === state.ollamaUrl
  ) {
    return;
  }
  state = next;
  persist(next);
  emit();
}

/** Clear the active provider's API key (a "forget key" action). Keeps provider/model. */
export function clearApiKey() {
  delete keysByProvider[state.provider];
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
