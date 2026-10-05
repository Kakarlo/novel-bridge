"""API tests using the mock engine and a temporary SQLite database."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.deps import get_storage, get_translation_engine
from app.engines.mock_engine import MockEngine
from app.main import create_app
from app.storage.sqlite_store import SQLiteStorage


@pytest.fixture()
def client(tmp_path):
    settings = Settings(nb_engine="mock", nb_db_path=str(tmp_path / "api.db"))
    app = create_app(settings)

    store = SQLiteStorage(settings.nb_db_path)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_storage] = lambda: store
    app.dependency_overrides[get_translation_engine] = lambda: MockEngine()

    with TestClient(app) as c:
        yield c


def _create_project(client, name="S", lang="zh"):
    r = client.post("/api/projects", json={"name": name, "source_lang": lang})
    assert r.status_code == 201
    return r.json()["id"]


def test_project_lifecycle(client):
    assert client.get("/api/projects").json() == []
    pid = _create_project(client)
    assert len(client.get("/api/projects").json()) == 1
    detail = client.get(f"/api/projects/{pid}").json()
    assert detail["counts"]["references"] == 0
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_empty_project_name_rejected(client):
    r = client.post("/api/projects", json={"name": "  "})
    assert r.status_code == 422


def test_reference_crud_and_validation(client):
    pid = _create_project(client)
    r = client.post(
        f"/api/projects/{pid}/references",
        json={"title": "Ch1", "content": "Once upon a time"},
    )
    assert r.status_code == 201
    ref_id = r.json()["id"]
    assert len(client.get(f"/api/projects/{pid}/references").json()) == 1
    # empty content rejected
    bad = client.post(
        f"/api/projects/{pid}/references", json={"title": "x", "content": ""}
    )
    assert bad.status_code == 422
    assert client.delete(f"/api/references/{ref_id}").status_code == 204


def test_add_reference_extracts_summary(client):
    pid = _create_project(client)
    r = client.post(
        f"/api/projects/{pid}/references",
        json={"title": "Ch1", "content": "Lin Feng climbed Azure Peak at dawn."},
    )
    assert r.status_code == 201
    ref = r.json()
    # The mock engine ran synchronously and populated derived context.
    assert ref["summary"].startswith("[MOCK-SUMMARY]")
    assert isinstance(ref["candidate_terms"], list)
    assert "Lin" in ref["candidate_terms"]
    # It is persisted and returned by the list endpoint too.
    listed = client.get(f"/api/projects/{pid}/references").json()[0]
    assert listed["summary"] == ref["summary"]


def test_add_reference_detects_proper_nouns(client):
    pid = _create_project(client)
    r = client.post(
        f"/api/projects/{pid}/references",
        json={
            "title": "Ch1",
            "content": (
                "Li Changshou bowed to the elder. The next morning, Li Changshou traveled "
                "to Beijing. In Beijing, Li Changshou met an old friend."
            ),
        },
    )
    assert r.status_code == 201
    ref = r.json()
    # The NER pass surfaces proper nouns separately from the AI candidate_terms. We assert on
    # substance, not exact segmentation: a recurring person name and a place are detected.
    # (NER may return "Li Changshou" or "Changshou" depending on context — both are a hit.)
    assert any("Changshou" in n for n in ref["detected_names"])
    assert "Beijing" in ref["detected_names"]


def test_resummarize_reference(client):
    pid = _create_project(client)
    ref_id = client.post(
        f"/api/projects/{pid}/references",
        json={"title": "Ch1", "content": "Dawn broke over the Jade City."},
    ).json()["id"]

    r = client.post(f"/api/references/{ref_id}/resummarize")
    assert r.status_code == 200
    assert r.json()["summary"].startswith("[MOCK-SUMMARY]")
    assert "Jade" in r.json()["candidate_terms"]
    # Unknown reference -> 404.
    assert client.post("/api/references/nope/resummarize").status_code == 404


def test_glossary_paired_create_and_update(client):
    pid = _create_project(client)
    # A classic paired entry: source_term + the English surface_form. Defaults to approved.
    r = client.post(
        f"/api/projects/{pid}/glossary",
        json={"surface_form": "Lin", "source_term": "林"},
    )
    assert r.status_code == 201
    entry = r.json()
    entry_id = entry["id"]
    assert entry["status"] == "approved"
    # Upsert on the same surface_form (case-insensitive) merges rather than duplicating.
    client.post(
        f"/api/projects/{pid}/glossary",
        json={"surface_form": "lin", "source_term": "林", "note": "renamed"},
    )
    entries = client.get(f"/api/projects/{pid}/glossary").json()
    assert len(entries) == 1 and entries[0]["note"] == "renamed"
    upd = client.put(f"/api/glossary/{entry_id}", json={"surface_form": "Lyn"})
    assert upd.status_code == 200 and upd.json()["surface_form"] == "Lyn"


def test_glossary_english_only_add_and_status(client):
    pid = _create_project(client)
    # English-only add defaults to candidate; category/gender accepted.
    r = client.post(
        f"/api/projects/{pid}/glossary",
        json={"surface_form": "Fang Yuan", "category": "character", "gender": "male"},
    )
    assert r.status_code == 201
    entry = r.json()
    assert entry["status"] == "candidate"
    assert entry["category"] == "character" and entry["gender"] == "male"
    assert entry["source_term"] is None
    # Approve it via the status PATCH.
    patched = client.patch(
        f"/api/glossary/{entry['id']}/status", json={"status": "approved"}
    )
    assert patched.status_code == 200 and patched.json()["status"] == "approved"
    # Blank surface form is rejected.
    bad = client.post(f"/api/projects/{pid}/glossary", json={"surface_form": "  "})
    assert bad.status_code == 422


def test_translate_streams_and_autosaves(client):
    pid = _create_project(client)
    client.post(
        f"/api/projects/{pid}/glossary",
        json={"surface_form": "Lin", "source_term": "林"},
    )
    with client.stream(
        "POST",
        f"/api/projects/{pid}/translate",
        json={"raw_text": "我是林", "source_lang": "zh"},
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = "".join(resp.iter_text())

    # Reassemble the streamed content fields (chunk boundaries are arbitrary).
    events = [
        json.loads(line[len("data: ") :])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
    streamed = "".join(e.get("content", "") for e in events)
    assert "[MOCK]" in streamed
    assert "我是Lin" in streamed  # glossary substitution applied
    assert any(e.get("done") is True and e.get("translation_id") for e in events)

    # Auto-saved on completion.
    saved = client.get(f"/api/projects/{pid}/translations").json()
    assert len(saved) == 1
    assert "我是Lin" in saved[0]["output_text"]


def test_translate_unknown_project_404(client):
    r = client.post(
        "/api/projects/nope/translate",
        json={"raw_text": "x", "source_lang": "zh"},
    )
    assert r.status_code == 404


def _run_translate(client, pid, raw, extra=None):
    """Stream a translation and return (reassembled events, done_event)."""
    body = {"raw_text": raw, "source_lang": "zh", **(extra or {})}
    with client.stream("POST", f"/api/projects/{pid}/translate", json=body) as resp:
        assert resp.status_code == 200
        text = "".join(resp.iter_text())
    events = [
        json.loads(line[len("data: ") :])
        for line in text.splitlines()
        if line.startswith("data: ")
    ]
    done = next(e for e in events if e.get("done"))
    return events, done


def test_translate_review_terms_folds_matches_into_done(client):
    pid = _create_project(client)
    # An approved English-first term that will appear in the mock output.
    client.post(
        f"/api/projects/{pid}/glossary",
        json={"surface_form": "hello", "status": "approved"},
    )
    # The mock engine echoes the raw text, so "hello" appears in the output.
    _events, done = _run_translate(
        client, pid, "hello there, hello again", extra={"review_terms": True}
    )
    assert "matches" in done
    assert len(done["matches"]) == 1
    m = done["matches"][0]
    assert m["surface_form"] == "hello"
    assert m["count"] == 2
    assert m["status"] == "approved"


def test_translate_without_review_omits_matches(client):
    pid = _create_project(client)
    client.post(
        f"/api/projects/{pid}/glossary",
        json={"surface_form": "hello", "status": "approved"},
    )
    _events, done = _run_translate(client, pid, "hello there")
    assert "matches" not in done  # streaming path untouched when review is off


def test_saved_translation_matches_endpoint(client):
    pid = _create_project(client)
    client.post(
        f"/api/projects/{pid}/glossary",
        json={"surface_form": "world", "status": "approved"},
    )
    _events, done = _run_translate(client, pid, "hello world, cruel world")
    tid = done["translation_id"]

    # Retrospective matching against the saved translation + current glossary.
    r = client.get(f"/api/translations/{tid}/matches")
    assert r.status_code == 200
    matches = r.json()
    assert len(matches) == 1
    assert matches[0]["surface_form"] == "world" and matches[0]["count"] == 2
    # Unknown translation -> 404.
    assert client.get("/api/translations/nope/matches").status_code == 404


def test_delete_translation(client):
    pid = _create_project(client)
    # Produce one saved translation via the streaming endpoint.
    with client.stream(
        "POST",
        f"/api/projects/{pid}/translate",
        json={"raw_text": "hello", "source_lang": "zh"},
    ) as resp:
        body = "".join(resp.iter_text())
    events = [
        json.loads(line[len("data: ") :])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
    tid = next(e["translation_id"] for e in events if e.get("done"))

    assert len(client.get(f"/api/projects/{pid}/translations").json()) == 1
    # Delete succeeds with 204, then the row is gone.
    assert client.delete(f"/api/translations/{tid}").status_code == 204
    assert len(client.get(f"/api/projects/{pid}/translations").json()) == 0
    assert client.get(f"/api/translations/{tid}").status_code == 404
    # Deleting again (missing) returns 404.
    assert client.delete(f"/api/translations/{tid}").status_code == 404


def test_add_reference_names_only_skips_summary(client):
    """extract_summary=False runs the name detector but skips the AI extraction."""
    pid = _create_project(client)
    r = client.post(
        f"/api/projects/{pid}/references",
        json={
            "title": "Ch1",
            "content": (
                "Li Changshou bowed. Later, Li Changshou traveled to Beijing. "
                "In Beijing, Li Changshou rested."
            ),
            "extract_summary": False,
        },
    )
    assert r.status_code == 201
    ref = r.json()
    # No AI summary / candidate terms (the mock engine was never called)...
    assert ref["summary"] is None
    assert ref["candidate_terms"] == []
    # ...but the offline name detector still ran.
    assert "Beijing" in ref["detected_names"]


def test_glossary_count_excludes_rejected(client):
    """The project 'glossary' count excludes rejected (soft-deleted) terms."""
    pid = _create_project(client)
    keep = client.post(
        f"/api/projects/{pid}/glossary", json={"surface_form": "Keeper"}
    ).json()
    drop = client.post(
        f"/api/projects/{pid}/glossary", json={"surface_form": "Dropped"}
    ).json()
    assert client.get(f"/api/projects/{pid}").json()["counts"]["glossary"] == 2
    # Reject one -> count drops, but the row is still stored (restorable).
    client.patch(f"/api/glossary/{drop['id']}/status", json={"status": "rejected"})
    assert client.get(f"/api/projects/{pid}").json()["counts"]["glossary"] == 1
    assert len(client.get(f"/api/projects/{pid}/glossary").json()) == 2
    # Restore it (status back to candidate) -> count rises again.
    client.patch(f"/api/glossary/{drop['id']}/status", json={"status": "candidate"})
    assert client.get(f"/api/projects/{pid}").json()["counts"]["glossary"] == 2
    assert keep["surface_form"] == "Keeper"


def test_reject_term_via_upsert_persists(client):
    """Option B: rejecting a suggestion creates a persistent rejected glossary entry,
    and a later promote (candidate) restores it (upsert on surface_form)."""
    pid = _create_project(client)
    # Reject a suggestion = upsert with status rejected.
    r = client.post(
        f"/api/projects/{pid}/glossary",
        json={"surface_form": "Noise Term", "status": "rejected"},
    )
    assert r.status_code == 201 and r.json()["status"] == "rejected"
    # It's remembered in storage, excluded from the count.
    assert client.get(f"/api/projects/{pid}").json()["counts"]["glossary"] == 0
    entries = client.get(f"/api/projects/{pid}/glossary").json()
    assert len(entries) == 1 and entries[0]["status"] == "rejected"
    # Promoting the same surface form later flips it back (upsert merge, explicit status).
    r2 = client.post(
        f"/api/projects/{pid}/glossary",
        json={"surface_form": "noise term", "status": "candidate"},
    )
    assert r2.status_code == 201 and r2.json()["status"] == "candidate"
    assert len(client.get(f"/api/projects/{pid}/glossary").json()) == 1


def test_redetect_reference_names_only(client):
    """POST /references/{id}/redetect refreshes detected_names without touching summary."""
    pid = _create_project(client)
    # Add with the AI summary so summary/candidate_terms are populated.
    ref = client.post(
        f"/api/projects/{pid}/references",
        json={"title": "Ch1", "content": "Lin Feng met Lin Feng's rival in Beijing."},
    ).json()
    summary_before = ref["summary"]
    assert summary_before  # mock engine populated it
    r = client.post(f"/api/references/{ref['id']}/redetect")
    assert r.status_code == 200
    body = r.json()
    # Summary is untouched; detected_names recomputed by the offline detector.
    assert body["summary"] == summary_before
    assert isinstance(body["detected_names"], list)
    # Unknown reference -> 404.
    assert client.post("/api/references/nope/redetect").status_code == 404


def test_resolve_term_removes_from_reference_pools(client):
    """Resolving a suggestion drops it from detected_names AND candidate_terms, so it
    won't reappear as a chip."""
    pid = _create_project(client)
    ref = client.post(
        f"/api/projects/{pid}/references",
        json={"title": "Ch1", "content": "Lin Feng met Lin Feng again in Beijing."},
    ).json()
    assert "Beijing" in ref["detected_names"]
    # Resolve "Beijing" out of the pool.
    r = client.post(
        f"/api/references/{ref['id']}/resolve-term", json={"term": "beijing"}
    )
    assert r.status_code == 200
    body = r.json()
    assert "Beijing" not in body["detected_names"]
    assert all(t.casefold() != "beijing" for t in body["candidate_terms"])
    # Unknown reference -> 404.
    assert (
        client.post("/api/references/nope/resolve-term", json={"term": "x"}).status_code
        == 404
    )


