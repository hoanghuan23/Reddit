from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.schemas import PipelineJobRead
from app.db.session import get_db
from app.repositories.job_repository import get_job, list_jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[PipelineJobRead])
def get_jobs(
    db: Session = Depends(get_db),
    source_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return list_jobs(db, limit=limit, offset=offset, source_id=source_id)


@router.get("/{job_id}", response_model=PipelineJobRead)
def get_job_detail(job_id: int, db: Session = Depends(get_db)):
    job = get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
