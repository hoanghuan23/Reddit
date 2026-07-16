from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PipelineLog


def list_logs(db: Session, limit: int = 100, offset: int = 0, job_id: int | None = None) -> list[PipelineLog]:
    stmt = select(PipelineLog).order_by(PipelineLog.created_at.desc()).limit(limit).offset(offset)
    if job_id is not None:
        stmt = stmt.where(PipelineLog.job_id == job_id)
    return list(db.scalars(stmt))
