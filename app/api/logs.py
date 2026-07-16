from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.schemas import PipelineLogRead
from app.db.session import get_db
from app.repositories.log_repository import list_logs

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("", response_model=list[PipelineLogRead])
def get_logs(
    db: Session = Depends(get_db),
    job_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return list_logs(db, limit=limit, offset=offset, job_id=job_id)
