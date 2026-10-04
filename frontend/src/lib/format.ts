// Small formatting helpers shared across the UI.

const LANG_LABEL: Record<string, string> = {
  zh: "Chinese",
  ja: "Japanese",
};

export function langLabel(lang: string | null | undefined): string {
  if (!lang) return "—";
  return LANG_LABEL[lang] ?? lang;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function pluralize(n: number, singular: string, plural?: string): string {
  const word = n === 1 ? singular : (plural ?? `${singular}s`);
  return `${n} ${word}`;
}
