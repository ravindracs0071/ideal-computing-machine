"""Jobs router – GET /jobs/{job_id}."""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import IngestJob

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobProgress(BaseModel):
    stage: str
    done: int
    total: int


class JobOut(BaseModel):
    job_id: str
    status: str
    progress: JobProgress
    errors: list[str]


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(IngestJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        errors = json.loads(job.errors or "[]")
    except (json.JSONDecodeError, TypeError):
        errors = []

    return JobOut(
        job_id=job.id,
        status=job.status,
        progress=JobProgress(stage=job.stage, done=job.done, total=job.total),
        errors=errors,
    )
