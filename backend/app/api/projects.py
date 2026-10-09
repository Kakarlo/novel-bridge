"""Project, reference, and glossary CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.deps import (
    get_request_api_key,
    get_storage,
    get_translation_engine,
    resolve_request_engine,
)
from app.engines.base import TranslationEngine
from app.models import (
    DetectNamesBody,
    DetectNamesResponse,
    GlossaryCreate,
    GlossaryEntry,
    GlossaryExtractBody,
    GlossaryPairSuggestion,
    GlossaryStatusUpdate,
    GlossaryUpdate,
    Project,
    ProjectCreate,
    ReferenceChapter,
    ReferenceCreate,
    ResolveTermBody,
    StyleExtractBody,
    StyleProfileBody,
    StyleProfileResult,
    TermMatch,
    Translation,
)
from app.services.chapter_number import parse_chapter_number
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


# --- style profile (per-project, task 3) ---
@router.post("/projects/{pid}/extract-style", response_model=StyleProfileResult)
async def extract_project_style(
    pid: str,
    body: StyleExtractBody | None = None,
    store: StorageService = Depends(get_storage),
    fallback_engine: TranslationEngine = Depends(get_translation_engine),
    settings: Settings = Depends(get_settings),
    api_key: str | None = Depends(get_request_api_key),
):
    """Extract a writing-style profile from reference content and return it.

    References are human English translations — their real value is the TRANSLATION STYLE.
    This is the primary AI pass on references, replacing the old per-reference summary +
    candidate-terms pass. Runs a single LLM call that characterizes the prose (register,
    rhythm, dialogue, honorific handling); the style is injected into every translation prompt.

    Returns only the computed style (``StyleProfileResult``), not the whole ``Project``: the
    CALLER persists it (the API-storage client via ``PUT /style``; the IndexedDB client in its
    local store). This is what makes the stateless path (task 23.4c) possible.

    Two paths (backward-compatible):
    - **Stateless** (``body.content`` provided): analyze that pasted chapter; the server does
      NOT read or write any project row. ``body.source_lang`` names the source language
      (defaults to ``zh``) since there's no project to read it from. Used by the IndexedDB
      backend, which has no server-side project.
    - **DB-backed** (no ``content``): fall back to the project's NEWEST reference chapter (by
      chapter_number, then upload order) and read ``source_lang`` from the project. 404 if the
      project is missing or has no references to analyze.

    Using one chapter keeps the context small and reliable for weak local models. A
    multi-chapter merge strategy is a future follow-up. 502 if extraction fails or is empty.
    """
    # Per-request engine resolution (BYO-key). selection.{provider, model} from the body,
    # key from the X-LLM-Api-Key header; falls back to the env/injected engine otherwise.
    sel = body.selection if body else None
    engine = resolve_request_engine(
        provider=sel.provider if sel else None,
        model=sel.model if sel else None,
        api_key=api_key,
        settings=settings,
        fallback=fallback_engine,
        ollama_base_url=sel.ollama_base_url if sel else None,
    )

    sample = body.content.strip() if body and body.content else ""
    if sample:
        # Stateless path: no project read/write; source lang comes from the body (default zh).
        lang = (body.source_lang if body else None) or "zh"
    else:
        # DB-backed path: read the project (for source lang) and its newest reference.
        project = store.get_project(pid)
        if not project:
            raise HTTPException(404, "Project not found")
        refs = store.list_references(pid)
        if not refs:
            raise HTTPException(404, "No reference content to analyze")
        # Use the NEWEST reference: highest chapter_number if available, else last uploaded.
        numbered = [r for r in refs if r.chapter_number is not None]
        if numbered:
            newest = max(numbered, key=lambda r: r.chapter_number)  # type: ignore[arg-type]
        else:
            newest = refs[-1]  # last uploaded (storage returns created_at ASC)
        sample = newest.content
        lang = project.source_lang or "zh"

    try:
        style = await engine.extract_style(sample, lang)
    except Exception as exc:
        raise HTTPException(502, f"Style extraction failed: {exc}") from exc
    if not style.strip():
        raise HTTPException(502, "Style extraction returned nothing")

    # DB-backed path persists server-side so the API client gets the stored project state;
    # the stateless path persists in the browser (the caller does it).
    if not (body and body.content) and not store.update_project_style(pid, style):
        raise HTTPException(404, "Project not found")
    return StyleProfileResult(style_profile=style)


@router.put("/projects/{pid}/style", response_model=Project)
def set_project_style(
    pid: str, body: StyleProfileBody, store: StorageService = Depends(get_storage)
):
    """Manually set/edit the project's style profile (user-authored or hand-tuned)."""
    updated = store.update_project_style(pid, body.style_profile)
    if not updated:
        raise HTTPException(404, "Project not found")
    return updated


@router.delete("/projects/{pid}/style", response_model=Project)
def clear_project_style(pid: str, store: StorageService = Depends(get_storage)):
    """Clear the project's style profile (back to no style)."""
    updated = store.update_project_style(pid, None)
    if not updated:
        raise HTTPException(404, "Project not found")
    return updated


