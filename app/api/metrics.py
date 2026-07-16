from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.schemas import PipelineJobRead, PostMetricRead
from app.db.session import get_db
from app.repositories.metric_repository import list_metrics
from app.services.metric_service import update_due_metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=list[PostMetricRead])
def get_metrics(db: Session = Depends(get_db), post_id: int | None = None, limit: int = 100):
    return list_metrics(db, limit=limit, post_id=post_id)


@router.post("/due/run", response_model=list[PipelineJobRead])
def run_due_metrics(db: Session = Depends(get_db)):
    jobs = update_due_metrics(db)
    db.commit()
    for job in jobs:
        db.refresh(job)
    return jobs
