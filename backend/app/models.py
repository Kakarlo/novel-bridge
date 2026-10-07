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
GlossaryStatus = Literal["candidate", "approved", "rejected"]
GlossaryCategory = Literal["character", "title", "term", "location", "organization", "item"]
Gender = Literal["male", "female", "unknown"]


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
    # Per-project writing-style profile extracted from reference chapters or written by hand.
    # Injected into every translation prompt so register, rhythm, and terminology stay
    # consistent across the whole series. None until the user extracts or writes a style.
    style_profile: str | None = None


class ReferenceChapter(BaseModel):
    id: str
    project_id: str
    title: str
    content: str
    created_at: str
    # Parsed from the title at upload (services/chapter_number.py). None when the title has
    # no recognizable chapter number; ordering falls back to created_at and the UI can ask
    # the user to set one.
    chapter_number: int | None = None
    # Derived at upload time by the engine's reference extraction (task 13). A short
    # style/plot summary and a list of candidate terms (names/terminology). Both are
    # optional: extraction may not have run yet (e.g. engine was unreachable) until a
    # resummarize is triggered.
    summary: str | None = None
    candidate_terms: list[str] = Field(default_factory=list)
    # Rule-based proper-noun detections (field-fix #2), kept SEPARATE from the AI's
    # candidate_terms so the user can see which came from deterministic rules vs the model.
    # Computed offline from the English text at upload (and on resummarize).
    detected_names: list[str] = Field(default_factory=list)


class GlossaryEntry(BaseModel):
    """English-first glossary entry (task 14).

    The glossary is English-first because references are already English, so the user
    knows the English name, not the source term. ``surface_form`` is the English name and
    is always present. ``source_term`` is the optional original-language term (set for
    classic paired entries, or once a source↔translation match has been confirmed).

    - ``status``: ``candidate`` (extracted, awaiting approval) → ``approved`` (fed to the
      prompt as a preferred spelling) / ``rejected`` (kept out of the prompt).
    - ``category``: ``character`` | ``title`` | ``term`` (borrowed from OpenNovel so the
      prompt can treat character names, honorific titles, and generic terms distinctly).
    - ``gender``: meaningful for characters; steers zh→en pronoun consistency.
    """

    id: str
    project_id: str
    surface_form: str
    source_term: str | None = None
    status: GlossaryStatus = "candidate"
    category: GlossaryCategory = "term"
    gender: Gender | None = None
    note: str | None = None
    created_at: str | None = None


class Translation(BaseModel):
    id: str
    project_id: str
    source_lang: SourceLang
    raw_text: str
    output_text: str
    model_used: str
    created_at: str


class TermMatch(BaseModel):
    """One glossary term's occurrences found in a translation's output (task 14.2).

    Produced by ``services.term_match.find_occurrences`` for the in-context review loop.
    Detection only — it never rewrites the translation. ``snippets`` are short context
    windows around occurrences for the review UI; ``count`` is the total occurrences.
    """

    term_id: str
    surface_form: str
    status: GlossaryStatus
    category: GlossaryCategory
    count: int
    snippets: list[str] = Field(default_factory=list)


