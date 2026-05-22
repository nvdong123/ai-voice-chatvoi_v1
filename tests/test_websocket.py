"""
test_websocket.py — WebSocket endpoint behaviour tests.

Uses starlette.testclient.TestClient.websocket_connect() (synchronous).
GeminiLive is fully mocked so no real API calls are made.

All tests are synchronous (def, not async def) because TestClient runs
the ASGI app in a thread — mixing it with pytest-asyncio would cause
event-loop conflicts.
"""

from unittest.mock import patch, MagicMock

import pytest

# TestClient is available via starlette (included in FastAPI)
from starlette.testclient import TestClient


# ─── Mock GeminiLive helpers ──────────────────────────────────────────────────

def _make_mock_gemini_class(extra_events=None):
    """
    Return a GeminiLive replacement whose start_session is an async generator
    that yields `extra_events` (list of dicts) then stops.
    """
    events = list(extra_events or [])

    class _MockGeminiLive:
        def __init__(self, *args, **kwargs):
            # Store init kwargs on the class so tests can inspect them
            _MockGeminiLive._last_init_kwargs = kwargs

        async def start_session(self, *args, **kwargs):
            for e in events:
                yield e

    _MockGeminiLive._last_init_kwargs = {}
    return _MockGeminiLive


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: connection sends session_info immediately
# ─────────────────────────────────────────────────────────────────────────────

def test_ws_receives_session_info():
    MockGemini = _make_mock_gemini_class()
    with patch("main.GeminiLive", MockGemini):
        client = TestClient(__import__("main").app)
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()

    assert msg["type"] == "session_info"
    assert msg.get("session_id") not in (None, "")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: custom session_id is preserved
# ─────────────────────────────────────────────────────────────────────────────

def test_ws_custom_session_id():
    MockGemini = _make_mock_gemini_class()
    with patch("main.GeminiLive", MockGemini):
        client = TestClient(__import__("main").app)
        with client.websocket_connect("/ws?session_id=my-custom-id") as ws:
            msg = ws.receive_json()

    assert msg["type"] == "session_info"
    assert msg["session_id"] == "my-custom-id"


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: auto-generated session_id when not provided
# ─────────────────────────────────────────────────────────────────────────────

def test_ws_auto_session_id():
    MockGemini = _make_mock_gemini_class()
    with patch("main.GeminiLive", MockGemini):
        client = TestClient(__import__("main").app)
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()

    assert msg["type"] == "session_info"
    sid = msg.get("session_id", "")
    assert isinstance(sid, str) and len(sid) > 0


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: RAG context is injected into system_instruction
# ─────────────────────────────────────────────────────────────────────────────

def test_ws_rag_context_injected(monkeypatch):
    import main

    monkeypatch.setattr(main.rag_engine, "has_documents", lambda: True)
    monkeypatch.setattr(main.rag_engine, "get_all_context", lambda: "--- context ---")

    MockGemini = _make_mock_gemini_class()

    with patch("main.GeminiLive", MockGemini):
        client = TestClient(main.app)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # session_info

    system_instruction = MockGemini._last_init_kwargs.get("system_instruction", "")
    assert "--- context ---" in system_instruction


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5: RAG disabled → effective_prompt = original SYSTEM_PROMPT
# ─────────────────────────────────────────────────────────────────────────────

def test_ws_rag_disabled_uses_original_prompt(monkeypatch):
    import main

    monkeypatch.setattr(main.rag_engine, "has_documents", lambda: False)

    MockGemini = _make_mock_gemini_class()

    with patch("main.GeminiLive", MockGemini):
        client = TestClient(main.app)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()

    system_instruction = MockGemini._last_init_kwargs.get("system_instruction", "")
    # Should equal exactly SYSTEM_PROMPT, no appended RAG context
    assert system_instruction == main.SYSTEM_PROMPT


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6: RAG error does not crash the WebSocket connection
# ─────────────────────────────────────────────────────────────────────────────

def test_ws_rag_error_does_not_crash(monkeypatch):
    import main

    def _raise():
        raise RuntimeError("ChromaDB is down")

    monkeypatch.setattr(main.rag_engine, "has_documents", _raise)

    MockGemini = _make_mock_gemini_class()

    with patch("main.GeminiLive", MockGemini):
        client = TestClient(main.app)
        # Must not raise — WebSocket should still be accepted
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()

    assert msg["type"] == "session_info"


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7: ChatHistory save_message error does not close the session abruptly
# ─────────────────────────────────────────────────────────────────────────────

def test_ws_chat_history_error_does_not_crash(monkeypatch):
    import main

    async def _raise(*args, **kwargs):
        raise RuntimeError("Firebase is unavailable")

    monkeypatch.setattr(main.chat_history, "save_message", _raise)

    # Generator that yields one user-text event to trigger save_message path
    user_event = {"type": "user", "text": "Xin chào"}
    MockGemini = _make_mock_gemini_class(extra_events=[user_event])

    with patch("main.GeminiLive", MockGemini):
        client = TestClient(main.app)
        with client.websocket_connect("/ws") as ws:
            session_msg = ws.receive_json()   # session_info
            user_msg = ws.receive_json()      # forwarded user event

    # Both messages received — no crash
    assert session_msg["type"] == "session_info"
    assert user_msg["type"] == "user"
