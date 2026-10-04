"""Unit tests for the SQLite storage backend."""

from __future__ import annotations

import pytest

from app.storage.sqlite_store import SQLiteStorage


@pytest.fixture()
def store(tmp_path):
    return SQLiteStorage(str(tmp_path / "test.db"))


def test_project_crud(store):
    assert store.list_projects() == []
    p = store.create_project("Cultivation Series", "zh")
    assert p.id and p.name == "Cultivation Series" and p.source_lang == "zh"
    assert len(store.list_projects()) == 1
    assert store.get_project(p.id).name == "Cultivation Series"
    assert store.delete_project(p.id) is True
    assert store.get_project(p.id) is None
    assert store.delete_project("missing") is False


def test_reference_crud_and_cascade(store):
    p = store.create_project("S", None)
    r = store.add_reference(p.id, "Ch1", "Once upon a time")
    assert r.project_id == p.id
    assert len(store.list_references(p.id)) == 1
    # cascade: deleting the project removes its references
    store.delete_project(p.id)
    assert store.list_references(p.id) == []


def test_glossary_upsert_uniqueness(store):
    p = store.create_project("S", "ja")
    e1 = store.upsert_glossary(p.id, "林", "Lin", None)
    # same source_term upserts (updates), does not duplicate
    e2 = store.upsert_glossary(p.id, "林", "Rin", "name changed")
    entries = store.list_glossary(p.id)
    assert len(entries) == 1
    assert e1.id == e2.id
    assert entries[0].translation == "Rin"
    assert entries[0].note == "name changed"


def test_glossary_update_and_delete(store):
    p = store.create_project("S", None)
    e = store.upsert_glossary(p.id, "天", "Heaven", None)
    updated = store.update_glossary(e.id, translation="Sky", note=None)
    assert updated.translation == "Sky"
    assert store.update_glossary("missing", "x", None) is None
    assert store.delete_glossary(e.id) is True
    assert store.list_glossary(p.id) == []


def test_translation_save_and_list(store):
    p = store.create_project("S", "zh")
    t = store.save_translation(p.id, "zh", "你好", "Hello", "qwen3.5:0.8b")
    assert t.output_text == "Hello"
    assert len(store.list_translations(p.id)) == 1
    assert store.get_translation(t.id).raw_text == "你好"
    # cascade on project delete
    store.delete_project(p.id)
    assert store.list_translations(p.id) == []


def test_translation_delete(store):
    p = store.create_project("S", "zh")
    t = store.save_translation(p.id, "zh", "你好", "Hello", "qwen3.5:0.8b")
    assert store.delete_translation(t.id) is True
    assert store.get_translation(t.id) is None
    assert store.list_translations(p.id) == []
    # deleting a missing id returns False
    assert store.delete_translation("missing") is False