class GlossaryPairSuggestion(BaseModel):
    """An LLM-paired source-term -> English-spelling glossary suggestion (task: replace the
    deterministic aligner).

    The old ``AlignmentCandidate`` paired by appearance-rank/frequency correlation — a
    heuristic that produced near-random pairs because that signal doesn't survive
    translation. This replaces it: the engine reads the source chapter AND its English
    translation and binds each source term to the exact English spelling the translator
    actually used (``services.prompt.build_glossary_pairing_messages``). These are
    suggestions — the frontend adds a chosen pair to the glossary as a ``candidate`` for the
    user to approve; nothing is written automatically.

    ``category``/``gender`` mirror ``GlossaryEntry`` so a confirmed pair maps straight onto a
    glossary row. ``gender`` is meaningful for characters (steers zh->en pronoun drift).
    """

    source_term: str
    surface_form: str
    category: GlossaryCategory = "term"
    gender: Gender | None = None
    note: str | None = None


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
    """Create a glossary entry, English-first.

    ``surface_form`` (the English name) is required. ``source_term`` is optional: when
    provided this is a classic paired entry and defaults to ``approved`` status. An
    English-only add omits ``source_term`` and defaults to ``candidate``.
    """

    surface_form: str
    source_term: str | None = None
    status: GlossaryStatus | None = None
    category: GlossaryCategory = "term"
    gender: Gender | None = None
    note: str | None = None

    @field_validator("surface_form")
    @classmethod
    def surface_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Glossary surface form must not be empty.")
        return v.strip()

    @field_validator("source_term")
    @classmethod
    def source_blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class GlossaryUpdate(BaseModel):
    surface_form: str | None = None
    source_term: str | None = None
    status: GlossaryStatus | None = None
    category: GlossaryCategory | None = None
    gender: Gender | None = None
    note: str | None = None


class GlossaryStatusUpdate(BaseModel):
    status: GlossaryStatus


class ResolveTermBody(BaseModel):
    """Remove one resolved suggestion (promoted/rejected) from a reference's pools."""

    term: str

    @field_validator("term")
    @classmethod
    def term_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Term must not be empty.")
        return v.strip()


class StyleProfileBody(BaseModel):
    """Manual set/edit of a per-project writing-style profile."""

    style_profile: str

    @field_validator("style_profile")
    @classmethod
    def style_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Style profile must not be empty.")
        return v.strip()


class StyleExtractBody(BaseModel):
    """Optional body for POST /projects/{id}/extract-style.

    ``content`` lets the caller analyze a specific pasted chapter; when omitted (or no body
    at all), the route falls back to the project's newest reference chapter.

    ``selection`` carries the optional per-request engine override ({provider, model}),
    same shape as the translate body, so a BYO-key user can run style extraction on their
    own provider. The API key rides on the X-LLM-Api-Key header, never in this body.

    Stateless path (task 23.4c): the IndexedDB backend has no server-side project row, so when
    it sends ``content`` it ALSO sends ``source_lang`` (the server can't read it from a project)
    and the route neither reads nor writes a project — it returns the computed style only (see
    ``StyleProfileResult``). ``source_lang`` is ignored on the DB path (read from the project).
    """

    content: str | None = None
    source_lang: SourceLang | None = None
    selection: "ModelSelection | None" = None

    @field_validator("content")
    @classmethod
    def content_blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class StyleProfileResult(BaseModel):
    """Response for POST /projects/{id}/extract-style (task 23.4c).

    The route returns ONLY the computed style string, not the whole ``Project``: the browser
    (IndexedDB backend) owns the project and persists the style locally, and the API backend
    just reads ``style_profile`` off this result and persists server-side itself. Returning a
    narrow result (instead of ``Project``) is what lets the stateless path avoid touching a
    project row at all.
    """

    style_profile: str


