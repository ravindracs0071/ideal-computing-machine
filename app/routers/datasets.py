"""Datasets router – POST /datasets, GET /datasets."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Dataset

router = APIRouter(prefix="/datasets", tags=["datasets"])


class DatasetCreate(BaseModel):
    name: str


class DatasetOut(BaseModel):
    dataset_id: str
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
async def create_dataset(body: DatasetCreate, db: AsyncSession = Depends(get_db)):
    ds = Dataset(name=body.name)
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return DatasetOut(dataset_id=ds.id, name=ds.name, created_at=ds.created_at)


@router.get("", response_model=list[DatasetOut])
async def list_datasets(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Dataset).order_by(Dataset.created_at.desc()))
    datasets = result.scalars().all()
    return [
        DatasetOut(dataset_id=ds.id, name=ds.name, created_at=ds.created_at)
        for ds in datasets
    ]


@router.get("/{dataset_id}", response_model=DatasetOut)
async def get_dataset(dataset_id: str, db: AsyncSession = Depends(get_db)):
    ds = await db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return DatasetOut(dataset_id=ds.id, name=ds.name, created_at=ds.created_at)
