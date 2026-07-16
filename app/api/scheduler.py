from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.schemas import RunDueResponse
from app.db.session import get_db
from app.services.scheduler_service import run_due

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.post("/run-due", response_model=RunDueResponse)
def run_due_endpoint(db: Session = Depends(get_db)):
    result = run_due(db)
    return RunDueResponse(source_jobs=result.source_jobs, metric_job=result.metric_job)
