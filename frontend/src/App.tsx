import { useEffect, useState } from "react";
import { BookOpen } from "lucide-react";

import { Toaster } from "@/components/ui/sonner";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { ProjectSidebar } from "@/components/project-sidebar";
import { ProjectWorkspace } from "@/components/project-workspace";
import { useProjects } from "@/hooks/use-projects";
import { useTheme } from "@/hooks/use-theme";
import { useIsStreaming } from "@/hooks/use-active-stream";

function App() {
  const { projects, loading, error, create, remove } = useProjects();
  const { theme, toggle: toggleTheme } = useTheme();
  const [activeId, setActiveId] = useState<string | null>(null);
  // A pending project switch awaiting confirmation because a translation is streaming
  // (field-fix #1). Switching projects unmounts the TranslateTab and drops the stream.
  const [pendingSwitch, setPendingSwitch] = useState<string | null>(null);
  const streaming = useIsStreaming();

  // Auto-select a project once loaded: prefer the last-selected one (persisted), else the
  // first. Keeps selection valid after deletes.
  useEffect(() => {
    if (loading) return;
    if (activeId && projects.some((p) => p.id === activeId)) return;
    let remembered: string | null = null;
    try {
      remembered = localStorage.getItem("nb:active-project");
    } catch {
      /* ignore */
    }
    const next = (remembered && projects.some((p) => p.id === remembered) ? remembered : projects[0]?.id) ?? null;
    setActiveId(next);
  }, [projects, loading, activeId]);

  // Persist the selected project so a refresh returns to it (field feedback #5).
  useEffect(() => {
    try {
      if (activeId) localStorage.setItem("nb:active-project", activeId);
    } catch {
      /* ignore */
    }
  }, [activeId]);

  // Guard a project switch while a translation is streaming: confirm first, since
  // leaving the current project stops the in-progress run (the draft input is preserved).
  function selectProject(id: string) {
    if (id === activeId) return;
    if (streaming) {
      setPendingSwitch(id);
      return;
    }
    setActiveId(id);
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <ProjectSidebar
        projects={projects}
        activeId={activeId}
        loading={loading}
        theme={theme}
        onToggleTheme={toggleTheme}
        onSelect={selectProject}
        onCreate={create}
        onDelete={async (id) => {
          await remove(id);
          if (id === activeId) setActiveId(null);
        }}
      />

      <main className="min-w-0 flex-1 overflow-hidden">
        {error ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
            <p className="text-sm font-medium text-destructive">{error}</p>
            <p className="max-w-sm text-sm text-muted-foreground">
              Make sure the backend is running on port 8000, then reload.
            </p>
          </div>
        ) : activeId ? (
          <ProjectWorkspace key={activeId} projectId={activeId} />
        ) : (
          <WelcomeState hasProjects={projects.length > 0} />
        )}
      </main>

      <Toaster position="bottom-right" theme={theme} />

      <ConfirmDialog
        open={pendingSwitch !== null}
        onOpenChange={(o) => !o && setPendingSwitch(null)}
        title="A translation is in progress"
        description="Switching series will stop the current translation (it can't be resumed). Your source text is saved as a draft. Continue?"
        confirmLabel="Switch series"
        destructive
        onConfirm={() => {
          if (pendingSwitch) setActiveId(pendingSwitch);
          setPendingSwitch(null);
        }}
      />
    </div>
  );
}

function WelcomeState({ hasProjects }: { hasProjects: boolean }) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="grid size-14 place-items-center rounded-2xl border bg-muted/40 text-muted-foreground">
        <BookOpen className="size-6" />
      </div>
      <h1 className="mt-5 font-heading text-2xl font-semibold tracking-tight">
        {hasProjects ? "Select a series" : "Welcome to NovelBridge"}
      </h1>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        {hasProjects
          ? "Choose a series from the left, or create a new one to continue a translation."
          : "Create a series in the sidebar to start translating chapters with a consistent glossary and reference voice."}
      </p>
    </div>
  );
}

export default App;
