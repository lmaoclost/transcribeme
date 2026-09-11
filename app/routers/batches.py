"""Batch endpoints: list + detail."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Batch, Job
from app.schemas import BatchDetailResponse, BatchResponse

router = APIRouter()


@router.get("/batches", response_model=List[BatchResponse])
def list_batches(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), session: Session = Depends(get_session)) -> List[BatchResponse]:
    batches = session.scalars(select(Batch).order_by(Batch.created_at.desc()).limit(limit).offset(offset)).all()
    return batches


@router.get("/batches/{batch_id}", response_model=BatchDetailResponse)
def get_batch(batch_id: str, session: Session = Depends(get_session)) -> BatchDetailResponse:
    batch = session.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    jobs = session.scalars(select(Job).where(Job.batch_id == batch_id)).all()
    return BatchDetailResponse(batch=batch, jobs=jobs, total=len(jobs))
