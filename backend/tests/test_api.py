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


def test_glossary_upsert_and_update(client):
    pid = _create_project(client)
    r = client.post(
        f"/api/projects/{pid}/glossary",
        json={"source_term": "林", "translation": "Lin"},
    )
    assert r.status_code == 201
    entry_id = r.json()["id"]
    # duplicate source_term upserts rather than duplicating
    client.post(
        f"/api/projects/{pid}/glossary",
        json={"source_term": "林", "translation": "Rin"},
    )
    entries = client.get(f"/api/projects/{pid}/glossary").json()
    assert len(entries) == 1 and entries[0]["translation"] == "Rin"
    upd = client.put(f"/api/glossary/{entry_id}", json={"translation": "Lyn"})
    assert upd.status_code == 200 and upd.json()["translation"] == "Lyn"


def test_translate_streams_and_autosaves(client):
    pid = _create_project(client)
    client.post(
        f"/api/projects/{pid}/glossary",
        json={"source_term": "林", "translation": "Lin"},
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
