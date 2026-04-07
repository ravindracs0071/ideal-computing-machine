"""Tests for the document extraction service (routing + text extraction).

Only tests that don't require external dependencies (Tesseract, PyMuPDF, etc.)
are exercised here.  OCR-dependent paths are tested with mocking.
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.extraction import (
    ExtractedPage,
    extract,
    _extract_text,
    _extract_docx,
    _extract_excel,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _write_tmp(suffix: str, content: bytes) -> Path:
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.write(content)
    f.flush()
    f.close()
    return Path(f.name)


# ── Route detection ───────────────────────────────────────────────────────────


class TestExtractRouting:
    def test_unsupported_extension_raises(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            extract("/fake/path/file.xyz")

    def test_md_file_routes_to_text_extractor(self, tmp_path):
        p = tmp_path / "doc.md"
        p.write_text("# Hello\nWorld", encoding="utf-8")
        result = extract(p)
        assert len(result) == 1
        assert "Hello" in result[0].content

    def test_txt_file_routes_to_text_extractor(self, tmp_path):
        p = tmp_path / "note.txt"
        p.write_text("Plain text content", encoding="utf-8")
        result = extract(p)
        assert result[0].content == "Plain text content"
        assert result[0].page is None
        assert result[0].sheet is None

    def test_pdf_extension_routes_to_pdf_extractor(self, tmp_path):
        """Verify the routing dispatcher calls _extract_pdf for .pdf files."""
        p = tmp_path / "file.pdf"
        p.write_bytes(b"fake pdf content")

        with patch("app.services.extraction._extract_pdf") as mock_pdf:
            mock_pdf.return_value = [ExtractedPage("mocked", 1, None)]
            result = extract(p)
        mock_pdf.assert_called_once_with(p)
        assert result[0].content == "mocked"

    def test_docx_extension_routes_to_docx_extractor(self, tmp_path):
        p = tmp_path / "file.docx"
        p.write_bytes(b"fake docx")

        with patch("app.services.extraction._extract_docx") as mock_docx:
            mock_docx.return_value = [ExtractedPage("docx content", None, None)]
            result = extract(p)
        mock_docx.assert_called_once_with(p)

    def test_xlsx_extension_routes_to_excel_extractor(self, tmp_path):
        p = tmp_path / "data.xlsx"
        p.write_bytes(b"fake xlsx")

        with patch("app.services.extraction._extract_excel") as mock_excel:
            mock_excel.return_value = [ExtractedPage("sheet data", None, "Sheet1")]
            result = extract(p)
        mock_excel.assert_called_once_with(p)

    def test_xls_extension_routes_to_excel_extractor(self, tmp_path):
        p = tmp_path / "data.xls"
        p.write_bytes(b"fake xls")

        with patch("app.services.extraction._extract_excel") as mock_excel:
            mock_excel.return_value = [ExtractedPage("xls data", None, "Sheet1")]
            result = extract(p)
        mock_excel.assert_called_once_with(p)

    def test_image_png_routes_to_image_extractor(self, tmp_path):
        p = tmp_path / "photo.png"
        p.write_bytes(b"fake png")

        with patch("app.services.extraction._extract_image") as mock_img:
            mock_img.return_value = [ExtractedPage("ocr text", 1, None)]
            result = extract(p)
        mock_img.assert_called_once_with(p)

    def test_image_jpg_routes_to_image_extractor(self, tmp_path):
        p = tmp_path / "photo.jpg"
        p.write_bytes(b"fake jpg")

        with patch("app.services.extraction._extract_image") as mock_img:
            mock_img.return_value = [ExtractedPage("ocr text", 1, None)]
            result = extract(p)
        mock_img.assert_called_once_with(p)


# ── Text extractor ────────────────────────────────────────────────────────────


class TestTextExtractor:
    def test_reads_utf8(self, tmp_path):
        p = tmp_path / "file.txt"
        p.write_text("Héllo Wörld", encoding="utf-8")
        result = _extract_text(p)
        assert result[0].content == "Héllo Wörld"

    def test_returns_single_page_with_no_page_no_sheet(self, tmp_path):
        p = tmp_path / "file.md"
        p.write_text("content", encoding="utf-8")
        result = _extract_text(p)
        assert len(result) == 1
        assert result[0].page is None
        assert result[0].sheet is None


# ── PDF OCR fallback (mocked) ─────────────────────────────────────────────────


class TestPdfOcrFallback:
    def test_ocr_called_when_text_is_low(self, tmp_path):
        """If pypdf returns <100 chars, _ocr_pdf_page should be called."""
        p = tmp_path / "scanned.pdf"
        p.write_bytes(b"%PDF-1.4 fake")

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "short"  # < 100 chars

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch("pypdf.PdfReader", return_value=mock_reader), \
             patch("app.services.extraction._ocr_pdf_page", return_value="OCR text") as mock_ocr:
            from app.services.extraction import _extract_pdf
            result = _extract_pdf(p)

        mock_ocr.assert_called_once_with(p, page_index=0)
        assert result[0].content == "OCR text"

    def test_text_used_directly_when_sufficient(self, tmp_path):
        p = tmp_path / "textpdf.pdf"
        p.write_bytes(b"%PDF-1.4 fake")

        long_text = "A" * 200  # > 100 chars threshold

        mock_page = MagicMock()
        mock_page.extract_text.return_value = long_text

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch("pypdf.PdfReader", return_value=mock_reader), \
             patch("app.services.extraction._ocr_pdf_page") as mock_ocr:
            from app.services.extraction import _extract_pdf
            result = _extract_pdf(p)

        mock_ocr.assert_not_called()
        assert result[0].content == long_text
        assert result[0].page == 1
