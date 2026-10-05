import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { BookA, Check, Pencil, Plus, ThumbsDown, ThumbsUp, Trash2, X } from "lucide-react";

import { api, ApiError } from "@/api/client";
import type { Gender, GlossaryCategory, GlossaryEntry, GlossaryStatus } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { cn } from "@/lib/utils";

type StatusFilter = "all" | GlossaryStatus;

const CATEGORY_LABELS: Record<GlossaryCategory, string> = {
  character: "Character",
  title: "Title",
  term: "Term",
};

export function GlossaryTab({ projectId }: { projectId: string }) {
  const [entries, setEntries] = useState<GlossaryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<GlossaryEntry | null>(null);
  const [filter, setFilter] = useState<StatusFilter>("all");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setAdding(false);
    setEditingId(null);
    setFilter("all");
    api
      .listGlossary(projectId)
      .then((data) => active && setEntries(sortEntries(data)))
      .catch((e) => active && toast.error(e instanceof Error ? e.message : "Load failed"))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [projectId]);

  function upsertLocal(entry: GlossaryEntry) {
    setEntries((prev) => {
      const exists = prev.some((e) => e.id === entry.id);
      const next = exists ? prev.map((e) => (e.id === entry.id ? entry : e)) : [...prev, entry];
      return sortEntries(next);
    });
  }

  async function handleCreate(draft: EditorDraft) {
    const entry = await api.createGlossary(projectId, {
      surface_form: draft.surfaceForm,
      source_term: draft.sourceTerm || null,
      category: draft.category,
      gender: draft.category === "character" ? draft.gender : null,
      note: draft.note || null,
    });
    upsertLocal(entry);
    toast.success("Term added");
    setAdding(false);
  }

  async function handleUpdate(id: string, draft: EditorDraft) {
    const entry = await api.updateGlossary(id, {
      surface_form: draft.surfaceForm,
      category: draft.category,
      gender: draft.category === "character" ? draft.gender : null,
      note: draft.note || null,
    });
    upsertLocal(entry);
    toast.success("Entry updated");
    setEditingId(null);
  }

  async function handleStatus(entry: GlossaryEntry, status: GlossaryStatus) {
    try {
      const updated = await api.setGlossaryStatus(entry.id, status);
      upsertLocal(updated);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not update status");
    }
  }

  async function handleDelete(entry: GlossaryEntry) {
    await api.deleteGlossary(entry.id);
    setEntries((prev) => prev.filter((e) => e.id !== entry.id));
    toast.success("Entry removed");
  }

  const counts = useMemo(() => {
    const c = { all: entries.length, candidate: 0, approved: 0, rejected: 0 };
    for (const e of entries) c[e.status] += 1;
    return c;
  }, [entries]);

  const visible = useMemo(
    () => (filter === "all" ? entries : entries.filter((e) => e.status === filter)),
    [entries, filter]
  );

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-4 border-b px-6 py-4">
        <div>
          <h2 className="font-heading text-xl font-semibold tracking-tight">Glossary</h2>
          <p className="text-sm text-muted-foreground">
            English-first names and terms. Only <span className="text-foreground">approved</span> entries steer the
            model; approve candidates as you see them in translations.
          </p>
        </div>
        <Button
          onClick={() => {
            setAdding(true);
            setEditingId(null);
          }}
          disabled={adding}
          data-icon="inline-start"
        >
          <Plus />
          Add name
        </Button>
      </div>

      {/* Status filter */}
      {!loading && entries.length > 0 && (
        <div className="flex items-center gap-1.5 border-b px-6 py-2">
          {(["all", "candidate", "approved", "rejected"] as StatusFilter[]).map((f) => (
            <Button
              key={f}
              size="xs"
              variant={filter === f ? "secondary" : "ghost"}
              onClick={() => setFilter(f)}
              className="capitalize"
            >
              {f} ({counts[f]})
            </Button>
          ))}
        </div>
      )}

      {loading ? (
        <div className="space-y-2 p-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-12 animate-pulse rounded-lg bg-muted/60" />
          ))}
        </div>
      ) : entries.length === 0 && !adding ? (
        <EmptyState
          icon={BookA}
          title="No glossary terms"
          body="Add character names, titles, and recurring terminology by their English name so they stay consistent across chapters."
          action={
            <Button variant="outline" onClick={() => setAdding(true)}>
              Add your first name
            </Button>
          }
        />
      ) : (
        <ScrollArea className="min-h-0 flex-1">
          <div className="p-4">
            {adding && <GlossaryEditor mode="create" onCancel={() => setAdding(false)} onSubmitCreate={handleCreate} />}

            {visible.length === 0 && !adding ? (
              <p className="px-2 py-8 text-center text-sm text-muted-foreground">No {filter} terms.</p>
            ) : (
              <ul className="space-y-1">
                {visible.map((entry) =>
                  editingId === entry.id ? (
                    <li key={entry.id}>
                      <GlossaryEditor
                        mode="edit"
                        entry={entry}
                        onCancel={() => setEditingId(null)}
                        onSubmitUpdate={handleUpdate}
                      />
                    </li>
                  ) : (
                    <li
                      key={entry.id}
                      className="group/row flex items-start justify-between gap-3 rounded-lg px-2 py-2.5 transition-colors duration-150 hover:bg-muted/50"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="truncate font-medium">{entry.surface_form}</span>
                          <StatusBadge status={entry.status} />
                          <CategoryBadge entry={entry} />
                          {entry.source_term && (
                            <span className="text-xs text-muted-foreground">← {entry.source_term}</span>
                          )}
                        </div>
                        {entry.note && (
                          <div className="mt-0.5 truncate text-xs text-muted-foreground">{entry.note}</div>
                        )}
                      </div>

                      <div className="flex shrink-0 items-center gap-0.5">
                        {/* Approve / reject (hidden until hover/focus to keep rows calm) */}
                        <div className="flex gap-0.5 opacity-0 transition-opacity duration-150 group-hover/row:opacity-100 focus-within:opacity-100">
                          {entry.status !== "approved" && (
                            <Button
                              size="icon-xs"
                              variant="ghost"
                              aria-label={`Approve ${entry.surface_form}`}
                              title="Approve"
                              onClick={() => handleStatus(entry, "approved")}
                            >
                              <ThumbsUp className="text-emerald-600 dark:text-emerald-400" />
                            </Button>
                          )}
                          {entry.status !== "rejected" && (
                            <Button
                              size="icon-xs"
                              variant="ghost"
                              aria-label={`Reject ${entry.surface_form}`}
                              title="Reject"
                              onClick={() => handleStatus(entry, "rejected")}
                            >
                              <ThumbsDown className="text-muted-foreground" />
                            </Button>
                          )}
                          <Button
                            size="icon-xs"
                            variant="ghost"
                            aria-label={`Edit ${entry.surface_form}`}
                            onClick={() => {
                              setEditingId(entry.id);
                              setAdding(false);
                            }}
                          >
                            <Pencil />
                          </Button>
                          <Button
                            size="icon-xs"
                            variant="ghost"
                            aria-label={`Delete ${entry.surface_form}`}
                            onClick={() => setPendingDelete(entry)}
                          >
                            <Trash2 className="text-muted-foreground" />
                          </Button>
                        </div>
                      </div>
                    </li>
                  )
                )}
              </ul>
            )}
          </div>
        </ScrollArea>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title="Delete this term?"
        description={
          <>
            <span className="font-medium text-foreground">{pendingDelete?.surface_form}</span> will be removed from the
            glossary.
          </>
        }
        confirmLabel="Delete"
        destructive
        onConfirm={async () => {
          if (pendingDelete) await handleDelete(pendingDelete);
        }}
      />
    </div>
  );
}

