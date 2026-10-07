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
}

/**
 * Fetch GET /api/models for the CURRENTLY SELECTED provider (cred-aware) and adapt it into the
 * provider-shaped view model the picker consumes.
 *
 * The backend returns models for one provider at a time (the ?provider= query the client adds
 * from the credential store). So we render every known provider from the static catalog and
 * fill the selected provider's `models`/`reachable` from the response; the others stay listed
 * but empty (the picker shows "add a key" / "select to load"). Refetches whenever the chosen
 * provider or the API key changes, so entering a key immediately lists that provider's models.
 * A failed/unreachable fetch leaves the selected provider empty (reachable=false) — it never
 * throws.
 */
export function useModels(): ModelsState {
  const { provider: selectedProvider, apiKey } = useCredentials();
  const activeId = selectedProvider || DEFAULT_PROVIDER_ID;

  const [state, setState] = useState<ModelsState>({
    loading: true,
    providers: emptyCatalog(activeId),
    current: "",
  });

  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const res = await api.listModels();
      setState({
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
      });
    } catch {
      // Backend/engine unreachable or key rejected — render the selected provider as
      // present-but-empty so the picker shows an honest "unavailable" state (never vanishes).
      setState({
        loading: false,
        current: "",
        providers: PROVIDERS.map((p) =>
          p.id === activeId
            ? { id: p.id, label: p.label, models: [], reachable: false, needs_key: p.needsKey }
            : unloadedProvider(p.id)
        ),
      });
    }
  }, [activeId]);

  // Refetch when the selected provider or the API key changes (apiKey in the dep list so
  // entering/clearing a key re-lists the provider's models).
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, apiKey]);

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
