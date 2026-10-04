import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { BookA, Check, Pencil, Plus, Trash2, X } from "lucide-react";

import { api, ApiError } from "@/api/client";
import type { GlossaryEntry } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";

export function GlossaryTab({ projectId }: { projectId: string }) {
  const [entries, setEntries] = useState<GlossaryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<GlossaryEntry | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setAdding(false);
    setEditingId(null);
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

  async function handleCreate(source_term: string, translation: string, note: string) {
    const existing = entries.find((e) => e.source_term.toLowerCase() === source_term.toLowerCase());
    const entry = await api.createGlossary(projectId, {
      source_term,
      translation,
      note: note || null,
    });
    upsertLocal(entry);
    toast.success(existing ? "Entry updated (term already existed)" : "Term added");
    setAdding(false);
  }

  async function handleUpdate(id: string, translation: string, note: string) {
    const entry = await api.updateGlossary(id, {
      translation,
      note: note || null,
    });
    upsertLocal(entry);
    toast.success("Entry updated");
    setEditingId(null);
  }

  async function handleDelete(entry: GlossaryEntry) {
    await api.deleteGlossary(entry.id);
    setEntries((prev) => prev.filter((e) => e.id !== entry.id));
    toast.success("Entry removed");
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-4 border-b px-6 py-4">
        <div>
          <h2 className="font-heading text-xl font-semibold tracking-tight">Glossary</h2>
          <p className="text-sm text-muted-foreground">
            Authoritative names and terms. The model is told to follow these exactly.
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
          Add term
        </Button>
      </div>

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
          body="Lock in character names, titles, and recurring terminology so they stay consistent across chapters."
          action={
            <Button variant="outline" onClick={() => setAdding(true)}>
              Add your first term
            </Button>
          }
        />
      ) : (
        <ScrollArea className="min-h-0 flex-1">
          <div className="p-4">
            {/* column header */}
            <div className="grid grid-cols-[1fr_1fr_auto] gap-3 px-2 pb-2 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
              <span>Source term</span>
              <span>Translation</span>
              <span className="w-16 text-right">Actions</span>
            </div>

            {adding && <GlossaryEditor mode="create" onCancel={() => setAdding(false)} onSubmitCreate={handleCreate} />}

            <ul className="space-y-1">
              {entries.map((entry) =>
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
                    className="group/row grid grid-cols-[1fr_1fr_auto] items-start gap-3 rounded-lg px-2 py-2.5 transition-colors duration-150 hover:bg-muted/50"
                  >
                    <div className="min-w-0">
                      <div className="truncate font-medium">{entry.source_term}</div>
                      {entry.note && <div className="mt-0.5 truncate text-xs text-muted-foreground">{entry.note}</div>}
                    </div>
                    <div className="min-w-0 truncate pt-0.5">{entry.translation}</div>
                    <div className="flex w-16 justify-end gap-0.5 opacity-0 transition-opacity duration-150 group-hover/row:opacity-100 focus-within:opacity-100">
                      <Button
                        size="icon-xs"
                        variant="ghost"
                        aria-label={`Edit ${entry.source_term}`}
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
                        aria-label={`Delete ${entry.source_term}`}
                        onClick={() => setPendingDelete(entry)}
                      >
                        <Trash2 className="text-muted-foreground" />
                      </Button>
                    </div>
                  </li>
                )
              )}
            </ul>
          </div>
        </ScrollArea>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title="Delete this term?"
        description={
          <>
            <span className="font-medium text-foreground">{pendingDelete?.source_term}</span> will be removed from the
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

interface GlossaryEditorProps {
  mode: "create" | "edit";
  entry?: GlossaryEntry;
  onCancel: () => void;
  onSubmitCreate?: (source_term: string, translation: string, note: string) => Promise<void>;
  onSubmitUpdate?: (id: string, translation: string, note: string) => Promise<void>;
}

function GlossaryEditor({ mode, entry, onCancel, onSubmitCreate, onSubmitUpdate }: GlossaryEditorProps) {
  const [sourceTerm, setSourceTerm] = useState(entry?.source_term ?? "");
  const [translation, setTranslation] = useState(entry?.translation ?? "");
  const [note, setNote] = useState(entry?.note ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [touched, setTouched] = useState(false);

  const invalid = useMemo(() => !sourceTerm.trim() || !translation.trim(), [sourceTerm, translation]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (invalid) return;
    try {
      setSubmitting(true);
      if (mode === "create") {
        await onSubmitCreate?.(sourceTerm.trim(), translation.trim(), note.trim());
      } else if (entry) {
        await onSubmitUpdate?.(entry.id, translation.trim(), note.trim());
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Save failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="my-1 grid grid-cols-[1fr_1fr_auto] items-start gap-3 rounded-lg border bg-background p-2.5"
    >
      <div className="space-y-1.5">
        <Input
          autoFocus={mode === "create"}
          value={sourceTerm}
          onChange={(e) => setSourceTerm(e.target.value)}
          placeholder="源术语 / 用語"
          className="h-8"
          disabled={mode === "edit"}
          aria-invalid={touched && !sourceTerm.trim()}
          aria-label="Source term"
        />
        <Input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Optional note (e.g. male, formal register)"
          className="h-8 text-xs"
          aria-label="Note"
        />
        {mode === "edit" && (
          <p className="px-0.5 text-[11px] text-muted-foreground">
            Source term is fixed; create a new entry to change it.
          </p>
        )}
      </div>

      <Input
        value={translation}
        onChange={(e) => setTranslation(e.target.value)}
        placeholder="English translation"
        className="h-8"
        aria-invalid={touched && !translation.trim()}
        aria-label="Translation"
      />

      <div className="flex w-16 justify-end gap-0.5">
        <Button type="submit" size="icon-xs" disabled={submitting} aria-label="Save">
          <Check />
        </Button>
        <Button type="button" size="icon-xs" variant="ghost" onClick={onCancel} aria-label="Cancel">
          <X />
        </Button>
      </div>
    </form>
  );
}

function sortEntries(list: GlossaryEntry[]): GlossaryEntry[] {
  return [...list].sort((a, b) =>
    a.source_term.localeCompare(b.source_term, undefined, {
      sensitivity: "base",
    })
  );
}
