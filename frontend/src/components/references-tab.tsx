import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FileText, Plus, RefreshCw, ScanSearch, Sparkles, Trash2, X } from "lucide-react";

import { api, ApiError } from "@/api/client";
import type { ReferenceChapter } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

export function ReferencesTab({
  projectId,
  onGlossaryChanged,
}: {
  projectId: string;
  // Notify the workspace after a glossary/reference mutation so the header counts refresh.
  // The glossary tab itself refetches when it next becomes active (not forced here).
  onGlossaryChanged?: () => void;
}) {
  const [items, setItems] = useState<ReferenceChapter[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [composing, setComposing] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<ReferenceChapter | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setSelectedId(null);
    setComposing(false);
    api
      .listReferences(projectId)
      .then((data) => {
        if (active) setItems(data);
      })
      .catch((e) => {
        if (active) toast.error(e instanceof Error ? e.message : "Failed to load");
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [projectId]);

  const selected = items.find((r) => r.id === selectedId) ?? null;

  async function handleDelete(ref: ReferenceChapter) {
    await api.deleteReference(ref.id);
    setItems((prev) => prev.filter((r) => r.id !== ref.id));
    if (selectedId === ref.id) setSelectedId(null);
    onGlossaryChanged?.(); // refresh the references count badge
    toast.success("Reference removed");
  }

  if (loading) {
    return (
      <div className="space-y-2 p-6">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-16 animate-pulse rounded-lg bg-muted/60" />
        ))}
      </div>
    );
  }

  if (composing) {
    return (
      <ReferenceComposer
        projectId={projectId}
        onCancel={() => setComposing(false)}
        onAdded={(ref) => {
          setItems((prev) => [ref, ...prev]);
          setComposing(false);
          setSelectedId(ref.id);
          onGlossaryChanged?.(); // refresh the references count badge
        }}
      />
    );
  }

  if (selected) {
    return (
      <ReferenceReader
        projectId={projectId}
        reference={selected}
        onGlossaryChanged={onGlossaryChanged}
        onBack={() => setSelectedId(null)}
        onDelete={() => setPendingDelete(selected)}
        onUpdated={(ref) => setItems((prev) => prev.map((r) => (r.id === ref.id ? ref : r)))}
        pendingDelete={pendingDelete}
        setPendingDelete={setPendingDelete}
        onConfirmDelete={handleDelete}
      />
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-4 border-b px-6 py-4">
        <div>
          <h2 className="font-heading text-xl font-semibold tracking-tight">Reference chapters</h2>
          <p className="text-sm text-muted-foreground">
            Paste previously translated chapters. The newest one anchors tone and continuity.
          </p>
        </div>
        <Button onClick={() => setComposing(true)} data-icon="inline-start">
          <Plus />
          Add reference
        </Button>
      </div>

      {items.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No references yet"
          body="Add an existing English chapter so translations match its voice, names, and pacing."
          action={
            <Button variant="outline" onClick={() => setComposing(true)}>
              Paste your first chapter
            </Button>
          }
        />
      ) : (
        <ScrollArea className="min-h-0 flex-1">
          <ul className="divide-y">
            {items.map((ref) => (
              <li key={ref.id}>
                <button
                  className="group/row flex w-full items-start gap-3 px-6 py-4 text-left transition-colors duration-150 hover:bg-muted/50"
                  onClick={() => setSelectedId(ref.id)}
                >
                  <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{ref.title}</div>
                    <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">
                      {ref.summary?.trim() || ref.content}
                    </p>
                    <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground/80">
                      <span>{ref.content.length.toLocaleString()} chars</span>
                      <span>·</span>
                      <span>{formatDate(ref.created_at)}</span>
                      {ref.summary ? (
                        <Badge variant="secondary" className="h-4 px-1.5 py-0 text-[10px]">
                          {ref.candidate_terms.length} term{ref.candidate_terms.length === 1 ? "" : "s"}
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="h-4 px-1.5 py-0 text-[10px]">
                          not summarized
                        </Badge>
                      )}
                    </div>
                  </div>
                  <Trash2
                    className="mt-0.5 size-4 shrink-0 text-muted-foreground opacity-0 transition-opacity duration-150 group-hover/row:opacity-100"
                    onClick={(e) => {
                      e.stopPropagation();
                      setPendingDelete(ref);
                    }}
                  />
                </button>
              </li>
            ))}
          </ul>
        </ScrollArea>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title="Remove this reference?"
        description={
          <>
            <span className="font-medium text-foreground">{pendingDelete?.title}</span> will no longer be used for
            context.
          </>
        }
        confirmLabel="Remove"
        destructive
        onConfirm={async () => {
          if (pendingDelete) await handleDelete(pendingDelete);
        }}
      />
    </div>
  );
}

function ReferenceComposer({
  projectId,
  onCancel,
  onAdded,
}: {
  projectId: string;
  onCancel: () => void;
  onAdded: (ref: ReferenceChapter) => void;
}) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [touched, setTouched] = useState(false);
  // Names-only mode: skip the (slow, local-LLM) AI summary and run only the offline name
  // detector. Lets the user test the extractor without waiting on the model.
  const [namesOnly, setNamesOnly] = useState(false);

  const titleEmpty = !title.trim();
  const contentEmpty = !content.trim();
  const invalid = titleEmpty || contentEmpty;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (invalid) return;
    try {
      setSubmitting(true);
      const ref = await api.addReference(projectId, {
        title: title.trim(),
        content: content.trim(),
        extract_summary: !namesOnly,
      });
      toast.success(namesOnly ? "Reference added (names only)" : "Reference added");
      onAdded(ref);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not add reference");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <h2 className="font-heading text-xl font-semibold tracking-tight">Add a reference chapter</h2>
        <Button type="button" variant="ghost" size="icon-sm" onClick={onCancel}>
          <X />
          <span className="sr-only">Cancel</span>
        </Button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-4 p-6">
        <div className="space-y-1.5">
          <Label htmlFor="ref-title">Chapter title</Label>
          <Input
            id="ref-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Chapter 12 — The Gu Master's Return"
            aria-invalid={touched && titleEmpty}
          />
          {touched && titleEmpty && <p className="text-xs text-destructive">A title is required.</p>}
        </div>

        <div className="flex min-h-0 flex-1 flex-col space-y-1.5">
          <Label htmlFor="ref-content">Translated text</Label>
          <Textarea
            id="ref-content"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Paste the full English translation of this chapter…"
            aria-invalid={touched && contentEmpty}
            className={cn("min-h-0 flex-1 resize-none font-serif text-[0.95rem] leading-relaxed")}
          />
          <div className="flex items-center justify-between">
            {touched && contentEmpty ? (
              <p className="text-xs text-destructive">Reference content can’t be empty.</p>
            ) : (
              <span className="text-[11px] text-muted-foreground">{content.length.toLocaleString()} characters</span>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between gap-4 border-t px-6 py-4">
        <label className="flex items-center gap-2 text-sm text-muted-foreground select-none">
          <input
            type="checkbox"
            checked={namesOnly}
            onChange={(e) => setNamesOnly(e.target.checked)}
            className="size-4 rounded border-input accent-[var(--accent-brand)]"
          />
          Names only — skip the AI summary (faster; just runs the name detector)
        </label>
        <div className="flex gap-2">
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Saving…" : "Save reference"}
          </Button>
        </div>
      </div>
    </form>
  );
}

function ReferenceReader({
  projectId,
  reference,
  onGlossaryChanged,
  onBack,
  onDelete,
  onUpdated,
  pendingDelete,
  setPendingDelete,
  onConfirmDelete,
}: {
  projectId: string;
  reference: ReferenceChapter;
  onGlossaryChanged?: () => void;
  onBack: () => void;
  onDelete: () => void;
  onUpdated: (ref: ReferenceChapter) => void;
  pendingDelete: ReferenceChapter | null;
  setPendingDelete: (r: ReferenceChapter | null) => void;
  onConfirmDelete: (r: ReferenceChapter) => Promise<void>;
}) {
  const [resummarizing, setResummarizing] = useState(false);
  const [redetecting, setRedetecting] = useState(false);

  async function resummarize() {
    try {
      setResummarizing(true);
      const updated = await api.resummarizeReference(reference.id);
      onUpdated(updated);
      toast.success("Reference re-summarized");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Re-summarize failed");
    } finally {
      setResummarizing(false);
    }
  }

  async function redetect() {
    try {
      setRedetecting(true);
      const updated = await api.redetectReferenceNames(reference.id);
      onUpdated(updated);
      const n = updated.detected_names.length;
      toast.success(`Redetected names (${n} found)`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Redetect failed");
    } finally {
      setRedetecting(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-4 border-b px-6 py-4">
        <div className="min-w-0">
          <button onClick={onBack} className="text-xs text-muted-foreground transition-colors hover:text-foreground">
            ← All references
          </button>
          <h2 className="truncate font-heading text-xl font-semibold tracking-tight">{reference.title}</h2>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={redetect} disabled={redetecting} data-icon="inline-start">
            <ScanSearch className={cn(redetecting && "animate-pulse")} />
            {redetecting ? "Redetecting…" : "Redetect names"}
          </Button>
          <Button variant="outline" size="sm" onClick={resummarize} disabled={resummarizing} data-icon="inline-start">
            <RefreshCw className={cn(resummarizing && "animate-spin")} />
            {resummarizing ? "Re-summarizing…" : "Re-summarize"}
          </Button>
          <Button variant="destructive" size="sm" onClick={onDelete}>
            <Trash2 />
            Remove
          </Button>
        </div>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        {/* Wide reading column for desktop (~75-80% of available width). */}
        <div className="mx-auto w-[78%] min-w-0 max-w-5xl px-6 py-8">
          <DerivedContext projectId={projectId} reference={reference} onGlossaryChanged={onGlossaryChanged} />
          <article className="mt-6 border-t pt-6 font-serif text-[1.02rem] leading-[1.75] whitespace-pre-wrap">
            {reference.content}
          </article>
        </div>
      </ScrollArea>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title="Remove this reference?"
        description={
          <>
            <span className="font-medium text-foreground">{pendingDelete?.title}</span> will no longer be used for
            context.
          </>
        }
        confirmLabel="Remove"
        destructive
        onConfirm={async () => {
          if (pendingDelete) await onConfirmDelete(pendingDelete);
        }}
      />
    </div>
  );
}

/**
 * The engine-derived context for a reference: a style/plot summary plus two separate
 * groups of promotable English names — rule-based "Detected names" (field-fix #2) and the
 * AI's "Candidate terms". References are English, so each term IS an English surface form;
 * promoting adds it to the glossary as a `candidate` in one click (English-first).
 *
 * Option B (unified vocabulary): a suggestion chip has two actions, both of which write to
 * the glossary (one concept, persisted — no more localStorage "dismiss"):
 *   • "+"  = promote → create a glossary entry as `candidate` (approve later).
 *   • "✕"  = reject  → create a glossary entry as `rejected` (soft-delete; remembered so
 *            the suggestion won't resurface, and restorable from the Glossary tab).
 * Both hide the chip, because any surface form already present in the glossary (regardless
 * of status) is filtered out. We fetch the glossary on load (and on the shared
 * glossaryVersion signal) to know which chips to hide.
 */
function DerivedContext({
  projectId,
  reference,
  onGlossaryChanged,
}: {
  projectId: string;
  reference: ReferenceChapter;
  onGlossaryChanged?: () => void;
}) {
  // Surface forms already in the glossary (case-insensitive), any status. A term that's
  // been promoted OR rejected lives here, so either action hides the chip persistently.
  const [inGlossary, setInGlossary] = useState<Set<string>>(new Set());

  useEffect(() => {
    let active = true;
    api
      .listGlossary(projectId)
      .then((entries) => {
        if (active) setInGlossary(new Set(entries.map((e) => e.surface_form.toLowerCase())));
      })
      .catch(() => {
        /* non-fatal: chips just won't pre-filter */
      });
    return () => {
      active = false;
    };
    // Re-fetch when switching to a different reference. Our own promote/reject updates the
    // inGlossary set locally, so chips hide immediately without a refetch.
  }, [projectId, reference.id]);

  const hidden = (t: string) => inGlossary.has(t.toLowerCase());

  const hasSummary = !!reference.summary?.trim();
  // Hide terms already in the glossary (promoted or rejected). Detected (rule-based) names
  // come first; drop any that also appear in the AI candidate list to avoid showing twice.
  const detected = (reference.detected_names ?? []).filter((t) => !hidden(t));
  const detectedLower = new Set(detected.map((t) => t.toLowerCase()));
  const candidates = (reference.candidate_terms ?? []).filter((t) => !hidden(t) && !detectedLower.has(t.toLowerCase()));

  const nothingToShow = !hasSummary && detected.length === 0 && candidates.length === 0;
  if (nothingToShow) {
    return (
      <div className="rounded-lg border border-dashed bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
        <Sparkles className="mr-1.5 inline size-3.5" />
        No derived context yet. Use “Re-summarize” to extract a summary and candidate terms (the engine must be
        reachable).
      </div>
    );
  }

  async function promote(term: string) {
    const en = term.trim();
    if (!en) return;
    try {
      // English-first: the term IS the English name. Add as a candidate to approve later.
      await api.createGlossary(projectId, { surface_form: en, status: "candidate" });
      // Hide the chip immediately; tell the workspace so the glossary tab + counts update.
      setInGlossary((prev) => new Set(prev).add(en.toLowerCase()));
      onGlossaryChanged?.();
      toast.success(`Added “${en}” to the glossary`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not add to glossary");
    }
  }

  async function reject(term: string) {
    const en = term.trim();
    if (!en) return;
    try {
      // Option B: rejecting a suggestion is a persistent soft-delete — a glossary entry
      // with status 'rejected'. It's remembered (won't resurface), stays out of the
      // prompt and the term count, and can be restored from the Glossary tab.
      await api.createGlossary(projectId, { surface_form: en, status: "rejected" });
      setInGlossary((prev) => new Set(prev).add(en.toLowerCase()));
      onGlossaryChanged?.();
      toast.success(`Rejected “${en}” (restore it from the Glossary tab)`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not reject term");
    }
  }

  // Each chip: click the name to add it to the glossary; click the ✕ to reject it (a
  // persistent soft-delete, restorable from the Glossary tab).
  const chip = (term: string) => (
    <li key={term}>
      <span className="inline-flex h-7 items-center overflow-hidden rounded-md border bg-background">
        <button
          type="button"
          onClick={() => promote(term)}
          title="Add to glossary"
          className="inline-flex h-full items-center gap-1 px-2 text-sm font-normal transition-colors hover:bg-muted"
        >
          {term}
          <Plus className="size-3 opacity-70" />
        </button>
        <button
          type="button"
          onClick={() => reject(term)}
          aria-label={`Reject ${term}`}
          title="Reject (soft-delete; restore from the Glossary tab)"
          className="inline-flex h-full items-center border-l px-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
        >
          <X className="size-3" />
        </button>
      </span>
    </li>
  );

  return (
    <section className="space-y-4 rounded-lg border bg-muted/20 p-4">
      <div className="flex items-center gap-2 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
        <Sparkles className="size-3.5" />
        Derived context
      </div>

      {hasSummary && (
        <div className="space-y-1">
          <div className="text-xs font-medium text-foreground">Summary</div>
          <p className="text-sm leading-relaxed text-muted-foreground">{reference.summary}</p>
        </div>
      )}

      {detected.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-foreground">
            Detected names
            <span className="ml-1.5 font-normal text-muted-foreground">
              — found by rules (capitalized proper nouns); click to add to the glossary
            </span>
          </div>
          <ul className="flex flex-wrap gap-1.5">{detected.map(chip)}</ul>
        </div>
      )}

      {candidates.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-foreground">
            Candidate terms
            <span className="ml-1.5 font-normal text-muted-foreground">
              — suggested by the model; click to add to the glossary (as a candidate to approve later)
            </span>
          </div>
          <ul className="flex flex-wrap gap-1.5">{candidates.map(chip)}</ul>
        </div>
      )}
    </section>
  );
}
