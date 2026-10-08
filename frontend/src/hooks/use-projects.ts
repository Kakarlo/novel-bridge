import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import type { Project, ProjectCreate } from "@/api/types";
import { getStorage } from "@/storage";

export function useProjects() {
  const storage = getStorage();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const data = await storage.listProjects();
      setProjects(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, [storage]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = useCallback(
    async (body: ProjectCreate): Promise<Project> => {
      try {
        const project = await storage.createProject(body);
        setProjects((prev) => [project, ...prev]);
        toast.success(`Created “${project.name}”`);
        return project;
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to create series";
        toast.error(message);
        throw error;
      }
    },
    [storage]
  );

  const update = useCallback(
    async (id: string, body: ProjectCreate): Promise<Project> => {
      try {
        const project = await storage.updateProject(id, body);
        setProjects((prev) => prev.map((p) => (p.id === id ? project : p)));
        toast.success(`Updated “${project.name}”`);
        return project;
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to create series";
        toast.error(message);
        throw error;
      }
    },
    [storage]
  );

  const remove = useCallback(
    async (id: string) => {
      await storage.deleteProject(id);
      setProjects((prev) => prev.filter((p) => p.id !== id));
      toast.success("Project deleted");
    },
    [storage]
  );

  return { projects, loading, error, refresh, create, update, remove };
}
