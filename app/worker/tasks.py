"""RQ worker tasks for async document ingestion."""

from __future__ import annotations

import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a synchronous context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def ingest_documents(
    job_id: str,
    dataset_id: str,
    documents: list[dict],
) -> None:
    """Ingestion pipeline: extract → chunk → embed → index.

    Args:
        job_id: IngestJob primary key (used to update progress).
        dataset_id: Parent dataset identifier.
        documents: List of dicts with keys: doc_id, filename, path.
    """
    _run_async(_ingest_async(job_id, dataset_id, documents))


async def _ingest_async(
    job_id: str,
    dataset_id: str,
    documents: list[dict],
) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

    from app.config import settings
    from app.models import Document, IngestJob
    from app.services.chunking import chunk_pages
    from app.services.embeddings import embed_texts
    from app.services.extraction import extract
    from app.services.search import upsert_chunks

    engine = create_async_engine(settings.app_db_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def update_job(session: AsyncSession, **kwargs):
        job = await session.get(IngestJob, job_id)
        if job:
            for k, v in kwargs.items():
                setattr(job, k, v)
            await session.commit()

    errors: list[str] = []
    all_chunks: list[dict] = []

    async with Session() as session:
        await update_job(session, status="running", stage="extract")

    # ── Stage 1: Extract ───────────────────────────────────────────────────
    doc_chunks_map: dict[str, list] = {}
    for doc_info in documents:
        doc_id = doc_info["doc_id"]
        filename = doc_info["filename"]
        path = doc_info["path"]
        try:
            pages = extract(path)
            doc_chunks_map[doc_id] = (filename, pages)
        except Exception as exc:
            logger.exception("Extraction failed for %s", filename)
            errors.append(f"{filename}: extraction error – {exc}")

    # ── Stage 2: Chunk ─────────────────────────────────────────────────────
    async with Session() as session:
        await update_job(session, stage="chunk")

    for doc_id, (filename, pages) in doc_chunks_map.items():
        chunks = chunk_pages(pages, doc_id)
        for chunk in chunks:
            all_chunks.append(
                {
                    "id": chunk.chunk_id,
                    "chunk_id": chunk.chunk_id,
                    "doc_id": doc_id,
                    "dataset_id": dataset_id,
                    "content": chunk.content,
                    "source_name": filename,
                    "page": chunk.page,
                    "sheet": chunk.sheet,
                }
            )

    total = len(all_chunks)
    async with Session() as session:
        await update_job(session, stage="embed", total=total, done=0)

    # ── Stage 3: Embed ─────────────────────────────────────────────────────
    texts = [c["content"] for c in all_chunks]
    try:
        vectors = await embed_texts(texts)
        for chunk, vec in zip(all_chunks, vectors):
            chunk["contentVector"] = vec
    except Exception as exc:
        logger.exception("Embedding failed")
        errors.append(f"Embedding error: {exc}")
        # Continue without vectors; index upsert will fail if schema requires them
        for chunk in all_chunks:
            chunk["contentVector"] = []

    async with Session() as session:
        await update_job(session, stage="index", done=len(all_chunks))

    # ── Stage 4: Index ─────────────────────────────────────────────────────
    try:
        await upsert_chunks(all_chunks)
    except Exception as exc:
        logger.exception("Azure Search upsert failed")
        errors.append(f"Index error: {exc}")

    # ── Finalize ───────────────────────────────────────────────────────────
    final_status = "failed" if errors else "succeeded"
    async with Session() as session:
        await update_job(
            session,
            status=final_status,
            stage="done",
            done=total,
            errors=json.dumps(errors),
        )
        # Mark individual documents
        for doc_info in documents:
            doc = await session.get(Document, doc_info["doc_id"])
            if doc:
                doc.status = "failed" if doc_info["doc_id"] in [
                    e.split(":")[0] for e in errors
                ] else "indexed"
        await session.commit()

    await engine.dispose()