# --- references ---
@router.get("/projects/{pid}/references", response_model=list[ReferenceChapter])
def list_references(pid: str, store: StorageService = Depends(get_storage)):
    _require_project(store, pid)
    return store.list_references(pid)


@router.post("/projects/{pid}/references", response_model=ReferenceChapter, status_code=201)
def add_reference(
    pid: str,
    body: ReferenceCreate,
    store: StorageService = Depends(get_storage),
):
    """Upload a reference chapter. LIGHTWEIGHT — no AI call (references-are-for-style pivot).

    References are human English translations; their value is the TRANSLATION STYLE, captured
    by the project-level ``extract-style`` pass (a deliberate user action), and glossary terms,
    captured by the glossary pairing pass. So upload itself does NO engine call: it just stores
    the text, parses the chapter number from the title, and runs the fast offline proper-noun
    detector (``detected_names``). This makes upload instant and keeps the one AI pass on
    references explicit (the "Extract style" button), rather than a slow surprise on every add.

    (``summary``/``candidate_terms`` columns remain for back-compat but are no longer populated
    at upload; a style profile replaces the per-reference summary.)
    """
    _require_project(store, pid)
    detected_names = extract_proper_nouns(body.content)
    chapter_number = parse_chapter_number(body.title)
    return store.add_reference(
        pid,
        body.title,
        body.content,
        None,  # summary — no longer extracted at upload (pivot to project style)
        [],  # candidate_terms — same
        detected_names,
        chapter_number,
    )


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
    detected_names = extract_proper_nouns(ref.translated_content)
    # Don't resurface names the user has already resolved into the glossary (promoted or
    # rejected) — those have left the suggestion pool on purpose.
    in_glossary = {e.surface_form.casefold() for e in store.list_glossary(ref.project_id)}
    detected_names = [n for n in detected_names if n.casefold() not in in_glossary]
    updated = store.set_reference_detected_names(ref_id, detected_names)
    if not updated:
        raise HTTPException(404, "Reference not found")
    return updated


@router.post("/detect-names", response_model=DetectNamesResponse)
def detect_names(body: DetectNamesBody):
    """Stateless proper-noun detection (task 23.4c) — the DB-free twin of ``redetect``.

    Pure offline spaCy compute over text the caller ships in the body; persists nothing. The
    IndexedDB backend uses this at reference upload (and on Redetect) so ``detected_names``
    works client-side without a server-side reference row. No glossary cross-check here (no
    project context) — the idb client filters already-resolved names against its local
    glossary.
    """
    return DetectNamesResponse(detected_names=extract_proper_nouns(body.content))


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
    return find_occurrences(tr.translated_text, glossary)


