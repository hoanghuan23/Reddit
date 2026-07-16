from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalyticsCache


def get_analytics_cache(db: Session, source_id: int, target_date: date) -> AnalyticsCache | None:
    return db.scalar(
        select(AnalyticsCache).where(
            AnalyticsCache.source_id == source_id,
            AnalyticsCache.date == target_date,
        )
    )
