// Client-side term occurrence detection (task 23.4d) — a faithful TS port of the backend's
// services/term_match.py. Powers the in-context review loop on the IndexedDB backend, where
// the browser owns the translation and there's no server to call.
//
// Decision (23.4d): term_match is pure stdlib string/regex work with no NLP deps, so it moves
// client-side as plain TS. The spaCy-dependent passes (pronoun/source-term) stay backend
// compute endpoints. This never rewrites the translation — detection only; the glossary is a
// guide. Exact whole-word, case-insensitive; multi-word surface forms match as a whole phrase
// with flexible internal whitespace (a newline between words still matches).

import type { GlossaryEntry, TermMatch } from "@/api/types";

const SNIPPET_RADIUS = 40;
const MAX_SNIPPETS = 3;

// Escape regex-special chars in a single token (equivalent to Python's re.escape for our use).
function escapeRegExp(tok: string): string {
  return tok.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Compile a whole-word, case-insensitive pattern for one surface form, or null when there's
// nothing matchable (all whitespace). Lookarounds give whole-word boundaries that also work
// for multi-word phrases ("Lin" must not match inside "Linda").
function buildPattern(surfaceForm: string): RegExp | null {
  const term = surfaceForm.trim();
  if (!term) return null;
  const tokens = term.split(/\s+/).filter(Boolean).map(escapeRegExp);
  if (tokens.length === 0) return null;
  const core = tokens.join("\\s+");
  return new RegExp(`(?<!\\w)(?:${core})(?!\\w)`, "giu");
}

function snippetsFor(text: string, pattern: RegExp): { count: number; snippets: string[] } {
  let count = 0;
  const snippets: string[] = [];
  for (const m of text.matchAll(pattern)) {
    count += 1;
    if (snippets.length < MAX_SNIPPETS) {
      const idx = m.index ?? 0;
      const start = Math.max(0, idx - SNIPPET_RADIUS);
      const end = Math.min(text.length, idx + m[0].length + SNIPPET_RADIUS);
      const prefix = start > 0 ? "…" : "";
      const suffix = end < text.length ? "…" : "";
      const window = prefix + text.slice(start, end).trim() + suffix;
      snippets.push(window.split(/\s+/).join(" ")); // collapse internal whitespace
    }
  }
  return { count, snippets };
}

/**
 * Find whole-word, case-insensitive occurrences of each glossary term in `outputText`.
 * Returns one TermMatch per term that appears at least once, most frequent first (ties keep
 * input order). Pure and offline — mirrors the backend's find_occurrences.
 */
export function findOccurrences(outputText: string, terms: GlossaryEntry[]): TermMatch[] {
  if (!outputText) return [];

  const matches: TermMatch[] = [];
  const seen = new Set<string>();
  for (const term of terms) {
    const key = term.surface_form.trim().toLowerCase();
    if (!key || seen.has(key)) continue; // skip blanks + duplicate surface forms
    seen.add(key);

    const pattern = buildPattern(term.surface_form);
    if (pattern === null) continue;
    const { count, snippets } = snippetsFor(outputText, pattern);
    if (count === 0) continue;
    matches.push({
      term_id: term.id,
      surface_form: term.surface_form,
      status: term.status,
      category: term.category,
      count,
      snippets,
    });
  }

  // Stable sort by count desc (Array.prototype.sort is stable in modern engines, so ties keep
  // insertion order — matching the Python contract).
  matches.sort((a, b) => b.count - a.count);
  return matches;
}
