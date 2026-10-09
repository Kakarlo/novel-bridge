import {
  ChevronDown,
  ChevronRight,
  FileText,
  Pencil,
  Plus,
  ScanSearch,
  Sparkles,
  Trash2,
  Wand2,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/api/client";
import type { Project, ReferenceChapter } from "@/api/types";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { getStorage, getStorageBackend } from "@/storage";
import { ReferenceReview } from "./reference-review";

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
  // The project's style profile lives on the project, not the reference — fetched here so
  // the StyleProfilePanel can show/extract/edit it alongside the references it's built from.
  const [styleProfile, setStyleProfile] = useState<string | null>(null);
  // The source language is needed for the stateless extract-style path (the idb backend has
  // no server-side project for the server to read it from — task 23.4c).
  const [sourceLang, setSourceLang] = useState<Project["source_lang"]>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setSelectedId(null);
    setComposing(false);
    Promise.all([getStorage().listReferences(projectId), getStorage().getProject(projectId)])
      .then(([refs, detail]) => {
        if (!active) return;
        setItems(refs);
        setStyleProfile(detail.project.style_profile);
        setSourceLang(detail.project.source_lang);
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

  // Display in chapter order, with unnumbered references last. Stable sort keeps ties in
  // upload order. `items` itself stays in upload order for mutations.
  const sortedItems = [...items].sort((a, b) => {
    if (a.chapter_number == null && b.chapter_number == null) return 0;
    if (a.chapter_number == null) return 1;
    if (b.chapter_number == null) return -1;
    return a.chapter_number - b.chapter_number;
  });

  async function handleDelete(ref: ReferenceChapter) {
    await getStorage().deleteReference(ref.id);
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
        sourceLang={sourceLang}
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
            Add a translated reference chapter. Optionally include the original source chapter to enable future glossary
            pairing and source-term extraction.
          </p>
        </div>
        <Button onClick={() => setComposing(true)} data-icon="inline-start">
          <Plus />
          Add reference
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-4 p-6">
          <StyleProfilePanel
            projectId={projectId}
            styleProfile={styleProfile}
            sourceLang={sourceLang}
            references={items}
            hasReferences={items.length > 0}
            onChanged={(project) => setStyleProfile(project.style_profile)}
          />

          {items.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No references yet"
              body="Add an existing English chapter, then extract a style profile so translations match its voice, pacing, and conventions."
              action={
                <Button variant="outline" onClick={() => setComposing(true)}>
                  Paste your first chapter
                </Button>
              }
            />
          ) : (
            <ul className="divide-y rounded-lg border">
              {sortedItems.map((ref) => (
                <li key={ref.id}>
                  <button
                    className="group/row flex w-full items-start gap-3 px-4 py-3 text-left transition-colors duration-150 hover:bg-muted/50"
                    onClick={() => setSelectedId(ref.id)}
                  >
                    <ChapterMarker chapter={ref.chapter_number} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{ref.title}</div>
                      <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">{ref.translated_content}</p>
                      <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground/80">
                        {ref.chapter_number == null && <span className="italic">No chapter number</span>}
                        <Badge variant="outline" className="h-4 px-1.5 py-0 text-[10px]">
                          {ref.source_content ? "EN + RAW" : "EN"}
                        </Badge>
                        <span>{(ref.translated_content ?? "").length.toLocaleString()} chars</span>
                        <span>·</span>
                        <span>{formatDate(ref.created_at)}</span>
                        {ref.detected_names.length > 0 && (
                          <Badge variant="secondary" className="h-4 px-1.5 py-0 text-[10px]">
                            {ref.detected_names.length} name{ref.detected_names.length === 1 ? "" : "s"}
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
          )}
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
          if (pendingDelete) await handleDelete(pendingDelete);
        }}
      />
    </div>
  );
}

// Pick the "newest" reference the same way the backend does: highest chapter_number if any
// are numbered, else the last uploaded (created_at ASC → last element). Used to feed
// extract-style a specific chapter so the stateless (idb) path works without a server project.
function newestReference(references: ReferenceChapter[]): ReferenceChapter | undefined {
  if (references.length === 0) return undefined;
  const numbered = references.filter((r) => r.chapter_number != null);
  if (numbered.length > 0) {
    return numbered.reduce((a, b) => (b.chapter_number! > a.chapter_number! ? b : a));
  }
  // listReferences returns oldest-first, so the last element is the most recently uploaded.
  return references[references.length - 1];
}

/**
 * Per-project writing-style profile surface (references-are-for-style pivot). References are
 * human English translations; their value is the TRANSLATION STYLE, extracted by one explicit
 * LLM pass (this panel's "Extract style" button) and injected into every translation prompt.
 *
 * States:
 *   • No style yet → a prompt to extract one (from the newest reference) or write one by hand.
 *   • Has a style  → shows it, with re-extract / edit / clear actions.
 * Editing opens an inline textarea backed by PUT /projects/{id}/style.
 */
function StyleProfilePanel({
  projectId,
  styleProfile,
  sourceLang,
  references,
  hasReferences,
  onChanged,
}: {
  projectId: string;
  styleProfile: string | null;
  sourceLang: Project["source_lang"];
  references: ReferenceChapter[];
  hasReferences: boolean;
  onChanged: (project: Project) => void;
}) {
  const [extracting, setExtracting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);
  const [pendingClear, setPendingClear] = useState(false);

  async function extract() {
    setExtracting(true);
    try {
      // extract-style now returns ONLY the computed style (task 23.4c); the caller persists it.
      // The server picks the newest reference on the DB-backed path, but the browser store has
      // no server-side project, so pass the newest reference's content + source lang explicitly.
      // Sending content works on BOTH backends (the API server analyzes the given text), so one
      // code path covers both.
      const newest = newestReference(references);
      const { style_profile } = await api.extractProjectStyle(
        projectId,
        newest?.translated_content ?? undefined,
        sourceLang
      );
      // Persist through the active store (server-side on the API backend; local on idb).
      const project = await getStorage().updateProjectStyle(projectId, style_profile);
      onChanged(project);
      setOpen(true);
      toast.success("Style profile extracted");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Style extraction failed");
    } finally {
      setExtracting(false);
    }
  }

  async function save() {
    if (!draft.trim()) return;
    setSaving(true);
    try {
      const project = await getStorage().updateProjectStyle(projectId, draft.trim());
      onChanged(project);
      setEditing(false);
      toast.success("Style profile saved");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save style");
    } finally {
      setSaving(false);
    }
  }

  async function clear() {
    try {
      const project = await getStorage().updateProjectStyle(projectId, null);
      onChanged(project);
      toast.success("Style profile cleared");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not clear style");
    }
  }

  if (editing) {
    return (
      <section className="space-y-3 rounded-lg border bg-muted/20 p-4">
        <div className="flex items-center gap-2 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
          <Wand2 className="size-3.5" />
          Edit style profile
        </div>
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={10}
          placeholder="Describe the writing style: register, sentence rhythm, dialogue conventions, honorific handling…"
          className="resize-y font-sans text-sm leading-relaxed"
        />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={save} disabled={saving || !draft.trim()}>
            {saving ? "Saving…" : "Save style"}
          </Button>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-3 rounded-lg border bg-muted/20 p-4">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 rounded-md px-1 py-1 text-left transition-colors hover:bg-muted/50"
        >
          {open ? (
            <ChevronDown className="size-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="size-4 text-muted-foreground" />
          )}

          <div className="flex items-center gap-2 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
            <Wand2 className="size-3.5" />
            Writing Style
            {styleProfile && (
              <span className="normal-case tracking-normal text-muted-foreground/70">
                {styleProfile.split(/\s+/).length} words
              </span>
            )}
          </div>
        </button>

        <div className="flex items-center gap-1.5">
          <Button
            size="xs"
            variant="outline"
            onClick={extract}
            disabled={extracting || !hasReferences}
            title={hasReferences ? "Analyze the newest reference chapter" : "Add a reference first"}
            data-icon="inline-start"
          >
            <Sparkles className={cn(extracting && "animate-pulse")} />
            {extracting ? "Extracting…" : styleProfile ? "Re-extract" : "Extract style"}
          </Button>

          <Button
            size="xs"
            variant="ghost"
            onClick={() => {
              setOpen(true);
              setDraft(styleProfile ?? "");
              setEditing(true);
            }}
            data-icon="inline-start"
          >
            <Pencil />
            {styleProfile ? "Edit" : "Write by hand"}
          </Button>

          {styleProfile && (
            <Button
              size="xs"
              variant="ghost"
              onClick={() => setPendingClear(true)}
              className="text-muted-foreground hover:text-destructive"
            >
              Clear
            </Button>
          )}
        </div>
      </div>

      {!open && (
        <div className="text-sm text-muted-foreground">
          {styleProfile ? (
            <>
              Style profile extracted and active for translations.
              <span className="ml-2 text-xs">
                {references.length} reference{references.length === 1 ? "" : "s"}
              </span>
            </>
          ) : (
            "No style profile yet. Extract one from a reference chapter or write one manually."
          )}
        </div>
      )}

      {open && (
        <>
          {styleProfile ? (
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">{styleProfile}</p>
          ) : (
            <p className="text-sm text-muted-foreground">
              No style profile yet. Extract one from a reference chapter (or write one by hand) and it steers the voice
              of every translation.
            </p>
          )}
        </>
      )}
      <ConfirmDialog
        open={pendingClear}
        onOpenChange={setPendingClear}
        title="Clear writing style?"
        description={
          <>
            The extracted style profile will be removed and future translations will no longer receive writing-style
            guidance.
          </>
        }
        confirmLabel="Clear"
        destructive
        onConfirm={clear}
      />
    </section>
  );
}

// Leading marker in the reference list: a compact "Ch N" chip when the title parsed to a
// chapter number, otherwise the plain file icon (keeps row alignment for unnumbered refs).
function ChapterMarker({ chapter }: { chapter: number | null }) {
  if (chapter == null) {
    return <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" />;
  }
  return (
    <span
      className="mt-0.5 inline-flex h-5 shrink-0 items-center rounded bg-muted px-1.5 text-[11px] font-medium text-muted-foreground tabular-nums"
      title={`Chapter ${chapter}`}
    >
      Ch {chapter}
    </span>
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
  const [translatedContent, setTranslatedContent] = useState("");
  const [sourceContent, setSourceContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [touched, setTouched] = useState(false);

  const titleEmpty = !title.trim();
  const translatedEmpty = !translatedContent.trim();

  const invalid = titleEmpty || translatedEmpty;

  async function submit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault();
    setTouched(true);
    if (invalid) return;
    try {
      setSubmitting(true);
      // Upload is lightweight — stores text + runs the offline name detector. No AI call;
      // the style profile is extracted separately (deliberate action, not on every add).
      const ref = await getStorage().addReference(projectId, {
        title: title.trim(),
        translated_content: translatedContent.trim(),
        source_content: sourceContent.trim() || null,
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
          <Label htmlFor="ref-content">Translated reference</Label>
          <Textarea
            id="ref-content"
            value={translatedContent}
            onChange={(e) => setTranslatedContent(e.target.value)}
            placeholder="Paste the full English translation of this chapter…"
            aria-invalid={touched && translatedEmpty}
            className={cn("min-h-0 flex-1 resize-none font-sans text-[0.95rem] leading-relaxed")}
          />
          <div className="flex items-center justify-between">
            {touched && translatedEmpty ? (
              <p className="text-xs text-destructive">A translated reference chapter is required.</p>
            ) : (
              <span className="text-[11px] text-muted-foreground">
                {translatedContent.length.toLocaleString()} characters
              </span>
            )}
          </div>
        </div>

        <div className="flex min-h-0 flex-1 flex-col space-y-1.5">
          <Label htmlFor="ref-content">Source chapter</Label>
          <Textarea
            id="ref-content"
            value={sourceContent}
            onChange={(e) => setSourceContent(e.target.value)}
            placeholder="Paste the original chapter…"
            className={cn("min-h-0 flex-1 resize-none font-sans text-[0.95rem] leading-relaxed")}
          />
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-muted-foreground">
              {sourceContent.length.toLocaleString()} characters
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-end gap-2 border-t px-6 py-4">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Saving…" : "Save reference"}
        </Button>
      </div>
    </form>
  );
}

function ReferenceReader({
  projectId,
  sourceLang,
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
  sourceLang: Project["source_lang"];
  reference: ReferenceChapter;
  onGlossaryChanged?: () => void;
  onBack: () => void;
  onDelete: () => void;
  onUpdated: (ref: ReferenceChapter) => void;
  pendingDelete: ReferenceChapter | null;
  setPendingDelete: (r: ReferenceChapter | null) => void;
  onConfirmDelete: (r: ReferenceChapter) => Promise<void>;
}) {
  const [redetecting, setRedetecting] = useState(false);
  const [showSource, setShowSource] = useState(false);

  async function redetect() {
    try {
      setRedetecting(true);
      let updated: ReferenceChapter;
      if (getStorageBackend() === "idb") {
        // Stateless path (task 23.4c): compute names from text via /detect-names, then persist
        // locally. Replicate the backend's glossary cross-check so already-resolved names
        // (promoted/rejected into the glossary) don't resurface as chips.
        const [{ detected_names }, glossary] = await Promise.all([
          api.detectNames(reference.translated_content ?? ""),
          getStorage().listGlossary(projectId),
        ]);
        const inGlossary = new Set(glossary.map((e) => e.surface_form.toLowerCase()));
        const filtered = detected_names.filter((n) => !inGlossary.has(n.toLowerCase()));
        updated = await getStorage().setReferenceDetectedNames(reference.id, filtered);
      } else {
        updated = await api.redetectReferenceNames(reference.id);
      }
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
          <div className="flex items-center gap-2">
            {reference.chapter_number != null && (
              <Badge variant="secondary" className="shrink-0 tabular-nums">
                Ch {reference.chapter_number}
              </Badge>
            )}
            <h2 className="truncate font-heading text-xl font-semibold tracking-tight">{reference.title}</h2>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {reference.source_content && (
            <Button variant="outline" size="sm" onClick={() => setShowSource((v) => !v)}>
              {showSource ? "Hide source" : "Show source"}
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={redetect} disabled={redetecting} data-icon="inline-start">
            <ScanSearch className={cn(redetecting && "animate-pulse")} />
            {redetecting ? "Redetecting…" : "Redetect names"}
          </Button>
          <Button variant="destructive" size="sm" onClick={onDelete}>
            <Trash2 />
            Remove
          </Button>
        </div>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        {/* Wide reading column for desktop (~75-80% of available width). */}
        <div className="mx-auto w-full max-w-4xl px-8 py-8">
          <DetectedNames
            projectId={projectId}
            reference={reference}
            onGlossaryChanged={onGlossaryChanged}
            onReferenceUpdated={onUpdated}
          />
          {reference.source_content && (
            <ReferenceReview
              projectId={projectId}
              reference={reference}
              sourceLang={sourceLang}
              onGlossaryChanged={onGlossaryChanged}
            />
          )}
          <article className="chapter-content whitespace-pre-wrap">
            {showSource ? reference.source_content : reference.translated_content}
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
 * Rule-based "Detected names" for a reference (deterministic spaCy NER, no LLM). References
 * are English, so each name IS an English surface form; promoting adds it to the glossary as
 * a `candidate` in one click. A chip has two actions, both writing to the glossary:
 *   • "+"  = promote → create a glossary entry as `candidate` (approve later).
 *   • "✕"  = reject  → create a glossary entry as `rejected` (soft-delete; restorable).
 * Any surface form already in the glossary (any status) is filtered out, so we fetch the
 * glossary on load to know which chips to hide.
 */
function DetectedNames({
  projectId,
  reference,
  onGlossaryChanged,
  onReferenceUpdated,
}: {
  projectId: string;
  reference: ReferenceChapter;
  onGlossaryChanged?: () => void;
  onReferenceUpdated: (ref: ReferenceChapter) => void;
}) {
  const [inGlossary, setInGlossary] = useState<Set<string>>(new Set());
  const [collapsed, setCollapsed] = useState(true);

  useEffect(() => {
    let active = true;
    getStorage()
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
  }, [projectId, reference.id]);

  const hidden = (t: string) => inGlossary.has(t.toLowerCase());
  const detected = (reference.detected_names ?? []).filter((t) => !hidden(t));

  if (detected.length === 0) {
    return (
      <div className="mb-6 rounded-lg border border-dashed bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
        <Sparkles className="mr-1.5 inline size-3.5" />
        No detected names. Use “Redetect names” to re-run the offline detector.
      </div>
    );
  }

  // Resolve a suggestion into the glossary (promote=candidate / reject=rejected) and remove
  // it from the reference's detected pool so it leaves the chips for good.
  async function resolve(term: string, status: "candidate" | "rejected") {
    const en = term.trim();
    if (!en) return;
    try {
      await getStorage().createGlossary(projectId, { surface_form: en, status });
      const updated = await getStorage().resolveReferenceTerm(reference.id, en);
      onReferenceUpdated(updated);
      onGlossaryChanged?.();
      toast.success(
        status === "candidate" ? `Added “${en}” to the glossary` : `Rejected “${en}” (restore it from the Glossary tab)`
      );
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not resolve term");
    }
  }

  const promote = (term: string) => resolve(term, "candidate");
  const reject = (term: string) => resolve(term, "rejected");

  return (
    <section className="mb-4 space-y-2 rounded-lg border bg-muted/20 p-3">
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        className="flex w-full cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-left transition-colors hover:bg-muted/50 hover:text-foreground"
      >
        {collapsed ? (
          <ChevronRight className="size-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="size-4 text-muted-foreground" />
        )}

        <span className="text-xs font-medium text-foreground">Detected names</span>

        <Badge variant="secondary" className="h-5 px-2 text-[10px]">
          {detected.length}
        </Badge>
      </button>
      {!collapsed && (
        <ul className="flex flex-wrap gap-1.5">
          {detected.map((term) => (
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
          ))}
        </ul>
      )}
    </section>
  );
}
