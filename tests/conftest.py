"""
conftest.py — shared pytest fixtures.

IMPORTANT: env vars MUST be set before importing main so that module-level
constants (ADMIN_PASSWORD, RAG_ENABLED, etc.) are initialised correctly.
"""

import json
import os

# ── Set all env vars before any app import ────────────────────────────────────
os.environ.setdefault("ADMIN_PASSWORD", "")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("RAG_ENABLED", "false")
os.environ.setdefault("CHAT_HISTORY_ENABLED", "false")
os.environ.setdefault("FIREBASE_PROJECT_ID", "")
os.environ.setdefault("GEMINI_MODEL", "gemini-test-model")
os.environ.setdefault("GEMINI_VOICE", "Aoede")

# ── App import (after env vars are set) ───────────────────────────────────────
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from main import app  # noqa: E402  — intentional late import


# ─────────────────────────────────────────────────────────────────────────────
# HTTP client fixture
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
async def client():
    """Async httpx client wired to the FastAPI ASGI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# ─────────────────────────────────────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def admin_headers():
    """Headers that pass both verify_admin and _is_api_request checks.

    With ADMIN_PASSWORD="" the token value is not checked, but the header
    presence is needed so _is_api_request() returns True instead of falling
    back to the SPA response.
    """
    return {"x-admin-token": "test"}


# ─────────────────────────────────────────────────────────────────────────────
# RAG / Firebase mocks
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_rag_disabled(monkeypatch):
    """Force rag_engine.enabled = False for the duration of the test."""
    import main
    monkeypatch.setattr(main.rag_engine, "enabled", False)
    monkeypatch.setattr(main.rag_engine, "_vectorstore", None)


@pytest.fixture
def mock_firebase_disabled(monkeypatch):
    """Force chat_history.enabled = False for the duration of the test."""
    import main
    monkeypatch.setattr(main.chat_history, "enabled", False)


# ─────────────────────────────────────────────────────────────────────────────
# Temp data dir
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_data_dir(tmp_path):
    """Create sample scenes.json and nodes.json in a temporary directory."""
    scenes = [
        {"id": "scene-001", "panoNodeId": "node001", "name": "Phòng khách"},
        {"id": "scene-002", "panoNodeId": "node002", "name": "Phòng ngủ"},
    ]
    nodes = [
        {"nodeId": "node001", "label": "Phòng khách"},
        {"nodeId": "node002", "label": "Phòng ngủ"},
    ]
    (tmp_path / "scenes.json").write_text(json.dumps(scenes), encoding="utf-8")
    (tmp_path / "nodes.json").write_text(json.dumps(nodes), encoding="utf-8")
    return tmp_path


# ─────────────────────────────────────────────────────────────────────────────
# Data file patcher (used by admin CRUD tests)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def patched_data_files(temp_data_dir, monkeypatch):
    """Redirect main.SCENES_FILE and main.NODES_FILE to temp files."""
    import main
    monkeypatch.setattr(main, "SCENES_FILE", temp_data_dir / "scenes.json")
    monkeypatch.setattr(main, "NODES_FILE", temp_data_dir / "nodes.json")
    return temp_data_dir
