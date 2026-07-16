from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Comment


def get_comment(db: Session, comment_id: int) -> Comment | None:
    return db.get(Comment, comment_id)


def get_comment_by_reddit_id(db: Session, reddit_comment_id: str) -> Comment | None:
    return db.scalar(select(Comment).where(Comment.reddit_comment_id == reddit_comment_id))


def list_comments(db: Session, limit: int = 100, offset: int = 0, post_id: int | None = None) -> list[Comment]:
    stmt = select(Comment).order_by(Comment.comment_created_at.desc()).limit(limit).offset(offset)
    if post_id is not None:
        stmt = stmt.where(Comment.post_id == post_id)
    return list(db.scalars(stmt))
