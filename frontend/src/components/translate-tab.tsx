import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  AlertTriangle,
  ArrowDown,
  CheckCircle2,
  Clock,
  History,
  Info,
  Languages,
  Loader2,
  Pencil,
  Sparkles,
  Square,
} from "lucide-react";

import { api } from "@/api/client";
import { isContentEvent, isDoneEvent, isErrorEvent, isInfoEvent, type SourceLang, type Translation } from "@/api/types";
import { setStreaming } from "@/hooks/use-active-stream";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { HistoryPanel } from "@/components/history-panel";
import { langLabel } from "@/lib/format";

type Status = "idle" | "streaming" | "done" | "error" | "viewing";

// --- Draft persistence (field-fix #1) -------------------------------------
// The in-progress stream can't survive a refresh (live HTTP connection, no server-side
// resume), but the user's typed input should. We persist a per-project draft — the raw
// source, the chosen language, and any partial output — to localStorage, and restore it on
// mount. Cleared on a successful save or when the user starts a new translation.
interface Draft {
  raw: string;
  lang: SourceLang;
  output: string;
  // Whether `output` is a partial stream that was interrupted (refresh mid-translation).
  unfinished: boolean;
}

const draftKey = (projectId: string) => `nb:draft:${projectId}`;

function loadDraft(projectId: string): Draft | null {
  try {
    const raw = localStorage.getItem(draftKey(projectId));
    if (!raw) return null;
    const d = JSON.parse(raw) as Partial<Draft>;
    if (typeof d.raw !== "string") return null;
    return {
      raw: d.raw,
      lang: d.lang === "ja" ? "ja" : "zh",
      output: typeof d.output === "string" ? d.output : "",
      unfinished: !!d.unfinished,
    };
  } catch {
    return null;
  }
}

function saveDraft(projectId: string, draft: Draft) {
  try {
    // Nothing worth persisting -> clear instead of writing an empty draft.
    if (!draft.raw.trim() && !draft.output.trim()) {
      localStorage.removeItem(draftKey(projectId));
      return;
    }
    localStorage.setItem(draftKey(projectId), JSON.stringify(draft));
  } catch {
    /* storage full / unavailable — draft persistence is best-effort */
  }
}

function clearDraft(projectId: string) {
  try {
    localStorage.removeItem(draftKey(projectId));
  } catch {
    /* ignore */
  }
}

interface TranslateTabProps {
  projectId: string;
  defaultLang: SourceLang;
  hasReferences: boolean;
  onSaved?: () => void;
}