@router.get("/translations/{tid}/source-terms", response_model=list[str])
def get_translation_source_terms(
    tid: str,
    store: StorageService = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    """EXPERIMENTAL (gated by NB_SOURCE_TERMS): deterministic zh/ja proper-noun detection
    over a saved translation's SOURCE chapter (``source_text``).

    A reference is English, so source-term NER belongs here, where real source text exists —
    not on references. 404 if the feature is off or the translation is missing. Returns [] if
    the relevant spaCy model isn't installed (treat empty as "unavailable", not "none found")."""
    if not settings.nb_source_terms:
        raise HTTPException(404, "Source-term detection is disabled")
    tr = store.get_translation(tid)
    if not tr:
        raise HTTPException(404, "Translation not found")
    return extract_source_terms(tr.source_text, tr.source_lang)


@router.post(
    "/translations/{tid}/extract-glossary",
    response_model=list[GlossaryPairSuggestion],
)
async def extract_translation_glossary(
    tid: str,
    body: GlossaryExtractBody | None = None,
    store: StorageService = Depends(get_storage),
    fallback_engine: TranslationEngine = Depends(get_translation_engine),
    settings: Settings = Depends(get_settings),
    api_key: str | None = Depends(get_request_api_key),
):
    """LLM-paired glossary extraction from a saved translation.

    Given a saved translation (which has both the raw source chapter and its English output),
    run a single LLM call that binds source-language terms to the exact English spellings
    used in the translation. Replaces the old deterministic appearance-rank/frequency aligner
    (``term-alignment``) which produced unreliable results.

    When ``NB_SOURCE_TERMS`` is enabled and the relevant spaCy model is installed, the
    deterministic source-term NER pass pre-filters candidates so the LLM sees a short,
    focused list (cheap tokens). English proper-noun NER (always available) adds the
    translation-side candidates. Both are hints — the engine may find more pairs.

    Returns ``GlossaryPairSuggestion[]`` for the user to confirm; nothing is written
    to the glossary automatically. The frontend calls ``POST /glossary`` with the chosen
    pairs. ``[]`` on any engine error (degraded, never crashes).

    Source of the text (task 23.4c, backward-compatible):
    - ``body.source_text`` AND ``body.translated_text`` both present → use them verbatim, NO storage
      read (the stateless path for the IndexedDB backend, which owns the saved translation).
      ``body.source_lang`` names the source language (defaults to ``zh``).
    - otherwise → load the saved translation from storage by ``tid`` (the API backend's
      behavior, unchanged); 404 when it's missing.
    """
    # Stateless path: both texts supplied in the body → skip the DB entirely.
    stateless = bool(body and body.source_text and body.translated_text)
    if stateless:
        source_text = body.source_text  # type: ignore[union-attr]
        translated_text = body.translated_text  # type: ignore[union-attr]
        source_lang = (body.source_lang if body else None) or "zh"
    else:
        tr = store.get_translation(tid)
        if not tr:
            raise HTTPException(404, "Translation not found")
        source_text = tr.source_text
        translated_text = tr.translated_text
        source_lang = tr.source_lang

    # Per-request engine resolution (BYO-key). selection.{provider, model} from the body
    # (unified pattern — same as translate / extract-style); key from the X-LLM-Api-Key
    # header. Falls back to the env/injected engine when no creds are supplied.
    sel = body.selection if body else None
    provider = sel.provider if sel else None
    model = sel.model if sel else None
    engine = resolve_request_engine(
        provider=provider,
        model=model,
        api_key=api_key,
        settings=settings,
        fallback=fallback_engine,
        ollama_base_url=sel.ollama_base_url if sel else None,
    )

    # Build candidate hints from deterministic pre-filters.
    candidates: list[str] = []
    if settings.nb_source_terms:
        candidates.extend(extract_source_terms(source_text, source_lang))
    candidates.extend(extract_proper_nouns(translated_text))

    pairs = await engine.extract_glossary(
        source_text=source_text,
        translated_text=translated_text,
        source_lang=source_lang,
        candidates=candidates or None,
        model=model,
    )

    # TODO(vNext): Canonicalize duplicate glossary pairs.
    #
    # Example:
    #   天庭 -> Heavenly Court
    #   天庭 -> Heavenly Courts
    #
    # Current behavior:
    #   Both entries are accepted.
    #
    # Desired behavior:
    #   Choose a single canonical English spelling based on frequency in the
    #   translated chapter and merge metadata into one entry.
    #
    # Priority: Low.
    # Reason: Requires deterministic post-processing, but does not affect the
    # correctness of the current translation pipeline.

    return [
        GlossaryPairSuggestion(
            source_term=p.source_term,
            surface_form=p.surface_form,
            category=p.category,
            gender=p.gender,
            note=p.note,
        )
        for p in pairs
    ]


@router.post(
    "/references/{ref_id}/extract-glossary",
    response_model=list[GlossaryPairSuggestion],
)
async def extract_reference_glossary(
    ref_id: str,
    body: GlossaryExtractBody | None = None,
    store: StorageService = Depends(get_storage),
    fallback_engine: TranslationEngine = Depends(get_translation_engine),
    settings: Settings = Depends(get_settings),
    api_key: str | None = Depends(get_request_api_key),
):

    # Stateless path: both texts supplied in the body → skip the DB entirely.
    stateless = bool(body and body.source_text and body.translated_text)
    if stateless:
        source_text = body.source_text  # type: ignore[union-attr]
        translated_text = body.translated_text  # type: ignore[union-attr]
        source_lang = (body.source_lang if body else None) or "zh"
    else:
        rf = store.get_reference(ref_id)
        if not rf:
            raise HTTPException(404, "Translation not found")
        source_text = rf.source_text
        translated_text = rf.translated_text
        source_lang = rf.source_lang

    sel = body.selection if body else None
    provider = sel.provider if sel else None
    model = sel.model if sel else None
    engine = resolve_request_engine(
        provider=provider,
        model=model,
        api_key=api_key,
        settings=settings,
        fallback=fallback_engine,
        ollama_base_url=sel.ollama_base_url if sel else None,
    )

    # Build candidate hints from deterministic pre-filters.
    candidates: list[str] = []
    if settings.nb_source_terms:
        candidates.extend(extract_source_terms(source_text, source_lang))
    candidates.extend(extract_proper_nouns(translated_text))

    pairs = await engine.extract_glossary(
        source_text=source_text,
        translated_text=translated_text,
        source_lang=source_lang,
        candidates=candidates or None,
        model=model,
    )

    return [
        GlossaryPairSuggestion(
            source_term=p.source_term,
            surface_form=p.surface_form,
            category=p.category,
            gender=p.gender,
            note=p.note,
        )
        for p in pairs
    ]


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
    return find_pronoun_drift(tr.translated_text, glossary)


@router.delete("/translations/{tid}", status_code=204)
def delete_translation(tid: str, store: StorageService = Depends(get_storage)):
    if not store.delete_translation(tid):
        raise HTTPException(404, "Translation not found")


def _require_project(store: StorageService, pid: str) -> None:
    if not store.get_project(pid):
        raise HTTPException(404, "Project not found")
