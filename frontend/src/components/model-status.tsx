import { FlaskConical } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Presentational health and model indicator used by ModelPicker.
 *
 * Displays the current model, engine status, and connectivity state using data
 * provided by its parent. The component is intentionally stateless and performs
 * no API calls of its own, allowing ModelPicker to remain the single source of
 * truth for health, model, and provider information.
 *
 * A reachable engine is shown with a green indicator, an unreachable engine
 * with amber, and a backend failure with red. Mock engines are highlighted
 * prominently to make test configurations obvious during development.
 */

/**
 * `asTrigger` renders the indicator inline without its card styling so it can
 * serve as the content of the ModelPicker trigger. This allows the model,
 * engine status, and settings control to appear as a single unified sidebar
 * action while reusing the same presentation component in other contexts.
 */

interface ModelStatusProps {
  asTrigger?: boolean;
  loading: boolean;
  apiUp: boolean;
  engineUp: boolean;
  engine?: string;
  displayModel: string;
}

export function ModelStatus({ asTrigger = false, loading, apiUp, engineUp, engine, displayModel }: ModelStatusProps) {
  const isMock = engineUp && engine === "mock";
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
    <div
      className={cn("flex items-center gap-2 text-xs", !asTrigger && "rounded-lg border bg-background/60 px-2.5 py-2")}
    >
      <span
        className={cn("size-2 shrink-0 rounded-full", dotClass)}
        role="img"
        aria-label={dotTitle}
        title={dotTitle}
      />
      <div className="min-w-0 flex-1 leading-tight">
        {engineUp ? (
          <>
            <div className="flex items-center gap-1.5">
              <span className="truncate font-medium text-foreground" title={displayModel}>
                {displayModel}
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
            <div className="truncate text-muted-foreground">{isMock ? "mock engine" : `${engine} engine`}</div>
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
                  ? `${engine ?? "engine"} not reachable`
                  : "backend unreachable"}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
