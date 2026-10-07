import { Download, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getStorage, getStorageBackend, type ExportBundle } from "@/storage";

/**
 * Backup / restore / merge for the browser-local store (design-local-first-storage.md step 3).
 *
 * Export reads every record and serializes to a JSON file (the portable, mergeable format from
 * design §4). Import parses a bundle and writes it in one of two modes:
 *   • replace — wipe the local store, then load the file (a restore).
 *   • merge   — upsert by id; the glossary additionally dedupes on surface_form, so importing
 *               someone else's glossary combines cleanly ("share a glossary").
 *
 * Only shown with the IndexedDB backend — these operate on the local store (the API backend
 * can't materialize a cross-table bundle, by design).
 */

export function DataManager({ compact = false }: { compact?: boolean }) {
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [pending, setPending] = useState<ExportBundle | null>(null);
  const [busy, setBusy] = useState(false);

  // Export/import only make sense for the local browser store.
  if (getStorageBackend() !== "idb") return null;

  async function doExport() {
    try {
      const bundle = await getStorage().exportAll();
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `novelbridge-backup-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      const n = bundle.projects.length;
      toast.success(`Exported ${n} series`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  }

  async function onFilePicked(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-picking the same file
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text()) as ExportBundle;
      if (parsed?.format !== "novelbridge-export") {
        toast.error("That file isn't a NovelBridge backup.");
        return;
      }
      setPending(parsed); // open the replace/merge chooser
    } catch {
      toast.error("Couldn't read that file as JSON.");
    }
  }

  async function runImport(mode: "merge" | "replace") {
    if (!pending) return;
    try {
      setBusy(true);
      await getStorage().importAll(pending, mode);
      toast.success(mode === "replace" ? "Backup restored" : "Backup merged");
      // The whole app reads from the store on mount — reload so every view reflects the
      // imported data cleanly, rather than threading a refresh through every component.
      window.location.reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Import failed");
      setBusy(false);
      setPending(null);
    }
  }

  if (compact) {
    return (
      <>
        <Button size="icon-sm" variant="ghost" onClick={doExport} title="Export a backup (JSON)">
          <Download />
        </Button>

        <Button size="icon-sm" variant="ghost" onClick={() => fileInput.current?.click()} title="Import a backup (JSON)">
          <Upload />
        </Button>

        <input ref={fileInput} type="file" accept="application/json,.json" className="hidden"  onChange={onFilePicked} />

        <Dialog open={pending !== null} onOpenChange={(o) => !busy && !o && setPending(null)}>
          <DialogContent showCloseButton={false}>
            <DialogHeader>
              <DialogTitle>Import this backup?</DialogTitle>
              <DialogDescription>
                {pending && (
                  <>
                    {pending.projects?.length ?? 0} series, {pending.glossary?.length ?? 0} glossary entries,{" "}
                    {pending.translations?.length ?? 0} translations.
                    <br />
                    <span className="text-foreground">Merge</span> adds to what you have (deduping glossary names).{" "}
                    <span className="text-foreground">Replace</span> wipes the local store first.
                  </>
                )}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setPending(null)} disabled={busy}>
                Cancel
              </Button>
              <Button variant="destructive" onClick={() => runImport("replace")} disabled={busy}>
                Replace
              </Button>
              <Button onClick={() => runImport("merge")} disabled={busy}>
                Merge
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </>
    );
  }

  return (
    <div className="flex items-center gap-1">
      <Button size="xs" variant="outline" onClick={doExport} data-icon="inline-start" title="Export a backup (JSON)">
        <Download />
        Export
      </Button>
      <Button
        size="xs"
        variant="outline"
        onClick={() => fileInput.current?.click()}
        data-icon="inline-start"
        title="Import a backup (JSON)"
      >
        <Upload />
        Import
      </Button>
      <input ref={fileInput} type="file" accept="application/json,.json" className="hidden" onChange={onFilePicked} />

      <Dialog open={pending !== null} onOpenChange={(o) => !busy && !o && setPending(null)}>
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>Import this backup?</DialogTitle>
            <DialogDescription>
              {pending && (
                <>
                  {pending.projects?.length ?? 0} series, {pending.glossary?.length ?? 0} glossary entries,{" "}
                  {pending.translations?.length ?? 0} translations.
                  <br />
                  <span className="text-foreground">Merge</span> adds to what you have (deduping glossary names).{" "}
                  <span className="text-foreground">Replace</span> wipes the local store first.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPending(null)} disabled={busy}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => runImport("replace")} disabled={busy}>
              Replace
            </Button>
            <Button onClick={() => runImport("merge")} disabled={busy}>
              Merge
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
