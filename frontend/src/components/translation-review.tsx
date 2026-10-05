import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ArrowRight, Check, Sparkles, X } from "lucide-react";

import { api, ApiError } from "@/api/client";
import type { AlignmentCandidate } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

/**
 * Lightweight review surface for a SAVED translation (FRONTEND_TODO #1 + #3). Two
 * experimental, opt-in groups that both derive from the translation's source chapter:
 *
 *   • Source-language terms — zh/ja proper nouns from the source text; copy a term to pair
 *     it with an English name in the Glossary tab.
 *   • Suggested source↔English pairs — deterministic pairing guesses; "confirm" writes the
 *     pair to the glossary (upsert on surface_form), "dismiss" just hides the row.
 *
 * Both endpoints are gated by NB_SOURCE_TERMS on the backend: a 404 means the feature is
 * off and a `[]` means the model is unavailable — either way we render nothing, never crash.
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
  const [alignments, setAlignments] = useState<AlignmentCandidate[]>([]);
  // Rows the user has resolved (confirmed or dismissed) this view — hide them locally.
  const [resolved, setResolved] = useState<Set<string>>(new Set());

  useEffect(() => {
    let active = true;
    setResolved(new Set());
    // 404 (feature off / missing) and [] (model unavailable) both degrade to "render
    // nothing" — swallow the error and leave the list empty.
    api
      .translationSourceTerms(translationId)
      .then((terms) => active && setSourceTerms(terms))
      .catch(() => active && setSourceTerms([]));
    api
      .translationTermAlignment(translationId)
      .then((cands) => active && setAlignments(cands))
      .catch(() => active && setAlignments([]));
    return () => {
      active = false;
    };
  }, [translationId]);

  const pairKey = (c: AlignmentCandidate) => `${c.source_term}→${c.surface_form}`;
  const pairs = alignments.filter((c) => !resolved.has(pairKey(c)));

  async function confirmPair(c: AlignmentCandidate) {
    try {
      // Upsert on surface_form via the existing glossary write — no new endpoint. A paired
      // entry (source_term set) defaults to approved on the backend, so it steers the next
      // translation immediately.
      await api.createGlossary(projectId, { surface_form: c.surface_form, source_term: c.source_term });
      setResolved((prev) => new Set(prev).add(pairKey(c)));
      onGlossaryChanged?.();
      toast.success(`Paired “${c.source_term}” → “${c.surface_form}”`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save the pairing");
    }
  }

  function dismissPair(c: AlignmentCandidate) {
    setResolved((prev) => new Set(prev).add(pairKey(c)));
  }

  // Both groups empty (feature off, or nothing detected) — render nothing.
  if (sourceTerms.length === 0 && pairs.length === 0) return null;

  return (
    <section className="space-y-4 border-b bg-muted/20 px-6 py-4">
      <div className="flex items-center gap-2 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
        <Sparkles className="size-3.5" />
        Review (experimental)
      </div>

      {pairs.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-foreground">
            Suggested source↔English pairs
            <span className="ml-1.5 font-normal text-muted-foreground">
              — guesses from appearance order &amp; frequency. Confirm to add a glossary pairing, or dismiss.
            </span>
          </div>
          <ul className="space-y-1.5">
            {pairs.map((c) => (
              <li
                key={pairKey(c)}
                className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border bg-background px-2.5 py-1.5 text-sm"
              >
                <span className="font-medium">{c.source_term}</span>
                <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="font-medium">{c.surface_form}</span>
                <ConfidenceBadge value={c.confidence} />
                <span className="text-[11px] text-muted-foreground">
                  {c.source_count}×src · {c.english_count}×en
                </span>
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
        </div>
      )}

      {sourceTerms.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-foreground">
            Source-language terms
            <span className="ml-1.5 font-normal text-muted-foreground">
              — proper nouns from the source chapter. Click to copy, then pair with an English name in the Glossary tab.
            </span>
          </div>
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
                  className="inline-flex h-7 items-center gap-1 rounded-md border bg-background px-2 text-sm font-normal transition-colors hover:bg-muted"
                >
                  {term}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

// Confidence is a 0..1 guess from a small model — show it honestly as low/med/high rather
// than a false-precision percentage.
function ConfidenceBadge({ value }: { value: number }) {
  const level = value >= 0.66 ? "high" : value >= 0.33 ? "med" : "low";
  return (
    <Badge variant="outline" className="h-4 px-1.5 py-0 text-[10px] capitalize">
      {level}
    </Badge>
  );
}
