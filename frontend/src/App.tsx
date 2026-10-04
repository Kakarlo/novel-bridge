import { useEffect, useState } from "react";
import { BookOpen } from "lucide-react";

import { Toaster } from "@/components/ui/sonner";
import { ProjectSidebar } from "@/components/project-sidebar";
import { ProjectWorkspace } from "@/components/project-workspace";
import { useProjects } from "@/hooks/use-projects";

function App() {
  const { projects, loading, error, create, remove } = useProjects();
  const [activeId, setActiveId] = useState<string | null>(null);

  // Auto-select the first project once loaded, and keep selection valid
  // after deletes.
  useEffect(() => {
    if (loading) return;
    if (activeId && projects.some((p) => p.id === activeId)) return;
    setActiveId(projects[0]?.id ?? null);
  }, [projects, loading, activeId]);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <ProjectSidebar
        projects={projects}
        activeId={activeId}
        loading={loading}
        onSelect={setActiveId}
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

      <Toaster position="bottom-right" />
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
