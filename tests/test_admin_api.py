"""
test_admin_api.py — Integration tests for admin HTTP endpoints.

Uses httpx.AsyncClient with ASGITransport (no real network calls).
ADMIN_PASSWORD="" → auth is disabled.
RAG and Firebase singletons are patched where needed.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────

async def test_login_correct_password(client, monkeypatch):
    import main
    monkeypatch.setattr(main, "ADMIN_PASSWORD", "secret")
    resp = await client.post("/admin/login", json={"password": "secret"})
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data


async def test_login_wrong_password(client, monkeypatch):
    import main
    monkeypatch.setattr(main, "ADMIN_PASSWORD", "secret")
    resp = await client.post("/admin/login", json={"password": "wrong"})
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────────────────────────────────────────

async def test_get_prompt(client, admin_headers, tmp_path, monkeypatch):
    import main
    pf = tmp_path / "prompt.txt"
    pf.write_text("Bạn là trợ lý AI.", encoding="utf-8")
    monkeypatch.setattr(main, "PROMPT_FILE", pf)
    monkeypatch.setattr(main, "SYSTEM_PROMPT", "Bạn là trợ lý AI.")

    resp = await client.get("/admin/prompt", headers=admin_headers)
    assert resp.status_code == 200
    assert "prompt" in resp.json()


async def test_post_prompt_saves_and_get_returns_it(client, admin_headers, tmp_path, monkeypatch):
    import main
    pf = tmp_path / "prompt.txt"
    pf.write_text("Original", encoding="utf-8")
    monkeypatch.setattr(main, "PROMPT_FILE", pf)
    monkeypatch.setattr(main, "SYSTEM_PROMPT", "Original")

    # Save new prompt
    resp = await client.post(
        "/admin/prompt",
        json={"prompt": "New system prompt"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert "message" in resp.json()

    # GET should return the new value
    resp2 = await client.get("/admin/prompt", headers=admin_headers)
    assert resp2.json()["prompt"] == "New system prompt"


async def test_post_prompt_empty_body(client, admin_headers):
    resp = await client.post(
        "/admin/prompt",
        json={"prompt": ""},
        headers=admin_headers,
    )
    assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

async def test_get_config(client, admin_headers, tmp_path, monkeypatch):
    import main
    pf = tmp_path / "prompt.txt"
    pf.write_text("Prompt", encoding="utf-8")
    monkeypatch.setattr(main, "PROMPT_FILE", pf)

    resp = await client.get("/admin/config", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "model" in data
    assert "voice" in data
    assert "availableVoices" in data
    assert "platform" in data


async def test_post_config_valid_model(client, admin_headers, monkeypatch):
    import main
    monkeypatch.setattr(main, "_CURRENT_MODEL", "gemini-test-model")
    monkeypatch.setattr(main, "_CURRENT_VOICE", "Aoede")

    resp = await client.post(
        "/admin/config",
        json={"model": "gemini-new-model", "voice": "Puck"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "gemini-new-model"


async def test_post_config_invalid_voice(client, admin_headers):
    resp = await client.post(
        "/admin/config",
        json={"model": "any-model", "voice": "InvalidVoice"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_post_config_missing_model(client, admin_headers):
    resp = await client.post(
        "/admin/config",
        json={"voice": "Aoede"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# Scenes CRUD
# ─────────────────────────────────────────────────────────────────────────────

async def test_list_scenes(client, admin_headers, patched_data_files):
    resp = await client.get("/admin/scenes", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2  # from temp_data_dir fixture


async def test_create_scene(client, admin_headers, patched_data_files):
    new_scene = {"id": "scene-new", "panoNodeId": "node999", "name": "Bếp"}
    resp = await client.post("/admin/scenes", json=new_scene, headers=admin_headers)
    assert resp.status_code == 201
    assert resp.json()["id"] == "scene-new"


async def test_create_scene_duplicate_id(client, admin_headers, patched_data_files):
    # scene-001 already exists
    dup = {"id": "scene-001", "panoNodeId": "node777", "name": "Dup"}
    resp = await client.post("/admin/scenes", json=dup, headers=admin_headers)
    assert resp.status_code == 409


async def test_update_scene(client, admin_headers, patched_data_files):
    resp = await client.put(
        "/admin/scenes/scene-001",
        json={"name": "Phòng khách mới"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Phòng khách mới"


async def test_delete_scene(client, admin_headers, patched_data_files):
    resp = await client.delete("/admin/scenes/scene-001", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


async def test_update_scene_not_found(client, admin_headers, patched_data_files):
    resp = await client.put(
        "/admin/scenes/nonexistent",
        json={"name": "X"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# RAG documents
# ─────────────────────────────────────────────────────────────────────────────

async def test_rag_list_documents_empty(client, admin_headers, monkeypatch):
    import main
    monkeypatch.setattr(main.rag_engine, "list_documents", lambda: [])

    resp = await client.get("/admin/rag/documents", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_rag_upload_valid_txt(client, admin_headers, tmp_path, monkeypatch):
    import main
    monkeypatch.setenv("RAG_DOCS_DIR", str(tmp_path))
    monkeypatch.setattr(
        main.rag_engine,
        "ingest_file",
        lambda fp, fn: {"chunks_added": 3, "filename": fn},
    )

    resp = await client.post(
        "/admin/rag/upload",
        files={"file": ("brochure.txt", b"Test document content", "text/plain")},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["chunks_added"] == 3
    assert data["filename"] == "brochure.txt"


async def test_rag_upload_invalid_extension(client, admin_headers):
    resp = await client.post(
        "/admin/rag/upload",
        files={"file": ("malware.exe", b"\x00\x01\x02", "application/octet-stream")},
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_rag_upload_no_file_field(client, admin_headers):
    resp = await client.post(
        "/admin/rag/upload",
        data={"other_field": "value"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_rag_delete_document(client, admin_headers, tmp_path, monkeypatch):
    import main
    monkeypatch.setenv("RAG_DOCS_DIR", str(tmp_path))
    monkeypatch.setattr(
        main.rag_engine,
        "delete_file",
        lambda fn: {"deleted": 1, "filename": fn},
    )

    resp = await client.delete("/admin/rag/documents/brochure.txt", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Chat history
# ─────────────────────────────────────────────────────────────────────────────

async def test_history_list_empty(client, admin_headers, monkeypatch):
    import main

    async def mock_list(limit=50, project=None):
        return []

    monkeypatch.setattr(main.chat_history, "list_sessions", mock_list)

    resp = await client.get("/admin/history", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_history_get_session(client, admin_headers, monkeypatch):
    import main

    async def mock_get(session_id):
        return [{"role": "user", "text": "hi", "timestamp": "2024-01-01T00:00:00+00:00"}]

    monkeypatch.setattr(main.chat_history, "get_history", mock_get)

    resp = await client.get("/admin/history/test-session-id", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "test-session-id"
    assert len(data["messages"]) == 1
    assert data["messages"][0]["role"] == "user"


async def test_history_delete_session(client, admin_headers, monkeypatch):
    import main

    async def mock_delete(session_id):
        return True

    monkeypatch.setattr(main.chat_history, "delete_session", mock_delete)

    resp = await client.delete("/admin/history/test-session-id", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
