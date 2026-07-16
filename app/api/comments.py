from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.schemas import CommentRead
from app.db.session import get_db
from app.repositories.comment_repository import get_comment, list_comments

router = APIRouter(prefix="/comments", tags=["comments"])


@router.get("", response_model=list[CommentRead])
def get_comments(
    db: Session = Depends(get_db),
    post_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return list_comments(db, limit=limit, offset=offset, post_id=post_id)


@router.get("/{comment_id}", response_model=CommentRead)
def get_comment_detail(comment_id: int, db: Session = Depends(get_db)):
    comment = get_comment(db, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    return comment
