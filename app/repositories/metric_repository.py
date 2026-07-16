from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PostMetric


def list_metrics(db: Session, limit: int = 100, offset: int = 0, post_id: int | None = None) -> list[PostMetric]:
    stmt = select(PostMetric).order_by(PostMetric.recorded_at.desc()).limit(limit).offset(offset)
    if post_id is not None:
        stmt = stmt.where(PostMetric.post_id == post_id)
    return list(db.scalars(stmt))
