import { useEffect, useState } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/api/client";
import type { GlossaryExtractionContent, GlossaryPairSuggestion, ReferenceChapter, SourceLang } from "@/api/types";
import { getStorage, getStorageBackend } from "@/storage";
import { GlossaryPairReview } from "./glossary-pair-review";

interface ReferenceReviewProps {
  projectId: string;
  reference: ReferenceChapter;
  sourceLang: SourceLang | null;
  onGlossaryChanged?: () => void;
}

export function ReferenceReview({ projectId, reference, sourceLang, onGlossaryChanged }: ReferenceReviewProps) {
  const [pairs, setPairs] = useState<GlossaryPairSuggestion[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [extracted, setExtracted] = useState(false);
  const pairKey = (c: GlossaryPairSuggestion) => `${c.source_term}→${c.surface_form}`;

  useEffect(() => {
    let active = true;
    setPairs([]);
    setExtracted(false);

    void getStorage()
      .getGlossaryExtractionRun("reference", reference.id)
      .then((run) => {
        if (!active || !run) return;

        setPairs(run.suggestions);
        setExtracted(true);
      })
      .catch(() => {
        /* no saved extraction */
      });
    return () => {
      active = false;
    };
  }, [reference.id]);

  async function suggestPairs() {
    setExtracting(true);

    try {
      let texts: GlossaryExtractionContent | undefined;

      if (getStorageBackend() === "idb") {
        texts = {
          source_text: reference.source_content ?? "",
          translated_text: reference.translated_content,
          source_lang: sourceLang ?? "zh",
        };
      }

      const result = await api.referenceExtractGlossary(reference.id, texts);
      setPairs(result);
      setExtracted(true);
      await getStorage().saveGlossaryExtractionRun({
        id: crypto.randomUUID(),
        project_id: projectId,
        source: "reference",
        source_id: reference.id,
        created_at: new Date().toISOString(),
        suggestions: result,
      });
      if (result.length === 0) {
        toast.info("No new pairings found");
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not extract glossary pairs");
    } finally {
      setExtracting(false);
    }
  }

  async function confirmPair(c: GlossaryPairSuggestion) {
    try {
      // Upsert on surface_form via the existing glossary write — no new endpoint. A paired
      // entry (source_term set) defaults to approved on the backend, so it steers the next
      // translation immediately. Carry the model's category/gender/note through.
      await getStorage().createGlossary(projectId, {
        surface_form: c.surface_form,
        source_term: c.source_term,
        category: c.category,
        status: "approved",
        gender: c.gender ?? undefined,
        note: c.note ?? undefined,
      });

      const updated = pairs.filter((p) => pairKey(p) !== pairKey(c));

      setPairs(updated);

      await getStorage().saveGlossaryExtractionRun({
        id: crypto.randomUUID(),
        project_id: projectId,
        source: "reference",
        source_id: reference.id,
        created_at: new Date().toISOString(),
        suggestions: updated,
      });
      onGlossaryChanged?.();
      toast.success(`Paired “${c.source_term}” → “${c.surface_form}”`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save the pairing");
    }
  }

  async function dismissPair(c: GlossaryPairSuggestion) {
    const updated = pairs.filter((p) => pairKey(p) !== pairKey(c));

    setPairs(updated);

    await getStorage().saveGlossaryExtractionRun({
      id: crypto.randomUUID(),
      project_id: projectId,
      source: "reference",
      source_id: reference.id,
      created_at: new Date().toISOString(),
      suggestions: updated,
    });
  }

  return (
    <section className="mb-4 max-h-38 overflow-y-auto rounded-lg border bg-muted/20 p-4">
      <GlossaryPairReview
        pairs={pairs}
        extracting={extracting}
        extracted={extracted}
        hint="paired by the model from the reference source chapter and its English translation — confirm to add a glossary pairing, or dismiss"
        onExtract={suggestPairs}
        onConfirm={confirmPair}
        onDismiss={dismissPair}
      />
    </section>
  );
}
