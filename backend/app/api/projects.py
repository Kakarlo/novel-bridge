"""Project, reference, and glossary CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_storage, get_translation_engine
from app.engines.base import TranslationEngine
from app.models import (
    GlossaryCreate,
    GlossaryEntry,
    GlossaryStatusUpdate,
    GlossaryUpdate,
    Project,
    ProjectCreate,
    ReferenceChapter,
    ReferenceCreate,
    Translation,
)
from app.storage.base import StorageService

router = APIRouter(prefix="/api", tags=["projects"])


# --- projects ---
@router.get("/projects", response_model=list[Project])
def list_projects(store: StorageService = Depends(get_storage)):
    return store.list_projects()


@router.post("/projects", response_model=Project, status_code=201)
def create_project(body: ProjectCreate, store: StorageService = Depends(get_storage)):
    return store.create_project(body.name, body.source_lang)


@router.get("/projects/{pid}")
def get_project(pid: str, store: StorageService = Depends(get_storage)):
    proj = store.get_project(pid)
    if not proj:
        raise HTTPException(404, "Project not found")
    return {
        "project": proj,
        "counts": {
            "references": len(store.list_references(pid)),
            "glossary": len(store.list_glossary(pid)),
            "translations": len(store.list_translations(pid)),
        },
    }


@router.delete("/projects/{pid}", status_code=204)
def delete_project(pid: str, store: StorageService = Depends(get_storage)):
    if not store.delete_project(pid):
        raise HTTPException(404, "Project not found")


# --- references ---
@router.get("/projects/{pid}/references", response_model=list[ReferenceChapter])
def list_references(pid: str, store: StorageService = Depends(get_storage)):
    _require_project(store, pid)
    return store.list_references(pid)


@router.post("/projects/{pid}/references", response_model=ReferenceChapter, status_code=201)
async def add_reference(
    pid: str,
    body: ReferenceCreate,
    store: StorageService = Depends(get_storage),
    engine: TranslationEngine = Depends(get_translation_engine),
):
    _require_project(store, pid)
    # Derive a summary + candidate glossary terms once, synchronously, at upload time
    # (task 13). If extraction fails (e.g. engine unreachable), store the reference
    # anyway with no summary; the user can trigger resummarize later.
    summary: str | None = None
    candidate_terms: list[str] = []
    project = store.get_project(pid)
    lang = (project.source_lang if project else None) or "zh"
    try:
        extraction = await engine.extract_reference(body.content, lang)
        summary = extraction.summary or None
        candidate_terms = extraction.candidate_terms
    except Exception:  # noqa: BLE001 - degrade gracefully, keep the reference
        summary = None
        candidate_terms = []
    return store.add_reference(pid, body.title, body.content, summary, candidate_terms)


@router.post("/references/{ref_id}/resummarize", response_model=ReferenceChapter)
async def resummarize_reference(
    ref_id: str,
    store: StorageService = Depends(get_storage),
    engine: TranslationEngine = Depends(get_translation_engine),
):
    ref = store.get_reference(ref_id)
    if not ref:
        raise HTTPException(404, "Reference not found")
    project = store.get_project(ref.project_id)
    lang = (project.source_lang if project else None) or "zh"
    try:
        extraction = await engine.extract_reference(ref.content, lang)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Reference extraction failed: {exc}") from exc
    updated = store.set_reference_summary(
        ref_id, extraction.summary, extraction.candidate_terms
    )
    if not updated:
        raise HTTPException(404, "Reference not found")
    return updated


@router.delete("/references/{ref_id}", status_code=204)
def delete_reference(ref_id: str, store: StorageService = Depends(get_storage)):
    if not store.delete_reference(ref_id):
        raise HTTPException(404, "Reference not found")


# --- glossary ---
@router.get("/projects/{pid}/glossary", response_model=list[GlossaryEntry])
def list_glossary(pid: str, store: StorageService = Depends(get_storage)):
    _require_project(store, pid)
    return store.list_glossary(pid)


@router.post("/projects/{pid}/glossary", response_model=GlossaryEntry, status_code=201)
def create_glossary(
    pid: str, body: GlossaryCreate, store: StorageService = Depends(get_storage)
):
    """Create/upsert a glossary term, English-first.

    A paired entry (``source_term`` provided) defaults to ``approved``; an English-only
    add defaults to ``candidate``. An explicit ``status`` in the body wins.
    """
    _require_project(store, pid)
    status = body.status or ("approved" if body.source_term else "candidate")
    return store.add_term(
        pid,
        body.surface_form,
        source_term=body.source_term,
        status=status,
        category=body.category,
        gender=body.gender,
        note=body.note,
    )


@router.put("/glossary/{entry_id}", response_model=GlossaryEntry)
def update_glossary(
    entry_id: str, body: GlossaryUpdate, store: StorageService = Depends(get_storage)
):
    updated = store.update_glossary(
        entry_id,
        surface_form=body.surface_form,
        source_term=body.source_term,
        status=body.status,
        category=body.category,
        gender=body.gender,
        note=body.note,
    )
    if not updated:
        raise HTTPException(404, "Glossary entry not found")
    return updated


@router.patch("/glossary/{entry_id}/status", response_model=GlossaryEntry)
def set_glossary_status(
    entry_id: str,
    body: GlossaryStatusUpdate,
    store: StorageService = Depends(get_storage),
):
    """Approve/reject a term in context (the in-context review loop)."""
    updated = store.set_term_status(entry_id, body.status)
    if not updated:
        raise HTTPException(404, "Glossary entry not found")
    return updated


@router.delete("/glossary/{entry_id}", status_code=204)
def delete_glossary(entry_id: str, store: StorageService = Depends(get_storage)):
    if not store.delete_glossary(entry_id):
        raise HTTPException(404, "Glossary entry not found")


# --- translations history ---
@router.get("/projects/{pid}/translations", response_model=list[Translation])
def list_translations(pid: str, store: StorageService = Depends(get_storage)):
    _require_project(store, pid)
    return store.list_translations(pid)


@router.get("/translations/{tid}", response_model=Translation)
def get_translation(tid: str, store: StorageService = Depends(get_storage)):
    tr = store.get_translation(tid)
    if not tr:
        raise HTTPException(404, "Translation not found")
    return tr


@router.delete("/translations/{tid}", status_code=204)
def delete_translation(tid: str, store: StorageService = Depends(get_storage)):
    if not store.delete_translation(tid):
        raise HTTPException(404, "Translation not found")


def _require_project(store: StorageService, pid: str) -> None:
    if not store.get_project(pid):
        raise HTTPException(404, "Project not found")
