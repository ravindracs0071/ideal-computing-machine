"""Documents router – POST /datasets/{dataset_id}/documents."""

import mimetypes
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel
from redis import Redis
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Dataset, Document, IngestJob

router = APIRouter(tags=["documents"])

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {
    ".md", ".txt", ".pdf", ".doc", ".docx",
    ".xls", ".xlsx", ".png", ".jpg", ".jpeg",
    ".tiff", ".tif", ".bmp", ".gif", ".webp",
}


class DocInfo(BaseModel):
    doc_id: str
    filename: str


class UploadResponse(BaseModel):
    job_id: str
    dataset_id: str
    documents: list[DocInfo]


@router.post(
    "/datasets/{dataset_id}/documents",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_documents(
    dataset_id: str,
    files: list[UploadFile],
    db: AsyncSession = Depends(get_db),
):
    ds = await db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    saved: list[tuple[Document, Path]] = []

    for upload in files:
        filename = upload.filename or "unknown"
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            )

        content = await upload.read()
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File '{filename}' exceeds {settings.max_upload_mb} MB limit",
            )

        doc_id = str(uuid.uuid4())
        mime_type = upload.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        dest = UPLOADS_DIR / f"{doc_id}{ext}"
        dest.write_bytes(content)

        doc = Document(
            id=doc_id,
            dataset_id=dataset_id,
            filename=filename,
            mime_type=mime_type,
            status="pending",
        )
        db.add(doc)
        saved.append((doc, dest))

    # Create job record
    job_record = IngestJob(dataset_id=dataset_id, status="queued", stage="queued")
    db.add(job_record)
    await db.commit()

    # Enqueue RQ job
    doc_payloads = [
        {"doc_id": doc.id, "filename": doc.filename, "path": str(path)}
        for doc, path in saved
    ]
    try:
        redis_conn = Redis.from_url(settings.redis_url)
        q = Queue(connection=redis_conn)
        q.enqueue(
            "app.worker.tasks.ingest_documents",
            kwargs={
                "job_id": job_record.id,
                "dataset_id": dataset_id,
                "documents": doc_payloads,
            },
            job_id=job_record.id,
            result_ttl=86400,
        )
    except Exception as exc:
        # If Redis is unavailable, record the job as failed gracefully
        job_record.status = "failed"
        job_record.errors = f'["Redis unavailable: {exc}"]'
        await db.commit()

    return UploadResponse(
        job_id=job_record.id,
        dataset_id=dataset_id,
        documents=[DocInfo(doc_id=doc.id, filename=doc.filename) for doc, _ in saved],
    )
