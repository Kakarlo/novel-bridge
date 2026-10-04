"""Project, reference, and glossary CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_storage
from app.models import (
    GlossaryCreate,
    GlossaryEntry,
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
def add_reference(
    pid: str, body: ReferenceCreate, store: StorageService = Depends(get_storage)
):
    _require_project(store, pid)
    return store.add_reference(pid, body.title, body.content)


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
    _require_project(store, pid)
    return store.upsert_glossary(pid, body.source_term, body.translation, body.note)


@router.put("/glossary/{entry_id}", response_model=GlossaryEntry)
def update_glossary(
    entry_id: str, body: GlossaryUpdate, store: StorageService = Depends(get_storage)
):
    updated = store.update_glossary(entry_id, body.translation, body.note)
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
