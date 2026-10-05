import { useCallback, useEffect, useState } from "react";
import { BookA, FileText, Languages } from "lucide-react";

import { api } from "@/api/client";
import type { ProjectDetail, SourceLang } from "@/api/types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { ReferencesTab } from "@/components/references-tab";
import { GlossaryTab } from "@/components/glossary-tab";
import { TranslateTab } from "@/components/translate-tab";
import { langLabel } from "@/lib/format";

type TabValue = "references" | "glossary" | "translate";
const TAB_KEY = (projectId: string) => `nb:tab:${projectId}`;

function loadTab(projectId: string): TabValue {
  try {
    const v = localStorage.getItem(TAB_KEY(projectId));
    if (v === "references" || v === "glossary" || v === "translate") return v;
  } catch {
    /* ignore */
  }
  return "translate";
}

export function ProjectWorkspace({ projectId }: { projectId: string }) {
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  // Controlled + persisted active tab so a refresh keeps the user on the same tab
  // (field feedback #5). Keyed per project.
  const [tab, setTab] = useState<TabValue>(() => loadTab(projectId));

  useEffect(() => {
    setTab(loadTab(projectId));
  }, [projectId]);

  function changeTab(v: string) {
    const next = v as TabValue;
    setTab(next);
    try {
      localStorage.setItem(TAB_KEY(projectId), next);
    } catch {
      /* ignore */
    }
  }

  const loadDetail = useCallback(async () => {
    const data = await api.getProject(projectId);
    setDetail(data);
    return data;
  }, [projectId]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setDetail(null);
    loadDetail()
      .catch(() => {})
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [loadDetail]);

  if (loading || !detail) {
    return <div className="flex h-full items-center justify-center text-sm text-muted-foreground">Loading series…</div>;
  }

  const { project, counts } = detail;
  const lang = (project.source_lang ?? "zh") as SourceLang;

  return (
    <div className="flex h-full flex-col">
      {/* Project header — asymmetric: title left, meta inline */}
      <header className="flex items-end justify-between gap-4 px-6 pt-6 pb-4">
        <div>
          <h1 className="font-heading text-3xl font-semibold tracking-tight">{project.name}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Translating from <span className="text-foreground">{langLabel(project.source_lang)}</span> to English
          </p>
        </div>
        <div className="hidden items-center gap-2 pb-1 sm:flex">
          <Badge variant="outline">{counts.references} refs</Badge>
          <Badge variant="outline">{counts.glossary} terms</Badge>
          <Badge variant="outline">{counts.translations} saved</Badge>
        </div>
      </header>

      <Tabs value={tab} onValueChange={changeTab} className="flex min-h-0 flex-1 flex-col gap-0">
        <div className="px-6">
          <TabsList>
            <TabsTrigger value="references" data-icon="inline-start">
              <FileText />
              References
            </TabsTrigger>
            <TabsTrigger value="glossary" data-icon="inline-start">
              <BookA />
              Glossary
            </TabsTrigger>
            <TabsTrigger value="translate" data-icon="inline-start">
              <Languages />
              Translate
            </TabsTrigger>
          </TabsList>
        </div>

        {/*
          forceMount keeps every tab mounted so switching tabs never unmounts the content.
          Essential for Translate: a live SSE stream (and the draft) must survive a tab
          switch (field feedback). Inactive tabs are hidden with CSS instead.
        */}
        <div className="mt-3 min-h-0 flex-1 border-t">
          <TabsContent value="references" forceMount className={cn("h-full", tab !== "references" && "hidden")}>
            <ReferencesTab key={`ref-${projectId}`} projectId={projectId} />
          </TabsContent>
          <TabsContent value="glossary" forceMount className={cn("h-full", tab !== "glossary" && "hidden")}>
            <GlossaryTab key={`glo-${projectId}`} projectId={projectId} />
          </TabsContent>
          <TabsContent value="translate" forceMount className={cn("h-full", tab !== "translate" && "hidden")}>
            <TranslateTab
              key={`tr-${projectId}`}
              projectId={projectId}
              defaultLang={lang}
              hasReferences={counts.references > 0}
              onSaved={() => void loadDetail()}
            />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