class ModelSelection(BaseModel):
    """Per-request engine override, modeled as a ``{provider, model}`` pair.

    Why a pair and not a bare ``model`` string: the project is heading toward multiple
    providers (local Ollama today; Gemini/OpenRouter next — see tech.md "Bring-your-own
    LLM API token"). Picking a model is only unambiguous WITHIN a provider, so the override
    is a pair from day one. Today ``provider`` is effectively fixed to the configured engine,
    but accepting the field now means adding a cloud provider later is a pure data change —
    no SSE-contract break for the frontend picker (already modeled provider → model).

    Both fields are optional:
    - ``provider`` omitted  → use the server's configured engine (``NB_ENGINE``).
    - ``model`` omitted      → use that provider's configured default (e.g. ``OLLAMA_MODEL``).
    """

    provider: str | None = None
    model: str | None = None

    @field_validator("provider", "model")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class GlossaryExtractBody(BaseModel):
    """Optional body for POST /translations/{tid}/extract-glossary.

    Carries the per-request engine override ({provider, model}) as ``selection`` — the SAME
    shape as the translate and extract-style bodies, so every LLM endpoint accepts the engine
    choice the same way (no more provider/model query params). Omitted entirely → the server
    falls back to its configured engine + default model. The API key rides on the
    X-LLM-Api-Key header, never in this body.

    Stateless (local-first) fields — task 23.4c, backward-compatible: the browser (IndexedDB
    backend) owns the saved translation, so it ships the source + output text in the body
    instead of the server loading them by ``tid``. Both ``raw_text`` and ``output_text`` are
    optional:
      - BOTH provided → the server uses them verbatim and does NO storage read (the stateless
        path; ``source_lang`` must then be supplied so the deterministic pre-filters know the
        source language).
      - either omitted → the server loads the saved translation from storage by ``tid`` as
        before (the API-storage backend's behavior, unchanged).
    """

    selection: "ModelSelection | None" = None
    raw_text: str | None = None
    output_text: str | None = None
    # Source language of ``raw_text`` on the stateless path (the server has no DB row to read
    # it from). Ignored when loading by ``tid``. Defaults to ``zh`` when the stateless body
    # omits it.
    source_lang: SourceLang | None = None

    @field_validator("raw_text", "output_text")
    @classmethod
    def text_blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class DetectNamesBody(BaseModel):
    """Body for POST /api/detect-names (task 23.4c).

    The stateless equivalent of ``POST /api/references/{id}/redetect``: pure, offline spaCy
    proper-noun compute over text the browser (IndexedDB backend) ships in the request, so no
    storage read/write is needed. spaCy stays server-side (design decision §8.4). Unlike
    ``redetect`` this endpoint does NO glossary cross-check — it has no project context; the
    idb client hides already-promoted/rejected names against its local glossary.
    """

    content: str

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Content must not be empty.")
        return v.strip()


class DetectNamesResponse(BaseModel):
    """Response for POST /api/detect-names: the deterministically detected proper nouns."""

    detected_names: list[str] = Field(default_factory=list)


class TranslateRequest(BaseModel):
    raw_text: str = Field(min_length=1)
    source_lang: SourceLang
    # Opt-in in-context term review (task 14). When true, the terminal `done` SSE event
    # carries `matches` (glossary terms found in the output) for the approve/reject loop.
    # Defaults false so the streaming path is untouched unless the user turned review on.
    review_terms: bool = False
    # Optional per-request engine override (provider-aware model picker). Omitted entirely
    # by existing clients → the server falls back to its configured engine + default model,
    # so this is fully backward-compatible. The engine already honors a per-request model
    # via TranslationRequest.model; see api/translate.py for how `selection` is resolved.
    selection: ModelSelection | None = None
    # --- Stateless (local-first) contract, task 23.4b ---------------------------
    # The browser (IndexedDB backend) owns all user data, so it ships the context the
    # translation needs in the request body instead of the server loading it by `pid`. All
    # three are OPTIONAL and backward-compatible:
    #   - ``glossary`` None       → the server loads the project glossary from storage (the
    #                               API-storage backend's behavior). A provided list (even
    #                               empty) is used verbatim and NO storage read happens.
    #   - ``style_profile`` None  → the server reads the project's stored style profile. A
    #                               provided string (including "") is used verbatim.
    #   - ``save`` True (default) → the server auto-saves the completed translation and the
    #                               `done` event carries its id (today's API-backend behavior).
    #                               The idb client sends ``save=false`` because it persists the
    #                               result client-side (task 23.4a); then no storage write
    #                               happens and `done.translation_id` is null.
    # Existing clients that send none of these see identical behavior to before.
    glossary: list[GlossaryEntry] | None = None
    style_profile: str | None = None
    save: bool = True

    @field_validator("raw_text")
    @classmethod
    def raw_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Raw text must not be empty.")
        return v


# StyleExtractBody and GlossaryExtractBody reference ModelSelection via a forward ref
# (ModelSelection is defined later in this module); resolve them now that all classes exist.
StyleExtractBody.model_rebuild()
GlossaryExtractBody.model_rebuild()
