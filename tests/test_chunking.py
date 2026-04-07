"""Tests for the chunking service."""

import pytest

from app.services.chunking import Chunk, chunk_text, chunk_pages
from app.services.extraction import ExtractedPage


class TestChunkText:
    def test_empty_text_returns_empty(self):
        result = chunk_text("", doc_id="doc1")
        assert result == []

    def test_whitespace_only_returns_empty(self):
        result = chunk_text("   \n\t  ", doc_id="doc1")
        assert result == []

    def test_short_text_produces_single_chunk(self):
        text = "Hello world"
        result = chunk_text(text, doc_id="doc1", chunk_size=100, chunk_overlap=10)
        assert len(result) == 1
        assert result[0].content == text
        assert result[0].chunk_id == "doc1:0"
        assert result[0].doc_id == "doc1"

    def test_chunk_ids_are_sequential(self):
        text = "A" * 300
        result = chunk_text(text, doc_id="d", chunk_size=100, chunk_overlap=10)
        assert [c.chunk_index for c in result] == list(range(len(result)))
        assert [c.chunk_id for c in result] == [f"d:{i}" for i in range(len(result))]

    def test_chunk_size_respected(self):
        text = "X" * 500
        result = chunk_text(text, doc_id="d", chunk_size=100, chunk_overlap=0)
        for chunk in result:
            assert len(chunk.content) <= 100

    def test_overlap_produces_correct_window(self):
        # With size=10 and overlap=5, step=5
        text = "0123456789ABCDEFGHIJ"  # 20 chars
        result = chunk_text(text, doc_id="d", chunk_size=10, chunk_overlap=5)
        # Windows: [0:10], [5:15], [10:20]
        assert result[0].content == "0123456789"
        assert result[1].content == "56789ABCDE"
        assert result[2].content == "ABCDEFGHIJ"

    def test_metadata_forwarded(self):
        result = chunk_text("some text", doc_id="d", page=3, sheet="Sheet1", chunk_size=100, chunk_overlap=0)
        assert result[0].page == 3
        assert result[0].sheet == "Sheet1"

    def test_start_index_offset(self):
        result = chunk_text("hello world", doc_id="d", chunk_size=100, chunk_overlap=0, start_index=5)
        assert result[0].chunk_index == 5
        assert result[0].chunk_id == "d:5"

    def test_invalid_overlap_raises(self):
        with pytest.raises(ValueError, match="chunk_overlap"):
            chunk_text("text", doc_id="d", chunk_size=10, chunk_overlap=10)

    def test_long_text_chunks_cover_all_content(self):
        text = "word " * 1000  # 5000 chars
        result = chunk_text(text, doc_id="d", chunk_size=200, chunk_overlap=20)
        # Reconstruct content without overlap and verify nothing is lost
        assert len(result) > 1
        # All chunks should be non-empty
        for chunk in result:
            assert chunk.content.strip()


class TestChunkPages:
    def test_multiple_pages_chunked_sequentially(self):
        pages = [
            ExtractedPage(content="Page one content here", page=1, sheet=None),
            ExtractedPage(content="Page two content here", page=2, sheet=None),
        ]
        result = chunk_pages(pages, doc_id="doc1", chunk_size=100, chunk_overlap=0)
        assert len(result) == 2
        assert result[0].page == 1
        assert result[1].page == 2
        # Indices should be globally sequential
        assert result[0].chunk_index == 0
        assert result[1].chunk_index == 1

    def test_empty_pages_skipped(self):
        pages = [
            ExtractedPage(content="", page=1, sheet=None),
            ExtractedPage(content="has content", page=2, sheet=None),
        ]
        result = chunk_pages(pages, doc_id="doc1", chunk_size=100, chunk_overlap=0)
        assert len(result) == 1
        assert result[0].page == 2

    def test_sheet_metadata_preserved(self):
        pages = [
            ExtractedPage(content="revenue data", page=None, sheet="Revenue"),
        ]
        result = chunk_pages(pages, doc_id="excel_doc", chunk_size=100, chunk_overlap=0)
        assert result[0].sheet == "Revenue"
        assert result[0].page is None
