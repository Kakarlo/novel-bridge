"""Abstract storage interface.

Isolating persistence behind this interface keeps the app local-first (SQLite)
while leaving a clean path to swap in DynamoDB later (Requirement 6.2).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import (
    GlossaryEntry,
    Project,
    ReferenceChapter,
    SourceLang,
    Translation,
)


class StorageService(ABC):
    # --- projects ---
    @abstractmethod
    def list_projects(self) -> list[Project]: ...

    @abstractmethod
    def create_project(self, name: str, source_lang: SourceLang | None) -> Project: ...

    @abstractmethod
    def get_project(self, pid: str) -> Project | None: ...

    @abstractmethod
    def delete_project(self, pid: str) -> bool: ...

    # --- references ---
    @abstractmethod
    def list_references(self, pid: str) -> list[ReferenceChapter]: ...

    @abstractmethod
    def get_reference(self, ref_id: str) -> ReferenceChapter | None: ...

    @abstractmethod
    def add_reference(
        self,
        pid: str,
        title: str,
        content: str,
        summary: str | None = None,
        candidate_terms: list[str] | None = None,
    ) -> ReferenceChapter: ...

    @abstractmethod
    def set_reference_summary(
        self, ref_id: str, summary: str, candidate_terms: list[str]
    ) -> ReferenceChapter | None: ...

    @abstractmethod
    def delete_reference(self, ref_id: str) -> bool: ...

    # --- glossary (English-first, task 14) ---
    @abstractmethod
    def list_glossary(self, pid: str) -> list[GlossaryEntry]: ...

    @abstractmethod
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
    ) -> GlossaryEntry: ...

    @abstractmethod
    def set_term_status(self, entry_id: str, status: str) -> GlossaryEntry | None: ...

    @abstractmethod
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
    ) -> GlossaryEntry | None: ...

    @abstractmethod
    def delete_glossary(self, entry_id: str) -> bool: ...

    # --- translations ---
    @abstractmethod
    def save_translation(
        self,
        pid: str,
        source_lang: SourceLang,
        raw_text: str,
        output_text: str,
        model_used: str,
    ) -> Translation: ...

    @abstractmethod
    def list_translations(self, pid: str) -> list[Translation]: ...

    @abstractmethod
    def get_translation(self, tid: str) -> Translation | None: ...

    @abstractmethod
    def delete_translation(self, tid: str) -> bool: ...
