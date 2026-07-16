from sqlalchemy.orm import Session

from app.core.constants import utc_now
from app.db.models import PipelineJob, PipelineLog


def create_job(db: Session, job_type: str, source_id: int | None = None) -> PipelineJob:
    now = utc_now()
    job = PipelineJob(
        job_type=job_type,
        source_id=source_id,
        status="pending",
        posts_found=0,
        posts_new=0,
        posts_updated=0,
        items_failed=0,
        created_at=now,
    )
    db.add(job)
    db.flush()
    return job


def mark_job_running(job: PipelineJob) -> None:
    job.status = "running"
    job.started_at = utc_now()


def mark_job_done(job: PipelineJob) -> None:
    job.status = "done"
    job.finished_at = utc_now()


def mark_job_failed(job: PipelineJob, error: Exception | str) -> None:
    job.status = "failed"
    job.error_message = str(error)
    job.finished_at = utc_now()


def log_warning_or_error(
    db: Session,
    message: str,
    job_id: int | None = None,
    source_id: int | None = None,
    exc: Exception | None = None,
    level: str = "ERROR",
) -> PipelineLog:
    log = PipelineLog(
        job_id=job_id,
        source_id=source_id,
        log_level=level,
        message=message,
        error_type=type(exc).__name__ if exc else None,
        error_details=str(exc) if exc else None,
        created_at=utc_now(),
    )
    db.add(log)
    db.flush()
    return log
