"""Document extraction service.

Supported types:
  .md / .txt  → direct UTF-8 decode
  .pdf        → pypdf text; OCR fallback via PyMuPDF if low text
  .docx       → python-docx (Office Open XML format)
  .doc        → python-docx (limited support; only works for some .doc files;
                legacy OLE2 binary .doc files may fail or produce empty output)
  .xls/.xlsx  → pandas / openpyxl
  images      → pytesseract OCR
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import NamedTuple


class ExtractedPage(NamedTuple):
    """A single logical page / sheet of extracted text."""

    content: str
    page: int | None  # 1-based page number (pdf / images)
    sheet: str | None  # sheet name (xlsx)


def extract(file_path: str | Path) -> list[ExtractedPage]:
    """Route file to the appropriate extractor and return extracted pages."""
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext in {".md", ".txt"}:
        return _extract_text(path)
    if ext == ".pdf":
        return _extract_pdf(path)
    if ext in {".docx", ".doc"}:
        return _extract_docx(path)
    if ext in {".xlsx", ".xls"}:
        return _extract_excel(path)
    if ext in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif", ".webp"}:
        return _extract_image(path)

    raise ValueError(f"Unsupported file type: {ext}")


# ── Plain text / markdown ────────────────────────────────────────────────────


def _extract_text(path: Path) -> list[ExtractedPage]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return [ExtractedPage(content=text, page=None, sheet=None)]


# ── PDF ─────────────────────────────────────────────────────────────────────


_OCR_THRESHOLD = 100  # chars per page below which we try OCR


def _extract_pdf(path: Path) -> list[ExtractedPage]:
    import pypdf

    pages: list[ExtractedPage] = []
    reader = pypdf.PdfReader(str(path))

    for i, pdf_page in enumerate(reader.pages, start=1):
        text = (pdf_page.extract_text() or "").strip()
        if len(text) < _OCR_THRESHOLD:
            text = _ocr_pdf_page(path, page_index=i - 1) or text
        pages.append(ExtractedPage(content=text, page=i, sheet=None))

    return pages


def _ocr_pdf_page(path: Path, page_index: int) -> str:
    """Render a PDF page with PyMuPDF and OCR it with pytesseract."""
    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image

        doc = fitz.open(str(path))
        page = doc[page_index]
        mat = fitz.Matrix(2.0, 2.0)  # 2× zoom for better OCR quality
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return pytesseract.image_to_string(img)
    except Exception:
        return ""


# ── DOCX ────────────────────────────────────────────────────────────────────


def _extract_docx(path: Path) -> list[ExtractedPage]:
    import docx

    doc = docx.Document(str(path))
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return [ExtractedPage(content=text, page=None, sheet=None)]


# ── Excel ───────────────────────────────────────────────────────────────────


def _extract_excel(path: Path) -> list[ExtractedPage]:
    import pandas as pd

    pages: list[ExtractedPage] = []
    xl = pd.ExcelFile(str(path), engine="openpyxl")
    for sheet_name in xl.sheet_names:
        df = xl.parse(sheet_name)
        text = df.to_string(index=False)
        pages.append(ExtractedPage(content=text, page=None, sheet=str(sheet_name)))
    return pages


# ── Images ──────────────────────────────────────────────────────────────────


def _extract_image(path: Path) -> list[ExtractedPage]:
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(str(path))
        text = pytesseract.image_to_string(img)
        return [ExtractedPage(content=text, page=1, sheet=None)]
    except Exception as exc:
        return [ExtractedPage(content=f"[OCR failed: {exc}]", page=1, sheet=None)]
