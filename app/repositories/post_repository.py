from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Post


def get_post(db: Session, post_id: int) -> Post | None:
    return db.get(Post, post_id)


def get_post_by_reddit_id(db: Session, reddit_post_id: str) -> Post | None:
    return db.scalar(select(Post).where(Post.reddit_post_id == reddit_post_id))


def list_posts(db: Session, limit: int = 100, offset: int = 0, source_id: int | None = None) -> list[Post]:
    stmt = select(Post).order_by(Post.post_created_at.desc()).limit(limit).offset(offset)
    if source_id is not None:
        stmt = stmt.where(Post.source_id == source_id)
    return list(db.scalars(stmt))