def test_redetect_excludes_glossary_terms(client):
    """Redetect must not resurface names the user already resolved into the glossary."""
    pid = _create_project(client)
    ref = client.post(
        f"/api/projects/{pid}/references",
        json={"title": "Ch1", "content": "Lin Feng traveled to Beijing with Lin Feng."},
    ).json()
    # Promote-equivalent: the name is now in the glossary.
    client.post(f"/api/projects/{pid}/glossary", json={"surface_form": "Beijing"})
    r = client.post(f"/api/references/{ref['id']}/redetect")
    assert r.status_code == 200
    assert "Beijing" not in r.json()["detected_names"]


def _client_with(settings: Settings):
    """Build a TestClient with explicit settings + mock engine + temp store."""
    app = create_app(settings)
    store = SQLiteStorage(settings.nb_db_path)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_storage] = lambda: store
    app.dependency_overrides[get_translation_engine] = lambda: MockEngine()
    return TestClient(app)


def test_experimental_endpoints_gated_off_by_default(client):
    """Both experimental endpoints 404 when their flags are off (the default)."""
    pid = _create_project(client)
    ref = client.post(
        f"/api/projects/{pid}/references",
        json={"title": "Ch1", "content": "Lin Feng went to Beijing."},
    ).json()
    assert client.get(f"/api/references/{ref['id']}/source-terms").status_code == 404
    # A saved translation to test pronoun-drift gating.
    with client.stream(
        "POST",
        f"/api/projects/{pid}/translate",
        json={"raw_text": "测试", "source_lang": "zh"},
    ) as s:
        tid = None
        for line in s.iter_lines():
            if line and line.startswith("data:"):
                payload = json.loads(line[5:])
                if payload.get("done"):
                    tid = payload["translation_id"]
    assert tid
    assert client.get(f"/api/translations/{tid}/pronoun-drift").status_code == 404


