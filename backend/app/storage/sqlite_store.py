"""SQLite implementation of StorageService."""

from __future__ import annotations

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
    def list_references(self, pid: str) -> list[ReferenceChapter]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reference_chapters WHERE project_id=? ORDER BY created_at ASC",
                (pid,),
            ).fetchall()
        return [ReferenceChapter(**dict(r)) for r in rows]

    def add_reference(self, pid: str, title: str, content: str) -> ReferenceChapter:
        ref = ReferenceChapter(
            id=new_id(),
            project_id=pid,
            title=title,
            content=content,
            created_at=utcnow_iso(),
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO reference_chapters (id, project_id, title, content, created_at)"
                " VALUES (?,?,?,?,?)",
                (ref.id, ref.project_id, ref.title, ref.content, ref.created_at),
            )
        return ref

    def delete_reference(self, ref_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM reference_chapters WHERE id=?", (ref_id,)
            )
        return cur.rowcount > 0

    # --- glossary ---
    def list_glossary(self, pid: str) -> list[GlossaryEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM glossary_entries WHERE project_id=? ORDER BY source_term ASC",
                (pid,),
            ).fetchall()
        return [GlossaryEntry(**dict(r)) for r in rows]

    def upsert_glossary(
        self, pid: str, source_term: str, translation: str, note: str | None
    ) -> GlossaryEntry:
        """Insert, or update translation/note if (project, source_term) exists."""
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM glossary_entries WHERE project_id=? AND source_term=?",
                (pid, source_term),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE glossary_entries SET translation=?, note=? WHERE id=?",
                    (translation, note, existing["id"]),
                )
                entry_id = existing["id"]
            else:
                entry_id = new_id()
                conn.execute(
                    "INSERT INTO glossary_entries (id, project_id, source_term, translation, note)"
                    " VALUES (?,?,?,?,?)",
                    (entry_id, pid, source_term, translation, note),
                )
        return GlossaryEntry(
            id=entry_id,
            project_id=pid,
            source_term=source_term,
            translation=translation,
            note=note,
        )

    def update_glossary(
        self, entry_id: str, translation: str | None, note: str | None
    ) -> GlossaryEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM glossary_entries WHERE id=?", (entry_id,)
            ).fetchone()
            if not row:
                return None
            new_translation = translation if translation is not None else row["translation"]
            new_note = note if note is not None else row["note"]
            conn.execute(
                "UPDATE glossary_entries SET translation=?, note=? WHERE id=?",
                (new_translation, new_note, entry_id),
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
