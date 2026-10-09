PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  source_lang   TEXT,
  created_at    TEXT NOT NULL,
  -- Per-project writing-style profile extracted from reference chapters or written by hand.
  -- Injected into every translation prompt to anchor register, rhythm, and terminology
  -- conventions across the whole series (the reference-summary pivot, task 3). NULL until
  -- the user extracts or writes a style. See engine.extract_style().
  style_profile TEXT
);

CREATE TABLE IF NOT EXISTS reference_chapters (
  id                  TEXT PRIMARY KEY,
  project_id          TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title               TEXT NOT NULL,
  translated_content  TEXT NOT NULL,
  source_content      TEXT NOT NULL,
  created_at          TEXT NOT NULL,
  -- Parsed from the title at upload (services/chapter_number.py); NULL when the title has
  -- no recognizable number (volume formats, prologues) — ordering then falls back to
  -- created_at and the UI can prompt for a manual value.
  chapter_number      INTEGER,
  -- Derived at upload time (task 13): a style/plot summary and a JSON array of
  -- candidate glossary terms. NULL until extraction has run.
  summary             TEXT,
  candidate_terms     TEXT,
  -- Rule-based proper-noun detections (field-fix #2), JSON array, kept separate from the
  -- AI candidate_terms. NULL until extraction has run.
  detected_names      TEXT
);

-- English-first glossary (task 14). References are English, so entries are keyed on the
-- English `surface_form`. `source_term` is optional (classic paired entries, or filled in
-- once a source<->translation match is confirmed). `status` drives the approve/reject
-- flow; `category`/`gender` steer the prompt (gender helps zh->en pronoun consistency).
CREATE TABLE IF NOT EXISTS glossary_entries (
  id           TEXT PRIMARY KEY,
  project_id   TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  surface_form TEXT NOT NULL,
  source_term  TEXT,
  status       TEXT NOT NULL DEFAULT 'candidate'
                 CHECK (status IN ('candidate','approved','rejected')),
  category     TEXT NOT NULL DEFAULT 'term'
                 CHECK (category IN ('character','title','term','location','organization','item')),
  gender       TEXT CHECK (gender IN ('male','female','unknown')),
  note         TEXT,
  created_at   TEXT NOT NULL,
  UNIQUE (project_id, surface_form COLLATE NOCASE)
);

CREATE TABLE IF NOT EXISTS translations (
  id          TEXT PRIMARY KEY,
  project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_lang TEXT NOT NULL,
  source_text    TEXT NOT NULL,
  translated_text TEXT NOT NULL,
  model_used  TEXT NOT NULL,
  created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_refs_project ON reference_chapters(project_id);
CREATE INDEX IF NOT EXISTS idx_glossary_project ON glossary_entries(project_id);
CREATE INDEX IF NOT EXISTS idx_translations_project ON translations(project_id);
