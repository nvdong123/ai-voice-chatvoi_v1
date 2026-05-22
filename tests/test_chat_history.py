"""
test_chat_history.py — Unit tests for ChatHistory.

All Firebase / Firestore calls are mocked.
The module-level _ENABLED=False and _PROJECT_ID="" (set via conftest env),
so every ChatHistory() starts with self.enabled=False.

Tests that need an enabled instance set it manually after construction
and inject a mock _db.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat_history as ch_module
from chat_history import ChatHistory


# ─── helpers ──────────────────────────────────────────────────────────────────

def _enabled_history() -> ChatHistory:
    """Return a ChatHistory with enabled=True and a mock Firestore client."""
    ch = ChatHistory()          # enabled=False (env defaults from conftest)
    ch.enabled = True
    ch._db = MagicMock()
    return ch


def _make_doc(exists: bool, data: dict = None):
    """Create a mock Firestore document snapshot."""
    doc = MagicMock()
    doc.exists = exists
    if data is not None:
        doc.to_dict.return_value = data
    return doc


# ─── TEST 1: __init__ when FIREBASE_PROJECT_ID not set ────────────────────────

def test_init_no_project_id(monkeypatch):
    monkeypatch.setattr(ch_module, "_ENABLED", True)
    monkeypatch.setattr(ch_module, "_PROJECT_ID", "")
    ch = ChatHistory()
    assert ch.enabled is False


# ─── TEST 2: __init__ when CHAT_HISTORY_ENABLED=false ─────────────────────────

def test_init_disabled_by_env(monkeypatch):
    monkeypatch.setattr(ch_module, "_ENABLED", False)
    ch = ChatHistory()
    assert ch.enabled is False


# ─── TEST 3: save_message() when disabled ─────────────────────────────────────

async def test_save_message_disabled():
    ch = ChatHistory()  # enabled=False
    # Must not raise
    await ch.save_message("session1", "user", "Hello")


# ─── TEST 4: save_message() with empty text ───────────────────────────────────

async def test_save_message_empty_text():
    ch = _enabled_history()
    await ch.save_message("session1", "user", "   ")
    # _db should never be touched
    ch._db.collection.assert_not_called()


# ─── TEST 5: save_message() creates new document ──────────────────────────────

async def test_save_message_new_document():
    ch = _enabled_history()

    mock_doc_ref = MagicMock()
    mock_snapshot = _make_doc(exists=False)
    mock_doc_ref.get.return_value = mock_snapshot

    ch._db.collection.return_value.document.return_value = mock_doc_ref

    # firebase-admin / google-cloud-firestore may not be installed in test env.
    # Inject a fake module so the `from google.cloud.firestore_v1 import ArrayUnion`
    # inside save_message() resolves without ImportError.
    import sys
    mock_fsv1 = MagicMock()
    with patch.dict(sys.modules, {"google.cloud.firestore_v1": mock_fsv1}):
        await ch.save_message("session1", "user", "Xin chao")

    mock_doc_ref.set.assert_called_once()
    call_data = mock_doc_ref.set.call_args[0][0]

    assert "created_at" in call_data
    assert "updated_at" in call_data
    assert "project" in call_data
    assert len(call_data["messages"]) == 1
    assert call_data["messages"][0]["role"] == "user"
    assert call_data["messages"][0]["text"] == "Xin chao"


# ─── TEST 6: save_message() updates existing document ─────────────────────────

async def test_save_message_existing_document():
    ch = _enabled_history()

    mock_doc_ref = MagicMock()
    mock_snapshot = _make_doc(exists=True)
    mock_doc_ref.get.return_value = mock_snapshot

    ch._db.collection.return_value.document.return_value = mock_doc_ref

    import sys
    mock_array_union_cls = MagicMock()
    mock_array_union_instance = MagicMock()
    mock_array_union_cls.return_value = mock_array_union_instance
    mock_fsv1 = MagicMock()
    mock_fsv1.ArrayUnion = mock_array_union_cls
    with patch.dict(sys.modules, {"google.cloud.firestore_v1": mock_fsv1}):
        await ch.save_message("session1", "assistant", "Da, toi co the giup gi?")

    mock_doc_ref.update.assert_called_once()
    update_data = mock_doc_ref.update.call_args[0][0]

    assert "updated_at" in update_data
    assert "messages" in update_data
    # messages value should be the ArrayUnion result
    assert update_data["messages"] is mock_array_union_instance


# ─── TEST 7: get_history() when disabled ──────────────────────────────────────

async def test_get_history_disabled():
    ch = ChatHistory()
    result = await ch.get_history("session1")
    assert result == []


# ─── TEST 8: get_history() session does not exist ─────────────────────────────

async def test_get_history_missing_session():
    ch = _enabled_history()

    mock_snapshot = _make_doc(exists=False)
    ch._db.collection.return_value.document.return_value.get.return_value = mock_snapshot

    result = await ch.get_history("nonexistent-session")
    assert result == []


# ─── TEST 9: get_history() returns messages ───────────────────────────────────

async def test_get_history_returns_messages():
    ch = _enabled_history()

    messages = [{"role": "user", "text": "hi", "timestamp": "2024-01-01T00:00:00+00:00"}]
    mock_snapshot = _make_doc(exists=True, data={"messages": messages})
    ch._db.collection.return_value.document.return_value.get.return_value = mock_snapshot

    result = await ch.get_history("session1")
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert result[0]["text"] == "hi"


# ─── TEST 10: list_sessions() when disabled ───────────────────────────────────

async def test_list_sessions_disabled():
    ch = ChatHistory()
    result = await ch.list_sessions()
    assert result == []


# ─── TEST 11: list_sessions() returns correct format ─────────────────────────

async def test_list_sessions_format():
    ch = _enabled_history()

    def _make_session_doc(sid, created, updated, msgs):
        d = MagicMock()
        d.id = sid
        d.to_dict.return_value = {
            "created_at": created,
            "updated_at": updated,
            "project": "test-project",
            "messages": msgs,
        }
        return d

    doc1 = _make_session_doc("sess-A", "2024-01-01T00:00:00+00:00", "2024-01-02T00:00:00+00:00", [1, 2])
    doc2 = _make_session_doc("sess-B", "2024-01-03T00:00:00+00:00", "2024-01-04T00:00:00+00:00", [1, 2, 3])

    (
        ch._db.collection.return_value
        .order_by.return_value
        .limit.return_value
        .stream.return_value
    ) = [doc1, doc2]

    result = await ch.list_sessions(limit=50)

    assert len(result) == 2
    for item in result:
        assert "session_id" in item
        assert "created_at" in item
        assert "updated_at" in item
        assert "message_count" in item

    assert result[0]["session_id"] == "sess-A"
    assert result[0]["message_count"] == 2
    assert result[1]["message_count"] == 3


# ─── TEST 12: delete_session() when disabled ──────────────────────────────────

async def test_delete_session_disabled():
    ch = ChatHistory()
    result = await ch.delete_session("session1")
    assert result is False


# ─── TEST 13: delete_session() success ────────────────────────────────────────

async def test_delete_session_success():
    ch = _enabled_history()

    mock_doc_ref = MagicMock()
    ch._db.collection.return_value.document.return_value = mock_doc_ref

    result = await ch.delete_session("session1")

    mock_doc_ref.delete.assert_called_once()
    assert result is True