function StatusBadge({ status }: { status: GlossaryStatus }) {
  const variant = status === "approved" ? "default" : status === "rejected" ? "destructive" : "secondary";
  return (
    <Badge variant={variant} className="capitalize">
      {status}
    </Badge>
  );
}

function CategoryBadge({ entry }: { entry: GlossaryEntry }) {
  const gender =
    entry.category === "character" && entry.gender && entry.gender !== "unknown" ? ` · ${entry.gender}` : "";
  return (
    <Badge variant="outline" className="font-normal">
      {CATEGORY_LABELS[entry.category]}
      {gender}
    </Badge>
  );
}

interface EditorDraft {
  surfaceForm: string;
  sourceTerm: string;
  category: GlossaryCategory;
  gender: Gender;
  note: string;
}

interface GlossaryEditorProps {
  mode: "create" | "edit";
  entry?: GlossaryEntry;
  onCancel: () => void;
  onSubmitCreate?: (draft: EditorDraft) => Promise<void>;
  onSubmitUpdate?: (id: string, draft: EditorDraft) => Promise<void>;
}

function GlossaryEditor({ mode, entry, onCancel, onSubmitCreate, onSubmitUpdate }: GlossaryEditorProps) {
  const [surfaceForm, setSurfaceForm] = useState(entry?.surface_form ?? "");
  const [sourceTerm, setSourceTerm] = useState(entry?.source_term ?? "");
  const [category, setCategory] = useState<GlossaryCategory>(entry?.category ?? "character");
  const [gender, setGender] = useState<Gender>(entry?.gender ?? "unknown");
  const [note, setNote] = useState(entry?.note ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [touched, setTouched] = useState(false);

  // English-first: only the English name is required. Source term is optional.
  const invalid = useMemo(() => !surfaceForm.trim(), [surfaceForm]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (invalid) return;
    const draft: EditorDraft = {
      surfaceForm: surfaceForm.trim(),
      sourceTerm: sourceTerm.trim(),
      category,
      gender,
      note: note.trim(),
    };
    try {
      setSubmitting(true);
      if (mode === "create") await onSubmitCreate?.(draft);
      else if (entry) await onSubmitUpdate?.(entry.id, draft);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Save failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="my-1 space-y-2.5 rounded-lg border bg-background p-3">
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        <div className="space-y-1">
          <label className="text-[11px] font-medium text-muted-foreground">English name *</label>
          <Input
            autoFocus={mode === "create"}
            value={surfaceForm}
            onChange={(e) => setSurfaceForm(e.target.value)}
            placeholder="e.g. Fang Yuan"
            className="h-8"
            aria-invalid={touched && !surfaceForm.trim()}
            aria-label="English name"
          />
        </div>
        <div className="space-y-1">
          <label className="text-[11px] font-medium text-muted-foreground">
            Source term <span className="font-normal">(optional)</span>
          </label>
          <Input
            value={sourceTerm}
            onChange={(e) => setSourceTerm(e.target.value)}
            placeholder="源术语 / 用語"
            className="h-8"
            disabled={mode === "edit"}
            aria-label="Source term (optional)"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        <div className="space-y-1">
          <label className="text-[11px] font-medium text-muted-foreground">Category</label>
          <Select value={category} onValueChange={(v) => setCategory(v as GlossaryCategory)}>
            <SelectTrigger size="sm" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="character">Character</SelectItem>
              <SelectItem value="title">Title</SelectItem>
              <SelectItem value="term">Term</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className={cn("space-y-1", category !== "character" && "opacity-50")}>
          <label className="text-[11px] font-medium text-muted-foreground">
            Gender <span className="font-normal">(characters)</span>
          </label>
          <Select value={gender} onValueChange={(v) => setGender(v as Gender)} disabled={category !== "character"}>
            <SelectTrigger size="sm" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="unknown">Unknown</SelectItem>
              <SelectItem value="male">Male</SelectItem>
              <SelectItem value="female">Female</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <Input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Optional note (e.g. formal register, cultivation sect leader)"
        className="h-8 text-xs"
        aria-label="Note"
      />

      {mode === "edit" && (
        <p className="text-[11px] text-muted-foreground">Source term is fixed; create a new entry to change it.</p>
      )}

      <div className="flex justify-end gap-1.5">
        <Button type="button" size="sm" variant="ghost" onClick={onCancel} data-icon="inline-start">
          <X />
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={submitting} data-icon="inline-start">
          <Check />
          {mode === "create" ? "Add" : "Save"}
        </Button>
      </div>
    </form>
  );
}

function sortEntries(list: GlossaryEntry[]): GlossaryEntry[] {
  return [...list].sort((a, b) =>
    a.surface_form.localeCompare(b.surface_form, undefined, {
      sensitivity: "base",
    })
  );
}
