import { BookMarked, ChevronLeft, ChevronRight, Moon, Plus, Sun, Trash2, Pencil } from "lucide-react";
import { useEffect, useState } from "react";

import type { Project, ProjectCreate, SourceLang } from "@/api/types";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { DataManager } from "@/components/data-manager";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { Theme } from "@/hooks/use-theme";
import { langLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ModelPicker } from "./model-picker";

interface ProjectSidebarProps {
  projects: Project[];
  activeId: string | null;
  loading: boolean;
  theme: Theme;
  onToggleTheme: () => void;
  onSelect: (id: string) => void;
  onCreate: (body: ProjectCreate) => Promise<Project>;
  onUpdate: (id: string, body: ProjectCreate) => Promise<Project>;
  onDelete: (id: string) => Promise<void>;
}

const SIDEBAR_STORAGE_KEY = "novelbridge-sidebar-collapsed";

export function ProjectSidebar({
  projects,
  activeId,
  loading,
  theme,
  onToggleTheme,
  onSelect,
  onCreate,
  onUpdate,
  onDelete,
}: ProjectSidebarProps) {
  const [adding, setAdding] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [name, setName] = useState("");
  const [lang, setLang] = useState<SourceLang>("zh");
  const [submitting, setSubmitting] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Project | null>(null);
  const [collapsed, setCollapsed] = useState(() => {
    return localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true";
  });
  const isExpanded = !collapsed;

  useEffect(() => {
    localStorage.setItem(SIDEBAR_STORAGE_KEY, String(collapsed));
  }, [collapsed]);

  async function submitNew(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;

    try {
      setSubmitting(true);
      if (editingProject) {
        await onUpdate(editingProject.id, {
          name: trimmed,
          source_lang: lang,
        });
        setEditingProject(null);
        setAdding(false);
      } else {
        const project = await onCreate({
          name: trimmed,
          source_lang: lang,
        });
        onSelect(project.id);
        setAdding(false);
      }
      setName("");
      setLang("zh");
    } catch {
      // Error already surfaced via useProjects toast.
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <aside
      className={cn(
        "flex h-full shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground transition-all duration-200",
        collapsed ? "w-16" : "w-72"
      )}
    >
      {/* Wordmark */}
      <div className="flex items-center justify-between px-4 pt-5 pb-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="grid size-8 shrink-0 place-items-center rounded-md bg-foreground text-background">
            <BookMarked className="size-4" />
          </div>

          <div
            className={cn(
              "overflow-hidden transition-all duration-200",
              isExpanded ? "max-w-[180px] opacity-100" : "max-w-0 opacity-0"
            )}
          >
            <div className="leading-tight whitespace-nowrap">
              <div className="font-heading text-lg font-semibold tracking-tight">NovelBridge</div>
              <div className="text-[11px] text-muted-foreground">context-aware translation</div>
            </div>
          </div>
        </div>

        {isExpanded && (
          <Button
            size="icon-sm"
            variant="ghost"
            onClick={() => setCollapsed((v) => !v)}
            aria-label="Collapse sidebar"
            className="shrink-0"
          >
            <ChevronLeft />
          </Button>
        )}
      </div>

      {!isExpanded && (
        <div className="px-4 pb-3">
          <Button
            size="icon-sm"
            variant="ghost"
            onClick={() => setCollapsed(false)}
            aria-label="Expand sidebar"
            className="w-full"
          >
            <ChevronRight />
          </Button>
        </div>
      )}

      {isExpanded && (
        <div className="flex items-center justify-between px-5 pb-2">
          <span className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">Series</span>
          <Button
            size="icon-xs"
            variant="ghost"
            aria-label="New project"
            onClick={() => {
              if (adding) {
                setAdding(false);
                setEditingProject(null);
                setName("");
                setLang("zh");
                return;
              }
              setEditingProject(null);
              setName("");
              setLang("zh");
              setAdding(true);
            }}
            aria-expanded={adding}
          >
            <Plus className="transition-transform duration-200" />
          </Button>
        </div>
      )}

      {isExpanded && adding && (
        <form onSubmit={submitNew} className="mx-3 mb-2 space-y-2.5 rounded-lg border bg-background p-3">
          <div className="space-y-1.5">
            <Label htmlFor="new-project-name" className="text-xs">
              {editingProject ? "Edit series" : "Series name"}
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
                setEditingProject(null);
                setName("");
              }}
            >
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={!name.trim() || submitting}>
              {editingProject ? "Save" : "Create"}
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
          <p
            className={cn(
              "px-2 py-8 text-center text-sm text-muted-foreground",
              isExpanded ? "opacity-100" : "opacity-0"
            )}
          >
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
                    {isExpanded && (
                      <span
                        className={cn(
                          "absolute top-1/2 left-0 h-5 w-0.5 -translate-y-1/2 rounded-full bg-accent-brand transition-opacity duration-150",
                          active ? "opacity-100" : "opacity-0"
                        )}
                        aria-hidden
                      />
                    )}
                    {isExpanded ? (
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">{p.name}</div>
                        <div className="text-[11px] text-muted-foreground">{langLabel(p.source_lang)}</div>
                      </div>
                    ) : (
                      <div className="flex flex-1 justify-center">
                        <BookMarked className={cn("size-4", active ? "text-accent-brand" : "text-muted-foreground")} />
                      </div>
                    )}
                    {isExpanded && (
                      <div>
                        <Button
                          size="icon-xs"
                          variant="ghost"
                          aria-label={`Edit ${p.name}`}
                          className="cursor-pointer opacity-0 transition-opacity duration-150 group-hover/item:opacity-100 focus-visible:opacity-100"
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingProject(p);
                            setName(p.name);
                            setLang((p.source_lang as SourceLang) || "zh");
                            setAdding(true);
                          }}
                        >
                          <Pencil className="text-muted-foreground" />
                        </Button>
                        <Button
                          size="icon-xs"
                          variant="ghost"
                          aria-label={`Delete ${p.name}`}
                          className="cursor-pointer opacity-0 transition-opacity duration-150 group-hover/item:opacity-100 focus-visible:opacity-100"
                          onClick={(e) => {
                            e.stopPropagation();
                            setPendingDelete(p);
                          }}
                        >
                          <Trash2 className="text-muted-foreground" />
                        </Button>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </ScrollArea>

      {/* Footer */}
      <div className={cn("border-t p-3", !isExpanded && "flex flex-col items-center")}>
        <div className={cn(isExpanded ? "space-y-2" : "flex flex-col items-center gap-3")}>
          <div className={cn(isExpanded ? "min-w-0" : "")}>
            <ModelPicker compact={!isExpanded} />
          </div>

          <div
            className={cn(isExpanded ? "flex items-center justify-between gap-2" : "flex flex-col items-center gap-3")}
          >
            <DataManager compact={!isExpanded} />

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
