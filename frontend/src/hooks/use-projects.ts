import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { api } from "@/api/client";
import type { Project, ProjectCreate } from "@/api/types";

export function useProjects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const data = await api.listProjects();
      setProjects(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = useCallback(async (body: ProjectCreate): Promise<Project> => {
    const project = await api.createProject(body);
    setProjects((prev) => [project, ...prev]);
    toast.success(`Created “${project.name}”`);
    return project;
  }, []);

  const remove = useCallback(async (id: string) => {
    await api.deleteProject(id);
    setProjects((prev) => prev.filter((p) => p.id !== id));
    toast.success("Project deleted");
  }, []);

  return { projects, loading, error, refresh, create, remove };
}
