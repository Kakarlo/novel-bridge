import { useCallback, useEffect, useState } from "react";

import { api } from "@/api/client";
import type { ModelProvider } from "@/api/types";

// The one provider that exists today. Kept as a constant so adding cloud providers later is a
// data change (push more entries) rather than a control-flow rewrite — see FRONTEND_TODO #5a.
const LOCAL_PROVIDER_ID = "ollama";
const LOCAL_PROVIDER_LABEL = "Local (Ollama)";

export interface ModelsState {
  loading: boolean;
  // Provider-aware list the picker renders. One synthetic local provider today.
  providers: ModelProvider[];
  // The configured default model (ModelsResponse.current).
  current: string;
}

/**
 * Fetch GET /api/models once and adapt the flat `{models, current}` contract into the
 * provider-shaped view model the picker consumes. A failed/unreachable fetch yields a single
 * local provider with an empty model list (reachable=false), which the picker shows as a
 * disabled "unavailable" state — it never throws.
 */
export function useModels(): ModelsState {
  const [state, setState] = useState<ModelsState>({ loading: true, providers: [], current: "" });

  const load = useCallback(async () => {
    try {
      const res = await api.listModels();
      setState({
        loading: false,
        current: res.current,
        providers: [
          {
            id: LOCAL_PROVIDER_ID,
            label: LOCAL_PROVIDER_LABEL,
            models: res.models,
            reachable: res.models.length > 0,
            needs_key: false, // local engine never needs a key
          },
        ],
      });
    } catch {
      // Backend/engine unreachable — render the provider as present-but-empty so the picker
      // can show an honest "unavailable" state rather than vanishing.
      setState({
        loading: false,
        current: "",
        providers: [
          { id: LOCAL_PROVIDER_ID, label: LOCAL_PROVIDER_LABEL, models: [], reachable: false, needs_key: false },
        ],
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return state;
}
