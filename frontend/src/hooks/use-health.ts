import { useCallback, useEffect, useState } from "react";

import { api } from "@/api/client";
import { useCredentials } from "@/hooks/use-credentials";

export interface Health {
  status: string;
  /** Whether the backend could actually reach the LLM engine. */
  reachable: boolean;
  engine: string;
  // The backend no longer returns a model from /health (the model picker owns the current
  // model now). Kept optional for back-compat; ModelStatus derives the model from the picker.
  model?: string;
}

export type HealthState =
  | { kind: "loading"; data: Health | null }
  | { kind: "ok"; data: Health }
  | { kind: "unreachable"; data: Health | null };

const POLL_MS = 30_000;

/**
 * Light health poll of GET /api/health for the model-status indicator.
 * Refetches on mount, every ~30s, and when the window regains focus (so a
 * backend restart is picked up quickly without hammering the endpoint).
 * Keeps the last-known engine/model while a refetch is in flight.
 */
export function useHealth(): HealthState {
  // Cred-aware: the client sends the chosen provider + key, so health reflects the user's own
  // provider. Re-probe when either changes (e.g. right after a key is entered).
  const { provider, apiKey } = useCredentials();
  const [state, setState] = useState<HealthState>({ kind: "loading", data: null });

  const check = useCallback(async () => {
    try {
      const data = await api.health();
      setState({ kind: "ok", data });
    } catch {
      // Keep the last-known data (if any) so the dot can go red without the
      // engine/model label flickering away. A 400/401 (unknown provider / missing key) lands
      // here too — surfaced as "unreachable" for the indicator.
      setState((prev) => ({ kind: "unreachable", data: prev.data }));
    }
  }, []);

  useEffect(() => {
    let active = true;
    const run = () => {
      if (active) void check();
    };

    run();
    const id = window.setInterval(run, POLL_MS);

    // CHANGED: Removed the window.addEventListener("focus") bindings to completely
    // stop health checks from firing repeatedly when alt-tabbing into the browser.
    return () => {
      active = false;
      window.clearInterval(id);
    };
    // Re-run (and re-probe immediately) when the selected provider or key changes.
  }, [check, provider, apiKey]);

  return state;
}
