"""
rag.py — RAG (Retrieval-Augmented Generation) engine.

Supports PDF, DOCX, CSV, XLSX, TXT document ingestion.
Uses ChromaDB as vector store + Google text-embedding-004.
Gracefully degrades when disabled or no documents present.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Config from env ──────────────────────────────────────────────────────────
_RAG_ENABLED      = os.getenv("RAG_ENABLED", "true").lower() == "true"
_RAG_DOCS_DIR     = Path(os.getenv("RAG_DOCS_DIR", "./data/rag_docs"))
_RAG_CHUNK_SIZE   = int(os.getenv("RAG_CHUNK_SIZE", "500"))
_RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "50"))
_CHROMA_DIR       = Path(os.getenv("RAG_CHROMA_DIR", "./data/chroma_db"))
_GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY", "")


class RAGEngine:
    """Manages document ingestion and context retrieval for Gemini sessions."""

    def __init__(self) -> None:
        self.enabled = _RAG_ENABLED
        self._vectorstore = None
        self._embeddings  = None

        if not self.enabled:
            logger.info("RAG disabled (RAG_ENABLED=false)")
            return

        _RAG_DOCS_DIR.mkdir(parents=True, exist_ok=True)
        _CHROMA_DIR.mkdir(parents=True, exist_ok=True)

        try:
            self._init_vectorstore()
            logger.info("RAGEngine initialised (chroma_dir=%s)", _CHROMA_DIR)
        except Exception as exc:
            logger.warning("RAGEngine init failed — RAG disabled: %s", exc)
            self.enabled = False

    # ── private ───────────────────────────────────────────────────────────────

    def _init_vectorstore(self) -> None:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        from langchain_community.vectorstores import Chroma

        self._embeddings = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=_GEMINI_API_KEY,
        )
        self._vectorstore = Chroma(
            collection_name="rag_docs",
            embedding_function=self._embeddings,
            persist_directory=str(_CHROMA_DIR),
        )

    def _load_file(self, file_path: Path) -> list:
        """Return list of LangChain Document objects from a file."""
        ext = file_path.suffix.lower()
        if ext == ".pdf":
            from langchain_community.document_loaders import PyPDFLoader
            loader = PyPDFLoader(str(file_path))
        elif ext == ".docx":
            from langchain_community.document_loaders import Docx2txtLoader
            loader = Docx2txtLoader(str(file_path))
        elif ext == ".csv":
            from langchain_community.document_loaders.csv_loader import CSVLoader
            loader = CSVLoader(str(file_path))
        elif ext in (".xlsx", ".xls"):
            from langchain_community.document_loaders import UnstructuredExcelLoader
            loader = UnstructuredExcelLoader(str(file_path))
        elif ext == ".txt":
            from langchain_community.document_loaders import TextLoader
            loader = TextLoader(str(file_path), encoding="utf-8")
        else:
            raise ValueError(f"Unsupported file type: {ext}")
        return loader.load()

    # ── public ────────────────────────────────────────────────────────────────

    def ingest_file(self, file_path: Path, filename: str) -> dict:
        """Ingest a document into the vector store. Returns stats dict."""
        if not self.enabled or self._vectorstore is None:
            return {"chunks_added": 0, "filename": filename, "error": "RAG not enabled"}

        try:
            try:
                from langchain_text_splitters import RecursiveCharacterTextSplitter
            except ImportError:
                from langchain.text_splitter import RecursiveCharacterTextSplitter

            docs = self._load_file(file_path)
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=_RAG_CHUNK_SIZE,
                chunk_overlap=_RAG_CHUNK_OVERLAP,
            )
            chunks = splitter.split_documents(docs)

            now = datetime.now(timezone.utc).isoformat()
            for chunk in chunks:
                chunk.metadata.update({
                    "source": filename,
                    "uploaded_at": now,
                    "file_type": file_path.suffix.lower().lstrip("."),
                })

            self._vectorstore.add_documents(chunks)
            logger.info("RAG ingested '%s': %d chunks", filename, len(chunks))
            return {"chunks_added": len(chunks), "filename": filename}
        except Exception as exc:
            logger.error("RAG ingest error for '%s': %s", filename, exc)
            return {"chunks_added": 0, "filename": filename, "error": str(exc)}

    def delete_file(self, filename: str) -> dict:
        """Remove all chunks for a given source filename."""
        if not self.enabled or self._vectorstore is None:
            return {"deleted": 0, "filename": filename}
        try:
            col = self._vectorstore._collection
            result = col.get(where={"source": filename})
            ids = result.get("ids", [])
            if ids:
                col.delete(ids=ids)
            logger.info("RAG deleted '%s': %d chunks removed", filename, len(ids))
            return {"deleted": len(ids), "filename": filename}
        except Exception as exc:
            logger.error("RAG delete error for '%s': %s", filename, exc)
            return {"deleted": 0, "filename": filename, "error": str(exc)}

    def list_documents(self) -> list:
        """Return unique documents with chunk counts."""
        if not self.enabled or self._vectorstore is None:
            return []
        try:
            col = self._vectorstore._collection
            result = col.get(include=["metadatas"])
            meta_list = result.get("metadatas") or []

            docs: dict[str, dict] = {}
            for m in meta_list:
                src = m.get("source", "unknown")
                if src not in docs:
                    docs[src] = {
                        "filename": src,
                        "chunks": 0,
                        "uploaded_at": m.get("uploaded_at", ""),
                        "file_type": m.get("file_type", ""),
                    }
                docs[src]["chunks"] += 1

            return list(docs.values())
        except Exception as exc:
            logger.error("RAG list_documents error: %s", exc)
            return []

    def has_documents(self) -> bool:
        """Return True if the vector store contains any documents."""
        if not self.enabled or self._vectorstore is None:
            return False
        try:
            return self._vectorstore._collection.count() > 0
        except Exception:
            return False

    def query(self, question: str, k: int = 5) -> str:
        """Similarity-search and return formatted context string."""
        if not self.enabled or self._vectorstore is None or not question.strip():
            return ""
        try:
            results = self._vectorstore.similarity_search(question, k=k)
            if not results:
                return ""
            parts = [doc.page_content for doc in results]
            return "--- Tài liệu tham khảo ---\n" + "\n\n".join(parts) + "\n---"
        except Exception as exc:
            logger.error("RAG query error: %s", exc)
            return ""

    def get_all_context(self, max_chunks: int = 20) -> str:
        """Return a condensed overview of all documents (used at session start)."""
        if not self.enabled or self._vectorstore is None:
            return ""
        try:
            col = self._vectorstore._collection
            result = col.get(
                include=["documents", "metadatas"],
                limit=max_chunks,
            )
            documents = result.get("documents") or []
            metadatas = result.get("metadatas") or []
            if not documents:
                return ""
            lines = ["--- Tài liệu tham khảo ---"]
            for doc, meta in zip(documents, metadatas):
                src = (meta or {}).get("source", "")
                lines.append(f"[{src}]\n{doc}")
            lines.append("---")
            return "\n\n".join(lines)
        except Exception as exc:
            logger.error("RAG get_all_context error: %s", exc)
            return ""
