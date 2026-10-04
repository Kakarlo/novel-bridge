import { FlaskConical } from "lucide-react";

import { useHealth } from "@/hooks/use-health";
import { cn } from "@/lib/utils";

/**
 * Compact engine/model health indicator for the sidebar footer. Driven by
 * GET /api/health (polled lightly). Shows a reachable/unreachable dot plus the
 * engine and model, and flags the mock engine prominently so a leaked
 * NB_ENGINE=mock is obvious at a glance. Groundwork for a future model picker.
 */
export function ModelStatus() {
  const health = useHealth();
  const data = health.data;
  const reachable = health.kind === "ok";
  const loading = health.kind === "loading";
  const isMock = reachable && data?.engine === "mock";

  const dotTitle = loading
    ? "Checking engine…"
    : reachable
      ? "Engine reachable"
      : "Engine unreachable";

  return (
    <div className="flex items-center gap-2 rounded-lg border bg-background/60 px-2.5 py-2 text-xs">
      <span
        className={cn(
          "size-2 shrink-0 rounded-full",
          loading
            ? "animate-pulse bg-muted-foreground/50"
            : reachable
              ? "bg-emerald-500"
              : "bg-destructive"
        )}
        role="img"
        aria-label={dotTitle}
        title={dotTitle}
      />
      <div className="min-w-0 flex-1 leading-tight">
        {reachable && data ? (
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
            <div className="truncate text-muted-foreground">
              {isMock ? "mock engine" : `${data.engine} engine`}
            </div>
          </>
        ) : (
          <>
            <div className="font-medium text-foreground">
              {loading ? "Checking engine…" : "Engine offline"}
            </div>
            <div className="truncate text-muted-foreground">
              {loading
                ? "contacting backend"
                : data
                  ? `last seen: ${data.model || data.engine}`
                  : "backend unreachable"}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
