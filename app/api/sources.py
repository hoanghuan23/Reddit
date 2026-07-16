from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.schemas import PipelineJobRead, SourceCreate, SourceCreateResponse, SourceRead, SourceUpdate
from app.db.session import get_db
from app.repositories.source_repository import get_source, list_sources
from app.services.reddit_client import RedditClientError
from app.services.source_service import create_or_update_source, scrape_source, soft_delete_source, update_source

router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("", response_model=SourceCreateResponse)
def create_source(payload: SourceCreate, db: Session = Depends(get_db)) -> SourceCreateResponse:
    source = create_or_update_source(db, payload)
    try:
        job = scrape_source(db, source)
    except RedditClientError as exc:
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    db.commit()
    db.refresh(source)
    db.refresh(job)
    return SourceCreateResponse(source=source, job=job)


@router.get("", response_model=list[SourceRead])
def get_sources(
    db: Session = Depends(get_db),
    include_inactive: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list:
    return list_sources(db, include_inactive=include_inactive, limit=limit, offset=offset)


@router.get("/{source_id}", response_model=SourceRead)
def get_source_detail(source_id: int, db: Session = Depends(get_db)):
    source = get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.patch("/{source_id}", response_model=SourceRead)
def patch_source(source_id: int, payload: SourceUpdate, db: Session = Depends(get_db)):
    source = get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    update_source(db, source, payload)
    db.commit()
    db.refresh(source)
    return source


@router.delete("/{source_id}", response_model=SourceRead)
def delete_source(source_id: int, db: Session = Depends(get_db)):
    source = get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    soft_delete_source(db, source)
    db.commit()
    db.refresh(source)
    return source


@router.post("/{source_id}/scrape", response_model=PipelineJobRead)
def scrape_source_endpoint(source_id: int, db: Session = Depends(get_db)):
    source = get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    try:
        job = scrape_source(db, source)
    except RedditClientError as exc:
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.commit()
    db.refresh(job)
    return job
