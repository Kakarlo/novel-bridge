import { useCallback, useEffect, useState } from "react";

import { api } from "@/api/client";
import { DEFAULT_PROVIDER_ID, PROVIDERS } from "@/api/providers";
import type { ModelProvider } from "@/api/types";
import { useCredentials } from "@/hooks/use-credentials";

export interface ModelsState {
  loading: boolean;
  // Provider-aware list the picker renders: every known provider (from the catalog), with the
  // currently-selected provider's live models filled in.
  providers: ModelProvider[];
  // The configured/active default model for the selected provider (ModelsResponse.current).
  current: string;
  // Call this to re-probe the active provider immediately (e.g. after setting a custom URL).
  refresh: () => void;
}

/**
 * Fetch GET /api/models for the CURRENTLY SELECTED provider (cred-aware) and adapt it into the
 * provider-shaped view model the picker consumes.
 *
 * Refetches when provider, apiKey, OR ollamaUrl changes — so entering a custom Ollama URL
 * takes effect immediately without switching providers (task 23.5 fix).
 */
export function useModels(): ModelsState {
  const { provider: selectedProvider, apiKey, ollamaUrl } = useCredentials();
  const activeId = selectedProvider || DEFAULT_PROVIDER_ID;

  const [state, setState] = useState<ModelsState>({
    loading: true,
    providers: emptyCatalog(activeId),
    current: "",
    refresh: () => {},
  });

  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const res = await api.listModels();
      setState((s) => ({
        ...s,
        loading: false,
        current: res.current,
        providers: PROVIDERS.map((p) =>
          p.id === activeId
            ? {
                id: p.id,
                label: p.label,
                models: res.models,
                reachable: res.models.length > 0,
                needs_key: p.needsKey,
              }
            : unloadedProvider(p.id)
        ),
      }));
    } catch {
      setState((s) => ({
        ...s,
        loading: false,
        current: "",
        providers: PROVIDERS.map((p) =>
          p.id === activeId
            ? { id: p.id, label: p.label, models: [], reachable: false, needs_key: p.needsKey }
            : unloadedProvider(p.id)
        ),
      }));
    }
  }, [activeId]); // activeId is the only stable dep for memoisation; ollamaUrl/apiKey are in the effect

  // Re-expose refresh on every load change so the picker can call it.
  useEffect(() => {
    setState((s) => ({ ...s, refresh: load }));
  }, [load]);

  // Refetch when provider, API key, OR custom Ollama URL changes.
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, apiKey, ollamaUrl]);

  return state;
}

/** A known provider with no models loaded yet (not the active selection). */
function unloadedProvider(id: string): ModelProvider {
  const p = PROVIDERS.find((x) => x.id === id)!;
  return { id: p.id, label: p.label, models: [], reachable: false, needs_key: p.needsKey };
}

/** The full catalog with nothing loaded — initial render before the first fetch resolves. */
function emptyCatalog(_activeId: string): ModelProvider[] {
  return PROVIDERS.map((p) => unloadedProvider(p.id));
}
