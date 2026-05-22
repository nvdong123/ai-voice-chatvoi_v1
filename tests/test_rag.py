"""
test_rag.py — Unit tests for RAGEngine.

All ChromaDB / LangChain calls are mocked.
The module-level _RAG_ENABLED=False (set via conftest env), so every
RAGEngine() starts with self.enabled=False.  Tests that need an enabled
engine set it manually after construction and inject a mock _vectorstore.
"""

from unittest.mock import MagicMock, patch

import pytest

from rag import RAGEngine


# ─── helpers ──────────────────────────────────────────────────────────────────

def _enabled_engine() -> RAGEngine:
    """Return a RAGEngine with enabled=True and a mock vectorstore."""
    engine = RAGEngine()
    engine.enabled = True
    engine._vectorstore = MagicMock()
    return engine


# ─── TEST 1: has_documents() when engine is disabled ──────────────────────────

def test_has_documents_disabled():
    engine = RAGEngine()
    assert engine.enabled is False
    assert engine.has_documents() is False


# ─── TEST 2: has_documents() enabled but empty collection ─────────────────────

def test_has_documents_empty_collection():
    engine = _enabled_engine()
    engine._vectorstore._collection.count.return_value = 0
    assert engine.has_documents() is False


# ─── TEST 3: has_documents() with documents ───────────────────────────────────

def test_has_documents_with_docs():
    engine = _enabled_engine()
    engine._vectorstore._collection.count.return_value = 5
    assert engine.has_documents() is True


# ─── TEST 4: query() when disabled ────────────────────────────────────────────

def test_query_disabled():
    engine = RAGEngine()
    result = engine.query("What is the price?")
    assert result == ""


# ─── TEST 5: query() with empty question ──────────────────────────────────────

def test_query_empty_question():
    engine = _enabled_engine()
    result = engine.query("   ")
    assert result == ""
    engine._vectorstore.similarity_search.assert_not_called()


# ─── TEST 6: query() returns formatted context ────────────────────────────────

def test_query_returns_formatted_context():
    engine = _enabled_engine()

    doc1 = MagicMock()
    doc1.page_content = "Giá căn hộ 2PN là 3 tỷ đồng."
    doc2 = MagicMock()
    doc2.page_content = "Diện tích từ 65–75 m²."

    engine._vectorstore.similarity_search.return_value = [doc1, doc2]

    result = engine.query("Giá bao nhiêu?")

    assert "Tài liệu tham khảo" in result
    assert "Giá căn hộ 2PN" in result
    assert "---" in result


# ─── TEST 7: ingest_file() when disabled ──────────────────────────────────────

def test_ingest_file_disabled(tmp_path):
    engine = RAGEngine()  # enabled=False
    dummy_file = tmp_path / "test.txt"
    dummy_file.write_text("content")

    result = engine.ingest_file(dummy_file, "test.txt")

    assert "error" in result
    assert result.get("chunks_added", 0) == 0


# ─── TEST 8: ingest_file() with valid .txt (mocked loader + splitter) ─────────

def test_ingest_file_txt(tmp_path):
    engine = _enabled_engine()

    txt_file = tmp_path / "brochure.txt"
    txt_file.write_text("Real estate document content. Property info.", encoding="utf-8")

    mock_doc = MagicMock()
    mock_doc.page_content = "Nội dung tài liệu bất động sản."
    mock_doc.metadata = {}

    mock_chunk = MagicMock()
    mock_chunk.metadata = {}

    # langchain may not be installed in the test environment — inject via sys.modules
    import sys
    mock_splitter_cls = MagicMock()
    mock_splitter_instance = MagicMock()
    mock_splitter_instance.split_documents.return_value = [mock_chunk, mock_chunk]
    mock_splitter_cls.return_value = mock_splitter_instance

    mock_ts_module = MagicMock()
    mock_ts_module.RecursiveCharacterTextSplitter = mock_splitter_cls

    with patch.object(engine, "_load_file", return_value=[mock_doc]):
        with patch.dict(sys.modules, {
            "langchain": MagicMock(),
            "langchain.text_splitter": mock_ts_module,
        }):
            result = engine.ingest_file(txt_file, "brochure.txt")

    assert result["chunks_added"] == 2
    assert result["filename"] == "brochure.txt"
    assert "error" not in result
    engine._vectorstore.add_documents.assert_called_once()


# ─── TEST 9: delete_file() when disabled ──────────────────────────────────────

def test_delete_file_disabled():
    engine = RAGEngine()
    result = engine.delete_file("some_doc.pdf")

    assert result["deleted"] == 0
    assert result["filename"] == "some_doc.pdf"


# ─── TEST 10: delete_file() success ───────────────────────────────────────────

def test_delete_file_success():
    engine = _enabled_engine()
    col = engine._vectorstore._collection

    col.get.return_value = {"ids": ["id1", "id2"]}

    result = engine.delete_file("test.txt")

    col.get.assert_called_once_with(where={"source": "test.txt"})
    col.delete.assert_called_once_with(ids=["id1", "id2"])
    assert result["deleted"] == 2
    assert result["filename"] == "test.txt"


# ─── TEST 11: list_documents() when disabled ──────────────────────────────────

def test_list_documents_disabled():
    engine = RAGEngine()
    assert engine.list_documents() == []


# ─── TEST 12: list_documents() aggregates chunks by source ────────────────────

def test_list_documents_groups_by_source():
    engine = _enabled_engine()
    col = engine._vectorstore._collection

    # 3 chunks all from the same source
    col.get.return_value = {
        "metadatas": [
            {"source": "brochure.pdf", "uploaded_at": "2024-01-01T00:00:00+00:00", "file_type": "pdf"},
            {"source": "brochure.pdf", "uploaded_at": "2024-01-01T00:00:00+00:00", "file_type": "pdf"},
            {"source": "brochure.pdf", "uploaded_at": "2024-01-01T00:00:00+00:00", "file_type": "pdf"},
        ]
    }

    docs = engine.list_documents()

    assert len(docs) == 1
    assert docs[0]["filename"] == "brochure.pdf"
    assert docs[0]["chunks"] == 3


# ─── TEST 13: get_all_context() with no documents ─────────────────────────────

def test_get_all_context_no_documents():
    engine = _enabled_engine()
    engine._vectorstore._collection.get.return_value = {"documents": [], "metadatas": []}

    result = engine.get_all_context()

    assert result == ""


# ─── TEST 14: get_all_context() returns formatted string ──────────────────────

def test_get_all_context_formatted():
    engine = _enabled_engine()
    col = engine._vectorstore._collection

    col.get.return_value = {
        "documents": ["Giá căn hộ từ 2.5 tỷ.", "Diện tích 65m²."],
        "metadatas": [
            {"source": "price_list.pdf"},
            {"source": "floor_plan.pdf"},
        ],
    }

    result = engine.get_all_context()

    assert "---" in result
    assert "price_list.pdf" in result
    assert "Giá căn hộ" in result
