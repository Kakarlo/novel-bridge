"""Project, reference, and glossary CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
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
    ResolveTermBody,
    TermMatch,
    Translation,
)
from app.services.noun_extract import extract_proper_nouns
from app.services.pronoun_check import PronounFlag, find_pronoun_drift
from app.services.source_terms import extract_source_terms
from app.services.term_match import find_occurrences
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
            # Exclude rejected terms: a rejected term is a soft-delete (kept for restore,
            # out of the prompt), so the headline count reflects only live terms.
            "glossary": sum(
                1 for e in store.list_glossary(pid) if e.status != "rejected"
            ),
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
    # (task 13). A deterministic rule-based proper-noun pass (field-fix #2) runs first and
    # both (a) feeds the engine as a hint and (b) is stored separately as detected_names.
    # If engine extraction fails (e.g. unreachable), keep the reference with the rule-based
    # names anyway; the user can resummarize later.
    detected_names = extract_proper_nouns(body.content)
    summary: str | None = None
    candidate_terms: list[str] = []
    # Names-only mode (body.extract_summary == False): skip the slow AI extraction entirely
    # and store just the detected names. Otherwise run the engine extraction, degrading
    # gracefully (keep the reference with names only) if the engine is unreachable.
    if body.extract_summary:
        project = store.get_project(pid)
        lang = (project.source_lang if project else None) or "zh"
        try:
            extraction = await engine.extract_reference(body.content, lang, detected_names)
            summary = extraction.summary or None
            candidate_terms = extraction.candidate_terms
        except Exception:  # noqa: BLE001 - degrade gracefully, keep the reference
            summary = None
            candidate_terms = []
    return store.add_reference(
        pid, body.title, body.content, summary, candidate_terms, detected_names
    )


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
    detected_names = extract_proper_nouns(ref.content)
    try:
        extraction = await engine.extract_reference(ref.content, lang, detected_names)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Reference extraction failed: {exc}") from exc
    updated = store.set_reference_summary(
        ref_id, extraction.summary, extraction.candidate_terms, detected_names
    )
    if not updated:
        raise HTTPException(404, "Reference not found")
    return updated


@router.post("/references/{ref_id}/redetect", response_model=ReferenceChapter)
def redetect_reference_names(
    ref_id: str, store: StorageService = Depends(get_storage)
):
    """Re-run ONLY the offline name detector for one reference (no AI, no engine call).

    A fast way to refresh ``detected_names`` after the detector improves, or to spot names
    missed on the first pass, without re-running the slow summary extraction.
    """
    ref = store.get_reference(ref_id)
    if not ref:
        raise HTTPException(404, "Reference not found")
    detected_names = extract_proper_nouns(ref.content)
    # Don't resurface names the user has already resolved into the glossary (promoted or
    # rejected) — those have left the suggestion pool on purpose.
    in_glossary = {e.surface_form.casefold() for e in store.list_glossary(ref.project_id)}
    detected_names = [n for n in detected_names if n.casefold() not in in_glossary]
    updated = store.set_reference_detected_names(ref_id, detected_names)
    if not updated:
        raise HTTPException(404, "Reference not found")
    return updated


@router.post("/references/{ref_id}/resolve-term", response_model=ReferenceChapter)
def resolve_reference_term(
    ref_id: str, body: ResolveTermBody, store: StorageService = Depends(get_storage)
):
    """Remove a resolved suggestion (promoted or rejected) from a reference's suggestion
    pool, so it won't reappear as a chip and redetect won't resurface it."""
    updated = store.remove_reference_term(ref_id, body.term)
    if not updated:
        raise HTTPException(404, "Reference not found")
    return updated


@router.get("/references/{ref_id}/source-terms", response_model=list[str])
def reference_source_terms(
    ref_id: str,
    store: StorageService = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    """EXPERIMENTAL (gated by NB_SOURCE_TERMS): deterministic zh/ja proper-noun detection
    over the reference's source text. 404 if the feature is off or the reference is missing.
    Returns [] if the relevant spaCy model isn't installed."""
    if not settings.nb_source_terms:
        raise HTTPException(404, "Source-term detection is disabled")
    ref = store.get_reference(ref_id)
    if not ref:
        raise HTTPException(404, "Reference not found")
    project = store.get_project(ref.project_id)
    lang = (project.source_lang if project else None) or "zh"
    return extract_source_terms(ref.content, lang)


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


@router.get("/translations/{tid}/matches", response_model=list[TermMatch])
def get_translation_matches(tid: str, store: StorageService = Depends(get_storage)):
    """Re-run occurrence detection against a saved translation (task 14).

    Supports retrospective review: viewing a saved translation re-scans its output for
    the project's current glossary terms. Recomputed on demand (not stored), so edits to
    the glossary are reflected without re-translating. Detection only.
    """
    tr = store.get_translation(tid)
    if not tr:
        raise HTTPException(404, "Translation not found")
    glossary = store.list_glossary(tr.project_id)
    return find_occurrences(tr.output_text, glossary)


@router.get("/translations/{tid}/pronoun-drift", response_model=list[PronounFlag])
def get_translation_pronoun_drift(
    tid: str,
    store: StorageService = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    """EXPERIMENTAL (gated by NB_PRONOUN_CHECK): flag likely gender/pronoun mismatches for
    gendered characters in a saved translation. Detection only — never rewrites. 404 if the
    feature is off or the translation is missing."""
    if not settings.nb_pronoun_check:
        raise HTTPException(404, "Pronoun-drift detection is disabled")
    tr = store.get_translation(tid)
    if not tr:
        raise HTTPException(404, "Translation not found")
    glossary = store.list_glossary(tr.project_id)
    return find_pronoun_drift(tr.output_text, glossary)


@router.delete("/translations/{tid}", status_code=204)
def delete_translation(tid: str, store: StorageService = Depends(get_storage)):
    if not store.delete_translation(tid):
        raise HTTPException(404, "Translation not found")


def _require_project(store: StorageService, pid: str) -> None:
    if not store.get_project(pid):
        raise HTTPException(404, "Project not found")
