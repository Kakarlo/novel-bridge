PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  source_lang TEXT,
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reference_chapters (
  id              TEXT PRIMARY KEY,
  project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title           TEXT NOT NULL,
  content         TEXT NOT NULL,
  created_at      TEXT NOT NULL,
  -- Derived at upload time (task 13): a style/plot summary and a JSON array of
  -- candidate glossary terms. NULL until extraction has run.
  summary         TEXT,
  candidate_terms TEXT
);

CREATE TABLE IF NOT EXISTS glossary_entries (
  id          TEXT PRIMARY KEY,
  project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_term TEXT NOT NULL,
  translation TEXT NOT NULL,
  note        TEXT,
  UNIQUE (project_id, source_term)
);

CREATE TABLE IF NOT EXISTS translations (
  id          TEXT PRIMARY KEY,
  project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_lang TEXT NOT NULL,
  raw_text    TEXT NOT NULL,
  output_text TEXT NOT NULL,
  model_used  TEXT NOT NULL,
  created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_refs_project ON reference_chapters(project_id);
CREATE INDEX IF NOT EXISTS idx_glossary_project ON glossary_entries(project_id);
CREATE INDEX IF NOT EXISTS idx_translations_project ON translations(project_id);