export function TranslateTab({ projectId, defaultLang, hasReferences, onSaved }: TranslateTabProps) {
  const [raw, setRaw] = useState("");
  const [output, setOutput] = useState("");
  const [lang, setLang] = useState<SourceLang>(defaultLang);
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [infoMsg, setInfoMsg] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyKey, setHistoryKey] = useState(0);
  const [viewingId, setViewingId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const outputScrollRef = useRef<HTMLDivElement | null>(null);
  // "Stick to bottom" autoscroll: only auto-follow the stream while the user is
  // pinned near the bottom. If they scroll up to read, stop following until they
  // return. `stickRef` is the live value the scroll effect reads; `atBottom`
  // drives the "jump to latest" affordance.
  const stickRef = useRef(true);
  const [atBottom, setAtBottom] = useState(true);

  // Reset the workspace when switching projects, restoring any saved draft so the user's
  // typed input (and any partial output) survives a refresh or a project switch.
  useEffect(() => {
    abortRef.current?.abort();
    const draft = loadDraft(projectId);
    if (draft) {
      setRaw(draft.raw);
      setOutput(draft.output);
      setLang(draft.lang);
      // A restored partial stream can't resume; show it as a recovered draft, and warn.
      setStatus(draft.output ? "error" : "idle");
      setErrorMsg(
        draft.unfinished && draft.output
          ? "This translation was interrupted (page reload). The partial result is restored below — press Translate to run it again."
          : null
      );
    } else {
      setRaw("");
      setOutput("");
      setStatus("idle");
      setErrorMsg(null);
      setLang(defaultLang);
    }
    setInfoMsg(null);
    setViewingId(null);
    setHistoryOpen(false);
  }, [projectId, defaultLang]);

  // Persist the draft as the user types / as output streams in. Debounced lightly via the
  // effect dependency list (React batches), good enough for a local-first app.
  useEffect(() => {
    // Don't persist while viewing a saved translation — that's not a draft.
    if (status === "viewing") return;
    saveDraft(projectId, { raw, lang, output, unfinished: status === "streaming" });
  }, [projectId, raw, lang, output, status]);

  // Publish streaming state app-wide so a project switch can be guarded (field-fix #1),
  // and warn on refresh/close while a stream is live. Clear the flag on unmount.
  useEffect(() => {
    const isStreaming = status === "streaming";
    setStreaming(isStreaming);
    if (!isStreaming) return;

    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = ""; // triggers the browser's native "Leave site?" prompt
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [status]);

  useEffect(() => () => setStreaming(false), []);

  // Track whether the user is pinned to the bottom of the output pane. When
  // they scroll up mid-stream we stop auto-following; when they come back to
  // the bottom we resume. Threshold tolerates sub-pixel/line rounding.
  const getViewport = () =>
    outputScrollRef.current?.querySelector<HTMLElement>("[data-radix-scroll-area-viewport]") ?? null;

  useEffect(() => {
    const el = getViewport();
    if (!el) return;
    const onScroll = () => {
      const stuck = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
      stickRef.current = stuck;
      setAtBottom(stuck);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  // Autoscroll as tokens arrive — but only while stuck to the bottom.
  useEffect(() => {
    if (!stickRef.current) return;
    const el = getViewport();
    if (el) el.scrollTop = el.scrollHeight;
  }, [output]);

  function jumpToLatest() {
    const el = getViewport();
    if (!el) return;
    const prefersReduced =
      typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollTo({ top: el.scrollHeight, behavior: prefersReduced ? "auto" : "smooth" });
    stickRef.current = true;
    setAtBottom(true);
  }

  useEffect(() => () => abortRef.current?.abort(), []);

  const streaming = status === "streaming";
  const viewing = status === "viewing";
  const canTranslate = raw.trim().length > 0 && !streaming;

  async function translate() {
    if (!canTranslate) return;
    const controller = new AbortController();
    abortRef.current = controller;

    setStatus("streaming");
    setOutput("");
    setErrorMsg(null);
    setInfoMsg(null);
    setViewingId(null);
    // Fresh stream: follow from the top down.
    stickRef.current = true;
    setAtBottom(true);

    try {
      const stream = api.translateStream(projectId, { raw_text: raw, source_lang: lang }, controller.signal);
      for await (const event of stream) {
        if (isContentEvent(event)) {
          setOutput((prev) => prev + event.content);
        } else if (isInfoEvent(event)) {
          setInfoMsg(event.info);
        } else if (isErrorEvent(event)) {
          // Engine failed mid-stream. Keep raw + whatever streamed so far.
          setStatus("error");
          setErrorMsg(event.error);
          toast.error("Translation failed");
          return;
        } else if (isDoneEvent(event)) {
          setStatus("done");
          setViewingId(event.translation_id);
          setHistoryKey((k) => k + 1);
          // Saved to history now — the draft is no longer needed.
          clearDraft(projectId);
          onSaved?.();
          toast.success("Translation saved");
          return;
        }
      }
      // Stream ended without an explicit done/error frame.
      if (!controller.signal.aborted) {
        setStatus((s) => (s === "streaming" ? "done" : s));
      }
    } catch (e) {
      if (controller.signal.aborted) return; // user stopped; not an error
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "Could not reach the translator");
      toast.error("Translation failed");
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
    setStatus(output ? "done" : "idle");
  }

  function loadSaved(t: Translation) {
    abortRef.current?.abort();
    setRaw(t.raw_text);
    setOutput(t.output_text);
    setLang(t.source_lang);
    setViewingId(t.id);
    setStatus("viewing");
    setErrorMsg(null);
    setInfoMsg(null);
  }

  function newTranslation() {
    setRaw("");
    setOutput("");
    setViewingId(null);
    setStatus("idle");
    setErrorMsg(null);
    clearDraft(projectId);
  }

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-6 py-3.5">
        <div className="flex items-center gap-3">
          <h2 className="font-heading text-xl font-semibold tracking-tight">Translate</h2>
          <StatusPill status={status} />
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5">
            <Languages className="size-4 text-muted-foreground" />
            <Select value={lang} onValueChange={(v) => setLang(v as SourceLang)} disabled={streaming}>
              <SelectTrigger size="sm" className="w-[7.5rem]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="zh">Chinese</SelectItem>
                <SelectItem value="ja">Japanese</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {streaming ? (
            <Button variant="outline" onClick={stop} data-icon="inline-start">
              <Square className="fill-current" />
              Stop
            </Button>
          ) : (
            <Button onClick={translate} disabled={!canTranslate} data-icon="inline-start">
              <Sparkles />
              Translate
            </Button>
          )}
          <Button
            variant={historyOpen ? "secondary" : "ghost"}
            size="icon"
            onClick={() => setHistoryOpen((v) => !v)}
            aria-label="Saved translations"
            aria-pressed={historyOpen}
            title="Saved translations"
          >
            <History />
          </Button>
        </div>
      </div>

      {/* Context notice */}
      {!hasReferences && (
        <div className="flex items-center gap-2 border-b bg-muted/40 px-6 py-2 text-xs text-muted-foreground">
          <Info className="size-3.5" />
          No reference chapters yet — translating without continuity context. Add references to improve consistency.
        </div>
      )}
      {infoMsg && (
        <div className="flex items-center gap-2 border-b bg-accent-brand/10 px-6 py-2 text-xs text-foreground">
          <AlertTriangle className="size-3.5 text-accent-brand" />
          {infoMsg}
        </div>
      )}

      {/* Viewing a saved translation (read-only) */}
      {viewing && (
        <div className="flex items-center justify-between gap-2 border-b bg-muted/40 px-6 py-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-2">
            <Clock className="size-3.5" />
            Viewing a saved translation
          </span>
          <Button size="xs" variant="ghost" onClick={newTranslation} data-icon="inline-start">
            <Pencil />
            New translation
          </Button>
        </div>
      )}

      {/* Error banner — raw text stays intact below */}
      {status === "error" && errorMsg && (
        <div
          role="alert"
          className="flex items-start gap-2 border-b border-destructive/30 bg-destructive/10 px-6 py-2.5 text-sm text-destructive"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <div>
            <span className="font-medium">{errorMsg}</span>
            <span className="text-destructive/80"> Your source text is preserved — adjust and try again.</span>
          </div>
        </div>
      )}

      {/* Panes + optional history panel */}
      <div className="flex min-h-0 flex-1">
        <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          {/* Source pane */}
          <section className="flex min-h-0 flex-col border-b lg:border-r lg:border-b-0">
            <PaneHeader label={`Source · ${langLabel(lang)}`} meta={`${raw.length.toLocaleString()} chars`} />
            <Textarea
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
              readOnly={viewing}
              placeholder={lang === "zh" ? "粘贴原文章节…" : "原文の章をここに貼り付け…"}
              spellCheck={false}
              className="min-h-0 flex-1 resize-none rounded-none border-0 bg-transparent px-6 py-5 font-sans text-[1.02rem] leading-[1.75] shadow-none focus-visible:ring-0"
            />
          </section>

          {/* Output pane */}
          <section className="relative flex min-h-0 flex-col bg-muted/20">
            <PaneHeader label="English" meta={outputMeta(status, output)} />
            {streaming && !atBottom && (
              <div className="pointer-events-none absolute inset-x-0 bottom-4 z-10 flex justify-center">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={jumpToLatest}
                  data-icon="inline-start"
                  className="pointer-events-auto shadow-md"
                >
                  <ArrowDown />
                  Jump to latest
                </Button>
              </div>
            )}
            <ScrollArea ref={outputScrollRef} className="min-h-0 flex-1">
              {output ? (
                <div className="px-6 py-5 font-sans text-[1.02rem] leading-[1.75] whitespace-pre-wrap">
                  {output}
                  {streaming && (
                    <span className="ml-0.5 inline-block h-[1.1em] w-[2px] translate-y-[0.15em] animate-pulse bg-accent-brand align-middle" />
                  )}
                </div>
              ) : (
                <div className="flex h-full flex-col items-center justify-center px-6 py-16 text-center text-sm text-muted-foreground">
                  {streaming ? (
                    <>
                      <Loader2 className="size-5 animate-spin text-accent-brand" />
                      <p className="mt-3">Translating…</p>
                    </>
                  ) : (
                    <>
                      <Languages className="size-5" />
                      <p className="mt-3 max-w-xs">The translation will stream in here, line by line.</p>
                    </>
                  )}
                </div>
              )}
            </ScrollArea>
          </section>
        </div>

        {historyOpen && (
          <HistoryPanel
            projectId={projectId}
            refreshKey={historyKey}
            activeId={viewingId}
            onClose={() => setHistoryOpen(false)}
            onSelect={loadSaved}
            onDeleted={(tid) => {
              // If the deleted translation is the one loaded in the panes,
              // reset to a fresh editor so we're not showing a stale save.
              if (tid === viewingId) newTranslation();
              // Keep the project's saved-translations count in sync.
              onSaved?.();
            }}
          />
        )}
      </div>
    </div>
  );
}

function PaneHeader({ label, meta }: { label: string; meta?: string }) {
  return (
    <div className="flex items-center justify-between border-b px-6 py-2.5">
      <span className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">{label}</span>
      {meta && <span className="text-[11px] text-muted-foreground/80">{meta}</span>}
    </div>
  );
}

function StatusPill({ status }: { status: Status }) {
  if (status === "streaming") {
    return (
      <Badge variant="secondary" className="gap-1 bg-accent-brand/15 text-accent-brand-foreground">
        <Loader2 className="size-3 animate-spin" />
        Streaming
      </Badge>
    );
  }
  if (status === "done") {
    return (
      <Badge variant="secondary" className="gap-1">
        <CheckCircle2 className="size-3 text-accent-brand" />
        Saved
      </Badge>
    );
  }
  if (status === "viewing") {
    return (
      <Badge variant="secondary" className="gap-1">
        <Clock className="size-3" />
        Saved
      </Badge>
    );
  }
  if (status === "error") {
    return (
      <Badge variant="secondary" className="gap-1 bg-destructive/10 text-destructive">
        <AlertTriangle className="size-3" />
        Failed
      </Badge>
    );
  }
  return null;
}

function outputMeta(status: Status, output: string): string | undefined {
  if (!output) return undefined;
  const chars = `${output.length.toLocaleString()} chars`;
  if (status === "done" || status === "viewing") return `${chars} · saved`;
  return chars;
}
