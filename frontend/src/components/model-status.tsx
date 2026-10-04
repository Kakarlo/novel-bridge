import { FlaskConical } from "lucide-react";

import { useHealth } from "@/hooks/use-health";
import { cn } from "@/lib/utils";

/**
 * Compact engine/model health indicator for the sidebar footer. Driven by
 * GET /api/health (polled lightly), which now probes the actual LLM engine
 * rather than echoing config. Shows a reachable/unreachable dot plus the engine
 * and model, flags the mock engine prominently (so a leaked NB_ENGINE=mock is
 * obvious), and distinguishes "backend down" from "LLM engine down". Groundwork
 * for a future model picker.
 */
export function ModelStatus() {
  const health = useHealth();
  const data = health.data;
  const loading = health.kind === "loading";
  // The backend API responded.
  const apiUp = health.kind === "ok";
  // The backend reached the actual LLM engine.
  const engineUp = apiUp && !!data?.reachable;
  const isMock = engineUp && data?.engine === "mock";

  let dotClass: string;
  let dotTitle: string;
  if (loading) {
    dotClass = "animate-pulse bg-muted-foreground/50";
    dotTitle = "Checking engine…";
  } else if (engineUp) {
    dotClass = "bg-emerald-500";
    dotTitle = "Engine reachable";
  } else if (apiUp) {
    // API is up but the LLM server is unreachable — amber, not red.
    dotClass = "bg-amber-500";
    dotTitle = "LLM engine unreachable";
  } else {
    dotClass = "bg-destructive";
    dotTitle = "Backend unreachable";
  }

  return (
    <div className="flex items-center gap-2 rounded-lg border bg-background/60 px-2.5 py-2 text-xs">
      <span
        className={cn("size-2 shrink-0 rounded-full", dotClass)}
        role="img"
        aria-label={dotTitle}
        title={dotTitle}
      />
      <div className="min-w-0 flex-1 leading-tight">
        {engineUp && data ? (
          <>
            <div className="flex items-center gap-1.5">
              <span className="truncate font-medium text-foreground" title={data.model}>
                {data.model || "unknown model"}
              </span>
              {isMock && (
                <span
                  className="inline-flex shrink-0 items-center gap-0.5 rounded bg-accent-brand/15 px-1 py-0.5 text-[10px] font-semibold tracking-wide text-accent-brand-foreground uppercase"
                  title="Running the deterministic mock engine (NB_ENGINE=mock) — not real translation."
                >
                  <FlaskConical className="size-2.5" />
                  Mock
                </span>
              )}
            </div>
            <div className="truncate text-muted-foreground">{isMock ? "mock engine" : `${data.engine} engine`}</div>
          </>
        ) : (
          <>
            <div className="font-medium text-foreground">
              {loading ? "Checking engine…" : apiUp ? "LLM engine offline" : "Backend offline"}
            </div>
            <div className="truncate text-muted-foreground">
              {loading
                ? "contacting backend"
                : apiUp
                  ? `${data?.engine ?? "engine"} not reachable`
                  : "backend unreachable"}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
