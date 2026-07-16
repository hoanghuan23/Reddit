from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PipelineJob


def get_job(db: Session, job_id: int) -> PipelineJob | None:
    return db.get(PipelineJob, job_id)


def list_jobs(db: Session, limit: int = 100, offset: int = 0, source_id: int | None = None) -> list[PipelineJob]:
    stmt = select(PipelineJob).order_by(PipelineJob.created_at.desc()).limit(limit).offset(offset)
    if source_id is not None:
        stmt = stmt.where(PipelineJob.source_id == source_id)
    return list(db.scalars(stmt))
