import { useEffect, useState } from "react";
import { toast } from "sonner";
import { BookA, FileText, Plus, RefreshCw, Sparkles, Trash2, X } from "lucide-react";

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

export function ReferencesTab({ projectId }: { projectId: string }) {
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
        }}
      />
    );
  }

  if (selected) {
    return (
      <ReferenceReader
        projectId={projectId}
        reference={selected}
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
      });
      toast.success("Reference added");
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

      <div className="flex justify-end gap-2 border-t px-6 py-4">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={submitting}>
          Save reference
        </Button>
      </div>
    </form>
  );
}

function ReferenceReader({
  projectId,
  reference,
  onBack,
  onDelete,
  onUpdated,
  pendingDelete,
  setPendingDelete,
  onConfirmDelete,
}: {
  projectId: string;
  reference: ReferenceChapter;
  onBack: () => void;
  onDelete: () => void;
  onUpdated: (ref: ReferenceChapter) => void;
  pendingDelete: ReferenceChapter | null;
  setPendingDelete: (r: ReferenceChapter | null) => void;
  onConfirmDelete: (r: ReferenceChapter) => Promise<void>;
}) {
  const [resummarizing, setResummarizing] = useState(false);

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
        <div className="mx-auto max-w-2xl px-6 py-8">
          <DerivedContext projectId={projectId} reference={reference} />
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
 * The engine-derived context for a reference: a short style/plot summary and
 * candidate glossary terms. References are English, so candidate terms are already
 * English surface forms — promoting one adds it to the glossary by its English name
 * in a single click, as a `candidate` awaiting approval (English-first; no source
 * mapping to type up front). Phase 5 adds category/gender on promotion.
 */
function DerivedContext({ projectId, reference }: { projectId: string; reference: ReferenceChapter }) {
  // Terms already promoted this session, so the chip can show a done state
  // without a full refetch of the glossary.
  const [promoted, setPromoted] = useState<Set<string>>(new Set());

  const hasSummary = !!reference.summary?.trim();
  const terms = reference.candidate_terms ?? [];

  if (!hasSummary && terms.length === 0) {
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
      // English-first: the candidate term IS the English name. Add as a candidate.
      await api.createGlossary(projectId, { surface_form: en, status: "candidate" });
      setPromoted((prev) => new Set(prev).add(term));
      toast.success(`Added “${en}” to the glossary`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not add to glossary");
    }
  }

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

      {terms.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-foreground">
            Candidate terms
            <span className="ml-1.5 font-normal text-muted-foreground">
              — click to add an English name to the glossary (as a candidate to approve later)
            </span>
          </div>
          <ul className="flex flex-wrap gap-1.5">
            {terms.map((term) => {
              const done = promoted.has(term);
              return (
                <li key={term}>
                  {done ? (
                    <Badge variant="secondary" className="gap-1 font-normal" data-icon="inline-start">
                      <BookA className="size-3" />
                      {term}
                    </Badge>
                  ) : (
                    <Button
                      size="xs"
                      variant="outline"
                      className="h-6 gap-1 font-normal"
                      onClick={() => promote(term)}
                      title="Add to glossary"
                    >
                      {term}
                      <Plus className="size-3 opacity-70" />
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}
