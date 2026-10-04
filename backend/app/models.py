"""Domain entities and API request/response models.

Entities use string UUID ids so the data model maps cleanly to a future
DynamoDB design (project_id as partition key) without schema churn.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

SourceLang = Literal["zh", "ja"]


def new_id() -> str:
    return uuid4().hex


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Entities ---------------------------------------------------------------


class Project(BaseModel):
    id: str
    name: str
    source_lang: SourceLang | None = None
    created_at: str


class ReferenceChapter(BaseModel):
    id: str
    project_id: str
    title: str
    content: str
    created_at: str
    # Derived at upload time by the engine's reference extraction (task 13). A short
    # style/plot summary and a list of candidate terms (names/terminology). Both are
    # optional: extraction may not have run yet (e.g. engine was unreachable) until a
    # resummarize is triggered.
    summary: str | None = None
    candidate_terms: list[str] = Field(default_factory=list)


class GlossaryEntry(BaseModel):
    id: str
    project_id: str
    source_term: str
    translation: str
    note: str | None = None


class Translation(BaseModel):
    id: str
    project_id: str
    source_lang: SourceLang
    raw_text: str
    output_text: str
    model_used: str
    created_at: str


# --- API request models -----------------------------------------------------


class ProjectCreate(BaseModel):
    name: str
    source_lang: SourceLang | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Project name must not be empty.")
        return v.strip()


class ReferenceCreate(BaseModel):
    title: str
    content: str

    @field_validator("title", "content")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Reference title and content must not be empty.")
        return v.strip()


class GlossaryCreate(BaseModel):
    source_term: str
    translation: str
    note: str | None = None

    @field_validator("source_term", "translation")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Glossary source term and translation must not be empty.")
        return v.strip()


class GlossaryUpdate(BaseModel):
    translation: str | None = None
    note: str | None = None


class TranslateRequest(BaseModel):
    raw_text: str = Field(min_length=1)
    source_lang: SourceLang

    @field_validator("raw_text")
    @classmethod
    def raw_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Raw text must not be empty.")
        return v
