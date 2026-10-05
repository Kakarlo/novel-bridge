"""SQLite implementation of StorageService."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.models import (
    GlossaryEntry,
    Project,
    ReferenceChapter,
    SourceLang,
    Translation,
    new_id,
    utcnow_iso,
)
from app.storage.base import StorageService

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class SQLiteStorage(StorageService):
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._init_db()

    # --- connection helpers ---
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self) -> None:
        schema = _SCHEMA_PATH.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(schema)
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Additive migrations for DBs created before newer columns existed."""
        cols = {
            r["name"]
            for r in conn.execute("PRAGMA table_info(reference_chapters)").fetchall()
        }
        if "summary" not in cols:
            conn.execute("ALTER TABLE reference_chapters ADD COLUMN summary TEXT")
        if "candidate_terms" not in cols:
            conn.execute(
                "ALTER TABLE reference_chapters ADD COLUMN candidate_terms TEXT"
            )
        if "detected_names" not in cols:
            conn.execute(
                "ALTER TABLE reference_chapters ADD COLUMN detected_names TEXT"
            )
        if "chapter_number" not in cols:
            conn.execute(
                "ALTER TABLE reference_chapters ADD COLUMN chapter_number INTEGER"
            )

    # --- projects ---
    def list_projects(self) -> list[Project]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY created_at DESC"
            ).fetchall()
        return [Project(**dict(r)) for r in rows]

    def create_project(self, name: str, source_lang: SourceLang | None) -> Project:
        proj = Project(
            id=new_id(), name=name, source_lang=source_lang, created_at=utcnow_iso()
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO projects (id, name, source_lang, created_at) VALUES (?,?,?,?)",
                (proj.id, proj.name, proj.source_lang, proj.created_at),
            )
        return proj

    def get_project(self, pid: str) -> Project | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return Project(**dict(row)) if row else None

    def delete_project(self, pid: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM projects WHERE id=?", (pid,))
        return cur.rowcount > 0

    # --- references ---
    @staticmethod
    def _load_json_list(value) -> list:
        try:
            parsed = json.loads(value) if value else []
        except (json.JSONDecodeError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []

    @classmethod
    def _row_to_reference(cls, row: sqlite3.Row) -> ReferenceChapter:
        data = dict(row)
        terms = cls._load_json_list(data.pop("candidate_terms", None))
        names = cls._load_json_list(data.pop("detected_names", None))
        return ReferenceChapter(candidate_terms=terms, detected_names=names, **data)

    def list_references(self, pid: str) -> list[ReferenceChapter]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reference_chapters WHERE project_id=? ORDER BY created_at ASC",
                (pid,),
            ).fetchall()
        return [self._row_to_reference(r) for r in rows]

    def get_reference(self, ref_id: str) -> ReferenceChapter | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM reference_chapters WHERE id=?", (ref_id,)
            ).fetchone()
        return self._row_to_reference(row) if row else None

    def add_reference(
        self,
        pid: str,
        title: str,
        content: str,
        summary: str | None = None,
        candidate_terms: list[str] | None = None,
        detected_names: list[str] | None = None,
        chapter_number: int | None = None,
    ) -> ReferenceChapter:
        ref = ReferenceChapter(
            id=new_id(),
            project_id=pid,
            title=title,
            content=content,
            created_at=utcnow_iso(),
            chapter_number=chapter_number,
            summary=summary,
            candidate_terms=candidate_terms or [],
            detected_names=detected_names or [],
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO reference_chapters"
                " (id, project_id, title, content, created_at, chapter_number, summary,"
                "  candidate_terms, detected_names)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    ref.id,
                    ref.project_id,
                    ref.title,
                    ref.content,
                    ref.created_at,
                    ref.chapter_number,
                    ref.summary,
                    json.dumps(ref.candidate_terms, ensure_ascii=False),
                    json.dumps(ref.detected_names, ensure_ascii=False),
                ),
            )
        return ref

    def set_reference_summary(
        self,
        ref_id: str,
        summary: str,
        candidate_terms: list[str],
        detected_names: list[str] | None = None,
    ) -> ReferenceChapter | None:
        with self._connect() as conn:
            if detected_names is None:
                cur = conn.execute(
                    "UPDATE reference_chapters SET summary=?, candidate_terms=? WHERE id=?",
                    (summary, json.dumps(candidate_terms, ensure_ascii=False), ref_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE reference_chapters SET summary=?, candidate_terms=?,"
                    " detected_names=? WHERE id=?",
                    (
                        summary,
                        json.dumps(candidate_terms, ensure_ascii=False),
                        json.dumps(detected_names, ensure_ascii=False),
                        ref_id,
                    ),
                )
            if cur.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM reference_chapters WHERE id=?", (ref_id,)
            ).fetchone()
        return self._row_to_reference(row) if row else None

    def set_reference_detected_names(
        self, ref_id: str, detected_names: list[str]
    ) -> ReferenceChapter | None:
        """Update ONLY the rule-based detected_names, leaving summary/candidate_terms as-is.

        Backs the "Redetect names" action: re-run the offline name detector without
        touching the (possibly expensive) AI-derived summary.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE reference_chapters SET detected_names=? WHERE id=?",
                (json.dumps(detected_names, ensure_ascii=False), ref_id),
            )
            if cur.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM reference_chapters WHERE id=?", (ref_id,)
            ).fetchone()
        return self._row_to_reference(row) if row else None

    def remove_reference_term(
        self, ref_id: str, term: str
    ) -> ReferenceChapter | None:
        """Drop a term (case-insensitive) from a reference's detected_names AND
        candidate_terms. Called when a suggestion is resolved (promoted or rejected) so it
        leaves the reference's suggestion pool for good — it now lives in the glossary.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM reference_chapters WHERE id=?", (ref_id,)
            ).fetchone()
            if not row:
                return None
            ref = self._row_to_reference(row)
            low = term.casefold()
            detected = [t for t in ref.detected_names if t.casefold() != low]
            candidates = [t for t in ref.candidate_terms if t.casefold() != low]
            conn.execute(
                "UPDATE reference_chapters SET detected_names=?, candidate_terms=?"
                " WHERE id=?",
                (
                    json.dumps(detected, ensure_ascii=False),
                    json.dumps(candidates, ensure_ascii=False),
                    ref_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM reference_chapters WHERE id=?", (ref_id,)
            ).fetchone()
        return self._row_to_reference(updated) if updated else None

    def delete_reference(self, ref_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM reference_chapters WHERE id=?", (ref_id,)
            )
        return cur.rowcount > 0

    # --- glossary (English-first, task 14) ---
    def list_glossary(self, pid: str) -> list[GlossaryEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM glossary_entries WHERE project_id=?"
                " ORDER BY surface_form COLLATE NOCASE ASC",
                (pid,),
            ).fetchall()
        return [GlossaryEntry(**dict(r)) for r in rows]

    def add_term(
        self,
        pid: str,
        surface_form: str,
        *,
        source_term: str | None = None,
        status: str = "candidate",
        category: str = "term",
        gender: str | None = None,
        note: str | None = None,
    ) -> GlossaryEntry:
        """Insert or upsert an English-first term, keyed on surface_form (case-insensitive).

        If the surface form already exists for the project, non-null fields are merged in
        (source_term/status/category/gender/note), so promoting a candidate to a paired,
        approved entry is a single call.
        """
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM glossary_entries"
                " WHERE project_id=? AND surface_form=? COLLATE NOCASE",
                (pid, surface_form),
            ).fetchone()
            if existing:
                entry_id = existing["id"]
                merged = {
                    "surface_form": surface_form,
                    "source_term": source_term
                    if source_term is not None
                    else existing["source_term"],
                    "status": status or existing["status"],
                    "category": category or existing["category"],
                    "gender": gender if gender is not None else existing["gender"],
                    "note": note if note is not None else existing["note"],
                }
                conn.execute(
                    "UPDATE glossary_entries SET surface_form=?, source_term=?, status=?,"
                    " category=?, gender=?, note=? WHERE id=?",
                    (
                        merged["surface_form"],
                        merged["source_term"],
                        merged["status"],
                        merged["category"],
                        merged["gender"],
                        merged["note"],
                        entry_id,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM glossary_entries WHERE id=?", (entry_id,)
                ).fetchone()
            else:
                entry_id = new_id()
                created_at = utcnow_iso()
                conn.execute(
                    "INSERT INTO glossary_entries"
                    " (id, project_id, surface_form, source_term, status, category,"
                    "  gender, note, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        entry_id,
                        pid,
                        surface_form,
                        source_term,
                        status,
                        category,
                        gender,
                        note,
                        created_at,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM glossary_entries WHERE id=?", (entry_id,)
                ).fetchone()
        return GlossaryEntry(**dict(row))

    def set_term_status(self, entry_id: str, status: str) -> GlossaryEntry | None:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE glossary_entries SET status=? WHERE id=?", (status, entry_id)
            )
            if cur.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM glossary_entries WHERE id=?", (entry_id,)
            ).fetchone()
        return GlossaryEntry(**dict(row)) if row else None

    def update_glossary(
        self,
        entry_id: str,
        *,
        surface_form: str | None = None,
        source_term: str | None = None,
        status: str | None = None,
        category: str | None = None,
        gender: str | None = None,
        note: str | None = None,
    ) -> GlossaryEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM glossary_entries WHERE id=?", (entry_id,)
            ).fetchone()
            if not row:
                return None
            merged = {
                "surface_form": surface_form
                if surface_form is not None
                else row["surface_form"],
                "source_term": source_term
                if source_term is not None
                else row["source_term"],
                "status": status if status is not None else row["status"],
                "category": category if category is not None else row["category"],
                "gender": gender if gender is not None else row["gender"],
                "note": note if note is not None else row["note"],
            }
            conn.execute(
                "UPDATE glossary_entries SET surface_form=?, source_term=?, status=?,"
                " category=?, gender=?, note=? WHERE id=?",
                (
                    merged["surface_form"],
                    merged["source_term"],
                    merged["status"],
                    merged["category"],
                    merged["gender"],
                    merged["note"],
                    entry_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM glossary_entries WHERE id=?", (entry_id,)
            ).fetchone()
        return GlossaryEntry(**dict(updated))

    def delete_glossary(self, entry_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM glossary_entries WHERE id=?", (entry_id,)
            )
        return cur.rowcount > 0

    # --- translations ---
    def save_translation(
        self,
        pid: str,
        source_lang: SourceLang,
        raw_text: str,
        output_text: str,
        model_used: str,
    ) -> Translation:
        tr = Translation(
            id=new_id(),
            project_id=pid,
            source_lang=source_lang,
            raw_text=raw_text,
            output_text=output_text,
            model_used=model_used,
            created_at=utcnow_iso(),
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO translations"
                " (id, project_id, source_lang, raw_text, output_text, model_used, created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    tr.id,
                    tr.project_id,
                    tr.source_lang,
                    tr.raw_text,
                    tr.output_text,
                    tr.model_used,
                    tr.created_at,
                ),
            )
        return tr

    def list_translations(self, pid: str) -> list[Translation]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM translations WHERE project_id=? ORDER BY created_at DESC",
                (pid,),
            ).fetchall()
        return [Translation(**dict(r)) for r in rows]

    def get_translation(self, tid: str) -> Translation | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM translations WHERE id=?", (tid,)
            ).fetchone()
        return Translation(**dict(row)) if row else None

    def delete_translation(self, tid: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM translations WHERE id=?", (tid,))
        return cur.rowcount > 0
