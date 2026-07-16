from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.schemas import PostMetricRead, PostRead
from app.db.session import get_db
from app.repositories.metric_repository import list_metrics
from app.repositories.post_repository import get_post, list_posts

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("", response_model=list[PostRead])
def get_posts(
    db: Session = Depends(get_db),
    source_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return list_posts(db, limit=limit, offset=offset, source_id=source_id)


@router.get("/{post_id}", response_model=PostRead)
def get_post_detail(post_id: int, db: Session = Depends(get_db)):
    post = get_post(db, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.get("/{post_id}/metrics", response_model=list[PostMetricRead])
def get_post_metrics(post_id: int, db: Session = Depends(get_db), limit: int = Query(100, ge=1, le=500)):
    if get_post(db, post_id) is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return list_metrics(db, limit=limit, post_id=post_id)
