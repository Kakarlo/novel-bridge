import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Clock, X } from "lucide-react";

import { api } from "@/api/client";
import type { Translation } from "@/api/types";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { formatDate, langLabel } from "@/lib/format";

interface HistoryPanelProps {
  projectId: string;
  /** Bumped by the parent after a save so the list refetches. */
  refreshKey: number;
  activeId: string | null;
  onClose: () => void;
  onSelect: (t: Translation) => void;
}

export function HistoryPanel({
  projectId,
  refreshKey,
  activeId,
  onClose,
  onSelect,
}: HistoryPanelProps) {
  const [items, setItems] = useState<Translation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api
      .listTranslations(projectId)
      .then((data) => active && setItems(data))
      .catch(
        (e) =>
          active &&
          toast.error(e instanceof Error ? e.message : "Failed to load history")
      )
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [projectId, refreshKey]);

  return (
    <aside className="flex h-full w-80 shrink-0 flex-col border-l bg-muted/20">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Clock className="size-4 text-muted-foreground" />
          <span className="font-heading text-sm font-semibold tracking-tight">
            Saved translations
          </span>
        </div>
        <Button
          size="icon-xs"
          variant="ghost"
          onClick={onClose}
          aria-label="Close history"
        >
          <X />
        </Button>
      </div>

      {loading ? (
        <div className="space-y-2 p-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-16 animate-pulse rounded-lg bg-muted/60" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="px-4 py-10 text-center text-sm text-muted-foreground">
          No saved translations yet. Completed translations are auto-saved and
          appear here.
        </p>
      ) : (
        <ScrollArea className="min-h-0 flex-1">
          <ul className="space-y-1 p-2">
            {items.map((t) => {
              const active = t.id === activeId;
              return (
                <li key={t.id}>
                  <button
                    onClick={() => onSelect(t)}
                    className={cn(
                      "w-full rounded-lg border px-3 py-2.5 text-left transition-colors duration-150",
                      active
                        ? "border-accent-brand/50 bg-accent-brand/10"
                        : "border-transparent hover:bg-muted/60"
                    )}
                  >
                    <p className="line-clamp-2 text-sm leading-snug">
                      {t.output_text || "(empty output)"}
                    </p>
                    <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                      <span className="rounded bg-muted px-1.5 py-0.5 font-medium">
                        {langLabel(t.source_lang)} → EN
                      </span>
                      <span className="truncate">{t.model_used}</span>
                      <span className="ml-auto shrink-0">
                        {formatDate(t.created_at)}
                      </span>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </ScrollArea>
      )}
    </aside>
  );
}
