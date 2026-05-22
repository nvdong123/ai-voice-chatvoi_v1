"""
chat_history.py — Firebase Firestore chat history manager.

Stores per-session chat messages without requiring user login.
Gracefully degrades (disabled) when Firebase is not configured.
"""

import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Config from env ──────────────────────────────────────────────────────────
_ENABLED              = os.getenv("CHAT_HISTORY_ENABLED", "true").lower() == "true"
_CREDENTIALS_JSON     = os.getenv("FIREBASE_CREDENTIALS_JSON", "")
_CREDENTIALS_BASE64   = os.getenv("FIREBASE_CREDENTIALS_BASE64", "")
_PROJECT_ID           = os.getenv("FIREBASE_PROJECT_ID", "")
_PROJECT_NAME         = os.getenv("PROJECT_NAME", "realestate-chatbot")
_COLLECTION           = "chat_sessions"


class ChatHistory:
    """Async Firebase Firestore wrapper for session-based chat history."""

    def __init__(self) -> None:
        self.enabled = False

        if not _ENABLED:
            logger.info("ChatHistory disabled (CHAT_HISTORY_ENABLED=false)")
            return

        if not _PROJECT_ID:
            logger.warning(
                "ChatHistory disabled — FIREBASE_PROJECT_ID not set"
            )
            return

        try:
            self._db = self._init_firebase()
            self.enabled = True
            logger.info("ChatHistory initialised (project=%s)", _PROJECT_ID)
        except Exception as exc:
            logger.warning("ChatHistory init failed — history disabled: %s", exc)

    # ── private ───────────────────────────────────────────────────────────────

    def _init_firebase(self):
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            cred_obj = self._load_credentials()
            firebase_admin.initialize_app(cred_obj, {"projectId": _PROJECT_ID})

        return firestore.client()

    def _load_credentials(self):
        from firebase_admin import credentials

        # 1. Path to JSON file
        if _CREDENTIALS_JSON:
            from pathlib import Path
            path = Path(_CREDENTIALS_JSON)
            if path.exists():
                return credentials.Certificate(str(path))
            logger.warning("FIREBASE_CREDENTIALS_JSON path not found: %s", path)

        # 2. Base64-encoded JSON string
        if _CREDENTIALS_BASE64:
            decoded = base64.b64decode(_CREDENTIALS_BASE64).decode("utf-8")
            info = json.loads(decoded)
            return credentials.Certificate(info)

        # 3. Application Default Credentials (GCP / Cloud Run)
        return credentials.ApplicationDefault()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── public async methods ──────────────────────────────────────────────────

    async def save_message(
        self,
        session_id: str,
        role: str,
        text: str,
    ) -> None:
        """Append a message to the session document."""
        if not self.enabled or not text.strip():
            return
        try:
            from google.cloud.firestore_v1 import ArrayUnion
            now = self._now()
            doc_ref = self._db.collection(_COLLECTION).document(session_id)
            doc = doc_ref.get()

            message = {
                "role": role,
                "text": text.strip(),
                "timestamp": now,
                "audio_url": None,
            }

            if doc.exists:
                doc_ref.update({
                    "updated_at": now,
                    "messages": ArrayUnion([message]),
                })
            else:
                doc_ref.set({
                    "created_at": now,
                    "updated_at": now,
                    "project": _PROJECT_NAME,
                    "messages": [message],
                })
        except Exception as exc:
            logger.error("ChatHistory.save_message error (session=%s): %s", session_id, exc)

    async def get_history(self, session_id: str) -> list:
        """Return messages list for a session."""
        if not self.enabled:
            return []
        try:
            doc = self._db.collection(_COLLECTION).document(session_id).get()
            if not doc.exists:
                return []
            return doc.to_dict().get("messages", [])
        except Exception as exc:
            logger.error("ChatHistory.get_history error (session=%s): %s", session_id, exc)
            return []

    async def list_sessions(self, limit: int = 50, project: Optional[str] = None) -> list:
        """Return recent sessions ordered by updated_at desc."""
        if not self.enabled:
            return []
        try:
            query = (
                self._db.collection(_COLLECTION)
                .order_by("updated_at", direction="DESCENDING")
                .limit(limit)
            )
            if project:
                query = query.where("project", "==", project)

            sessions = []
            for doc in query.stream():
                data = doc.to_dict()
                sessions.append({
                    "session_id": doc.id,
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "project": data.get("project", ""),
                    "message_count": len(data.get("messages", [])),
                })
            return sessions
        except Exception as exc:
            logger.error("ChatHistory.list_sessions error: %s", exc)
            return []

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session document from Firestore."""
        if not self.enabled:
            return False
        try:
            self._db.collection(_COLLECTION).document(session_id).delete()
            logger.info("ChatHistory deleted session: %s", session_id)
            return True
        except Exception as exc:
            logger.error("ChatHistory.delete_session error (session=%s): %s", session_id, exc)
            return False