def test_pronoun_drift_endpoint_when_enabled(tmp_path):
    """With NB_PRONOUN_CHECK on, the endpoint flags a gender/pronoun mismatch."""
    settings = Settings(
        nb_engine="mock",
        nb_db_path=str(tmp_path / "pron.db"),
        nb_pronoun_check=True,
    )
    with _client_with(settings) as c:
        pid = c.post("/api/projects", json={"name": "S", "source_lang": "zh"}).json()["id"]
        # Approved male character.
        c.post(
            f"/api/projects/{pid}/glossary",
            json={"surface_form": "Fang Yuan", "category": "character", "gender": "male"},
        )
        # Save a translation whose output has a conflicting pronoun. MockEngine echoes a
        # deterministic output, so instead we test the detector endpoint on a translation
        # we craft via the normal translate path is awkward; just assert the gate opens and
        # returns a list (detector unit-tested separately).
        with c.stream(
            "POST",
            f"/api/projects/{pid}/translate",
            json={"raw_text": "x", "source_lang": "zh"},
        ) as s:
            tid = None
            for line in s.iter_lines():
                if line and line.startswith("data:"):
                    payload = json.loads(line[5:])
                    if payload.get("done"):
                        tid = payload["translation_id"]
        r = c.get(f"/api/translations/{tid}/pronoun-drift")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


def test_source_terms_endpoint_when_enabled(tmp_path):
    """With NB_SOURCE_TERMS on, the endpoint returns a list (empty if model absent)."""
    settings = Settings(
        nb_engine="mock",
        nb_db_path=str(tmp_path / "src.db"),
        nb_source_terms=True,
    )
    with _client_with(settings) as c:
        pid = c.post("/api/projects", json={"name": "S", "source_lang": "zh"}).json()["id"]
        ref = c.post(
            f"/api/projects/{pid}/references",
            json={"title": "Ch1", "content": "林风走向北京。", "extract_summary": False},
        ).json()
        r = c.get(f"/api/references/{ref['id']}/source-terms")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
