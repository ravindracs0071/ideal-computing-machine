"""Text chunking service.

Splits text into overlapping windows of configurable size.
Chunk IDs are stable: ``{doc_id}:{chunk_index}``.
"""

from __future__ import annotations

from typing import NamedTuple

from app.config import settings


class Chunk(NamedTuple):
    chunk_id: str
    content: str
    doc_id: str
    chunk_index: int
    # optional metadata forwarded from extraction
    page: int | None
    sheet: str | None


def chunk_text(
    text: str,
    doc_id: str,
    page: int | None = None,
    sheet: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    start_index: int = 0,
) -> list[Chunk]:
    """Split *text* into overlapping chunks and return a list of :class:`Chunk`.

    Args:
        text: The raw text to split.
        doc_id: Identifier for the parent document.
        page: Source page number (PDF/images).
        sheet: Source sheet name (Excel).
        chunk_size: Maximum characters per chunk (default: settings.chunk_size).
        chunk_overlap: Overlap between consecutive chunks (default: settings.chunk_overlap).
        start_index: Offset for the first chunk index (used to merge pages of the same doc).
    """
    size = chunk_size if chunk_size is not None else settings.chunk_size
    overlap = chunk_overlap if chunk_overlap is not None else settings.chunk_overlap

    if overlap >= size:
        raise ValueError(
            f"chunk_overlap ({overlap}) must be less than chunk_size ({size})"
        )

    text = text.strip()
    if not text:
        return []

    chunks: list[Chunk] = []
    pos = 0
    idx = start_index

    while pos < len(text):
        end = pos + size
        window = text[pos:end]
        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}:{idx}",
                content=window,
                doc_id=doc_id,
                chunk_index=idx,
                page=page,
                sheet=sheet,
            )
        )
        idx += 1
        pos += size - overlap

    return chunks


def chunk_pages(
    pages: list,  # list of ExtractedPage (avoid circular import)
    doc_id: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Chunk]:
    """Chunk all extracted pages of a document, preserving metadata."""
    all_chunks: list[Chunk] = []
    for page in pages:
        page_chunks = chunk_text(
            text=page.content,
            doc_id=doc_id,
            page=page.page,
            sheet=page.sheet,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            start_index=len(all_chunks),
        )
        all_chunks.extend(page_chunks)
    return all_chunks
