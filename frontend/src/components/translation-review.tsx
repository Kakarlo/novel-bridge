import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { ArrowRight, Check, ChevronRight, Loader2, Sparkles, X } from "lucide-react";

import { api, ApiError } from "@/api/client";
import type { GlossaryPairSuggestion } from "@/api/types";
import { getStorage } from "@/storage";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

/**
 * Lightweight review surface for a SAVED translation (FRONTEND_TODO #1 + #3). Two groups
 * that both derive from the translation's source chapter:
 *
 *   • Source-language terms — zh/ja proper nouns from the source text (EXPERIMENTAL, gated by
 *     NB_SOURCE_TERMS). Copy a term to pair it with an English name in the Glossary tab.
 *   • Suggested source↔English pairs — LLM-paired suggestions binding each source term to the
 *     exact English spelling the translation actually used (replaces the old deterministic
 *     aligner, which produced unreliable pairs). This is an on-demand LLM call, so it runs
 *     only when the user clicks "Suggest pairs" — never automatically. "Confirm" writes the
 *     pair to the glossary (upsert on surface_form, defaults to approved); "dismiss" hides it.
 *
 * Source terms degrade silently (404 feature off / [] model unavailable → render nothing).
 * This only makes sense for a persisted translation (it has a source chapter on the server),
 * so the caller mounts it only when a translation_id exists — never during a live stream.
 */
export function TranslationReview({
  projectId,
  translationId,
  onGlossaryChanged,
}: {
  projectId: string;
  translationId: string;
  onGlossaryChanged?: () => void;
}) {
  const [sourceTerms, setSourceTerms] = useState<string[]>([]);
  const [pairs, setPairs] = useState<GlossaryPairSuggestion[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [extracted, setExtracted] = useState(false);
  // Rows the user has resolved (confirmed or dismissed) this view — hide them locally.
  const [resolved, setResolved] = useState<Set<string>>(new Set());

  useEffect(() => {
    let active = true;
    setResolved(new Set());
    setPairs([]);
    setExtracted(false);
    // Source terms are cheap + deterministic, so fetch on mount. 404 (feature off) and []
    // (model unavailable) both degrade to "render nothing" — swallow and leave empty.
    api
      .translationSourceTerms(translationId)
      .then((terms) => active && setSourceTerms(terms))
      .catch(() => active && setSourceTerms([]));
    return () => {
      active = false;
    };
  }, [translationId]);

  const pairKey = (c: GlossaryPairSuggestion) => `${c.source_term}→${c.surface_form}`;
  const visiblePairs = pairs.filter((c) => !resolved.has(pairKey(c)));

  async function suggestPairs() {
    setExtracting(true);
    try {
      // On-demand LLM call: pairs source terms to the English spellings in the translation.
      const result = await api.translationExtractGlossary(translationId);
      setPairs(result);
      setExtracted(true);
      if (result.length === 0) toast.info("No new pairings found");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not extract glossary pairs");
    } finally {
      setExtracting(false);
    }
  }

  async function confirmPair(c: GlossaryPairSuggestion) {
    try {
      // Upsert on surface_form via the existing glossary write — no new endpoint. A paired
      // entry (source_term set) defaults to approved on the backend, so it steers the next
      // translation immediately. Carry the model's category/gender/note through.
      await getStorage().createGlossary(projectId, {
        surface_form: c.surface_form,
        source_term: c.source_term,
        category: c.category,
        gender: c.gender ?? undefined,
        note: c.note ?? undefined,
      });
      setResolved((prev) => new Set(prev).add(pairKey(c)));
      onGlossaryChanged?.();
      toast.success(`Paired “${c.source_term}” → “${c.surface_form}”`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save the pairing");
    }
  }

  function dismissPair(c: GlossaryPairSuggestion) {
    setResolved((prev) => new Set(prev).add(pairKey(c)));
  }

  // Cap the whole surface and scroll inside it, so the review never swallows the reading
  // pane even with both groups expanded; the groups themselves are collapsible to reclaim
  // space entirely.
  return (
    <section className="pane-scroll max-h-[40%] shrink-0 space-y-3 overflow-y-auto border-b bg-muted/20 px-6 py-4">
      <div className="flex items-center gap-2 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
        <Sparkles className="size-3.5" />
        Review
        <Button
          size="xs"
          variant="outline"
          className="ml-auto normal-case"
          onClick={suggestPairs}
          disabled={extracting}
        >
          {extracting ? <Loader2 className="animate-spin" /> : <Sparkles />}
          {extracting ? "Extracting…" : extracted ? "Re-suggest pairs" : "Suggest pairs"}
        </Button>
      </div>

      {visiblePairs.length > 0 && (
        <CollapsibleGroup
          title="Suggested source↔English pairs"
          count={visiblePairs.length}
          hint="paired by the model from the source and its translation — confirm to add a glossary pairing, or dismiss"
        >
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
                    onClick={() => confirmPair(c)}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <Check />
                  </Button>
                  <Button
                    size="icon-xs"
                    variant="ghost"
                    aria-label={`Dismiss pairing ${c.source_term} to ${c.surface_form}`}
                    title="Dismiss this suggestion"
                    onClick={() => dismissPair(c)}
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

      {sourceTerms.length > 0 && (
        <CollapsibleGroup
          title="Source-language terms"
          count={sourceTerms.length}
          hint="proper nouns from the source chapter — click to copy, then pair with an English name in the Glossary tab"
        >
          <ul className="flex flex-wrap gap-1.5">
            {sourceTerms.map((term) => (
              <li key={term}>
                <button
                  type="button"
                  onClick={() => {
                    void navigator.clipboard?.writeText(term);
                    toast.success(`Copied “${term}”`);
                  }}
                  title="Copy source term"
                  className="inline-flex h-7 items-center gap-1 rounded-md border bg-card px-2 text-sm font-normal transition-colors hover:bg-muted"
                >
                  {term}
                </button>
              </li>
            ))}
          </ul>
        </CollapsibleGroup>
      )}
    </section>
  );
}

// A collapsible group on the shadcn/radix Collapsible primitive. Default open; the chevron
// rotates off the trigger's data-state so the user can fold a group to reclaim space.
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
