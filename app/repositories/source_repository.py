from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Source


def get_source(db: Session, source_id: int) -> Source | None:
    return db.get(Source, source_id)


def get_source_by_key(db: Session, source_type: str, identifier: str) -> Source | None:
    return db.scalar(select(Source).where(Source.source_type == source_type, Source.identifier == identifier))


def list_sources(db: Session, include_inactive: bool = False, limit: int = 100, offset: int = 0) -> list[Source]:
    stmt = select(Source).order_by(Source.id.desc()).limit(limit).offset(offset)
    if not include_inactive:
        stmt = stmt.where(Source.is_active.is_(True))
    return list(db.scalars(stmt))
