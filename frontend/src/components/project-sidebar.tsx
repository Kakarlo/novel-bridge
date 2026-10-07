import { useState } from "react";
import { BookMarked, Moon, Plus, Sun, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { DataManager } from "@/components/data-manager";
import { cn } from "@/lib/utils";
import { langLabel } from "@/lib/format";
import type { Theme } from "@/hooks/use-theme";
import type { Project, ProjectCreate, SourceLang } from "@/api/types";
import { ModelPicker } from "./model-picker";

interface ProjectSidebarProps {
  projects: Project[];
  activeId: string | null;
  loading: boolean;
  theme: Theme;
  onToggleTheme: () => void;
  onSelect: (id: string) => void;
  onCreate: (body: ProjectCreate) => Promise<Project>;
  onDelete: (id: string) => Promise<void>;
}

export function ProjectSidebar({
  projects,
  activeId,
  loading,
  theme,
  onToggleTheme,
  onSelect,
  onCreate,
  onDelete,
}: ProjectSidebarProps) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [lang, setLang] = useState<SourceLang>("zh");
  const [submitting, setSubmitting] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Project | null>(null);

  async function submitNew(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    try {
      setSubmitting(true);
      const project = await onCreate({ name: trimmed, source_lang: lang });
      setName("");
      setLang("zh");
      setAdding(false);
      onSelect(project.id);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground">
      {/* Wordmark */}
      <div className="flex items-center gap-2.5 px-5 pt-5 pb-4">
        <div className="grid size-8 place-items-center rounded-md bg-foreground text-background">
          <BookMarked className="size-4" />
        </div>
        <div className="leading-tight">
          <div className="font-heading text-lg font-semibold tracking-tight">NovelBridge</div>
          <div className="text-[11px] text-muted-foreground">context-aware translation</div>
        </div>
      </div>

      <div className="flex items-center justify-between px-5 pb-2">
        <span className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">Series</span>
        <Button
          size="icon-xs"
          variant="ghost"
          aria-label="New project"
          onClick={() => setAdding((v) => !v)}
          aria-expanded={adding}
        >
          <Plus className="transition-transform duration-200" />
        </Button>
      </div>

      {adding && (
        <form onSubmit={submitNew} className="mx-3 mb-2 space-y-2.5 rounded-lg border bg-background p-3">
          <div className="space-y-1.5">
            <Label htmlFor="new-project-name" className="text-xs">
              Series name
            </Label>
            <Input
              id="new-project-name"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Reverend Insanity"
              className="h-8"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Source language</Label>
            <Select value={lang} onValueChange={(v) => setLang(v as SourceLang)}>
              <SelectTrigger size="sm" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="zh">Chinese</SelectItem>
                <SelectItem value="ja">Japanese</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex justify-end gap-2 pt-0.5">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => {
                setAdding(false);
                setName("");
              }}
            >
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={!name.trim() || submitting}>
              Create
            </Button>
          </div>
        </form>
      )}

      <ScrollArea className="min-h-0 flex-1 px-3">
        {loading ? (
          <div className="space-y-1.5 py-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded-lg bg-muted/60" />
            ))}
          </div>
        ) : projects.length === 0 ? (
          <p className="px-2 py-8 text-center text-sm text-muted-foreground">
            No series yet. Create one to start building its glossary and references.
          </p>
        ) : (
          <ul className="space-y-0.5 py-1">
            {projects.map((p) => {
              const active = p.id === activeId;
              return (
                <li key={p.id}>
                  <div
                    className={cn(
                      "group/item relative flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 transition-colors duration-150",
                      active ? "bg-sidebar-accent" : "hover:bg-sidebar-accent/60"
                    )}
                    onClick={() => onSelect(p.id)}
                  >
                    <span
                      className={cn(
                        "absolute top-1/2 left-0 h-5 w-0.5 -translate-y-1/2 rounded-full bg-accent-brand transition-opacity duration-150",
                        active ? "opacity-100" : "opacity-0"
                      )}
                      aria-hidden
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{p.name}</div>
                      <div className="text-[11px] text-muted-foreground">{langLabel(p.source_lang)}</div>
                    </div>
                    <Button
                      size="icon-xs"
                      variant="ghost"
                      aria-label={`Delete ${p.name}`}
                      className="opacity-0 transition-opacity duration-150 group-hover/item:opacity-100 focus-visible:opacity-100"
                      onClick={(e) => {
                        e.stopPropagation();
                        setPendingDelete(p);
                      }}
                    >
                      <Trash2 className="text-muted-foreground" />
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </ScrollArea>

      {/* Footer: engine/model health, then a bottom row of app actions (backup + theme). */}
      <div className="space-y-2 border-t p-3">
        <div className="min-w-0">
          <ModelPicker />
        </div>
        <div className="flex items-center justify-between gap-2">
          <DataManager />
          <Button
            size="icon-sm"
            variant="ghost"
            onClick={onToggleTheme}
            aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? <Sun /> : <Moon />}
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title="Delete this series?"
        description={
          <>
            <span className="font-medium text-foreground">{pendingDelete?.name}</span> and all its references, glossary
            entries, and saved translations will be permanently removed. This can’t be undone.
          </>
        }
        confirmLabel="Delete series"
        destructive
        onConfirm={async () => {
          if (pendingDelete) await onDelete(pendingDelete.id);
        }}
      />
    </aside>
  );
}
