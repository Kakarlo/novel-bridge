import { ArrowRight, Check, ChevronRight, Loader2, Sparkles, X } from "lucide-react";
import type { ReactNode } from "react";

import type { GlossaryPairSuggestion } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

interface GlossaryPairReviewProps {
  pairs: GlossaryPairSuggestion[];
  extracting: boolean;
  extracted: boolean;
  hint: string;
  onExtract: () => void | Promise<void>;
  onConfirm: (pair: GlossaryPairSuggestion) => void | Promise<void>;
  onDismiss: (pair: GlossaryPairSuggestion) => void | Promise<void>;
}

export function GlossaryPairReview({
  pairs,
  extracting,
  extracted,
  hint,
  onExtract,
  onConfirm,
  onDismiss,
}: GlossaryPairReviewProps) {
  const pairKey = (c: GlossaryPairSuggestion) => `${c.source_term}→${c.surface_form}`;

  const visiblePairs = pairs;

  return (
    <>
      <div className="flex items-center gap-2 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
        <Sparkles className="size-3.5" />
        Review
        <Button size="xs" variant="outline" className="ml-auto normal-case" onClick={onExtract} disabled={extracting}>
          {extracting ? <Loader2 className="animate-spin" /> : <Sparkles />}

          {extracting ? "Extracting…" : extracted ? "Re-suggest pairs" : "Suggest pairs"}
        </Button>
      </div>

      {visiblePairs.length > 0 && (
        <CollapsibleGroup title="Suggested source↔English pairs" count={visiblePairs.length} hint={hint}>
          <ul className="space-y-1.5">
            {visiblePairs.map((c) => (
              <li
                key={pairKey(c)}
                className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border bg-card px-2.5 py-1.5 text-sm"
              >
                <span className="font-medium">{c.source_term}</span>

                <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" />

                <span className="font-medium">{c.surface_form}</span>

                <Badge variant="outline" className="h-4 px-1.5 py-0 text-[10px] capitalize">
                  {c.category}
                </Badge>

                {c.gender && c.gender !== "unknown" && (
                  <span className="text-[11px] text-muted-foreground">{c.gender}</span>
                )}

                {c.note && <span className="truncate text-[11px] text-muted-foreground">{c.note}</span>}

                <div className="ml-auto flex shrink-0 items-center gap-1">
                  <Button
                    size="icon-xs"
                    variant="ghost"
                    aria-label={`Confirm pairing ${c.source_term} to ${c.surface_form}`}
                    title="Add this pairing to the glossary"
                    onClick={() => onConfirm(c)}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <Check />
                  </Button>

                  <Button
                    size="icon-xs"
                    variant="ghost"
                    aria-label={`Dismiss pairing ${c.source_term} to ${c.surface_form}`}
                    title="Dismiss this suggestion"
                    onClick={() => onDismiss(c)}
                    className="text-muted-foreground hover:text-destructive"
                  >
                    <X />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </CollapsibleGroup>
      )}
    </>
  );
}

function CollapsibleGroup({
  title,
  count,
  hint,
  children,
}: {
  title: string;
  count: number;
  hint: string;
  children: ReactNode;
}) {
  return (
    <Collapsible defaultOpen className="space-y-2">
      <CollapsibleTrigger className="group/trigger flex w-full items-center gap-1.5 text-left text-xs font-medium text-foreground">
        <ChevronRight className="size-3.5 shrink-0 text-muted-foreground transition-transform duration-150 group-data-[state=open]/trigger:rotate-90" />

        <span className="shrink-0">{title}</span>

        <Badge variant="secondary" className="h-4 px-1.5 py-0 text-[10px]">
          {count}
        </Badge>

        <span className="ml-1 truncate font-normal text-muted-foreground">— {hint}</span>
      </CollapsibleTrigger>

      <CollapsibleContent>{children}</CollapsibleContent>
    </Collapsible>
  );
}
