import { useCallback, useEffect, useState } from "react";

import { api } from "@/api/client";

export interface Health {
  status: string;
  engine: string;
  model: string;
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
  const [state, setState] = useState<HealthState>({ kind: "loading", data: null });

  const check = useCallback(async () => {
    try {
      const data = await api.health();
      setState({ kind: "ok", data });
    } catch {
      // Keep the last-known data (if any) so the dot can go red without the
      // engine/model label flickering away.
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
    const onFocus = () => run();
    window.addEventListener("focus", onFocus);

    return () => {
      active = false;
      window.clearInterval(id);
      window.removeEventListener("focus", onFocus);
    };
  }, [check]);

  return state;
}
