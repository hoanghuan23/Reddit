from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import schedule_tier_for, utc_now
from app.db.models import AnalyticsCache, Post, PostMetric, SourcePost


def rebuild_source_analytics_for_today(db: Session, source_id: int) -> AnalyticsCache:
    today = utc_now().date()
    rows = db.execute(
        select(Post.id, PostMetric.comments_count, PostMetric.score)
        .join(SourcePost, SourcePost.post_id == Post.id)
        .join(PostMetric, PostMetric.post_id == Post.id)
        .where(SourcePost.source_id == source_id, func.date(Post.post_created_at) == today.isoformat())
        .order_by(PostMetric.recorded_at.desc())
    ).all()
    latest_by_post: dict[int, tuple[int, int]] = {}
    for post_id, comments_count, score in rows:
        latest_by_post.setdefault(post_id, (comments_count or 0, score or 0))
    total_posts = len(latest_by_post)
    total_comments = sum(item[0] for item in latest_by_post.values())
    total_score = sum(item[1] for item in latest_by_post.values())
    top_post_id = None
    if latest_by_post:
        top_post_id = max(latest_by_post.items(), key=lambda item: (item[1][0], item[1][1]))[0]

    previous = db.scalar(
        select(AnalyticsCache).where(AnalyticsCache.source_id == source_id, AnalyticsCache.date < today).order_by(AnalyticsCache.date.desc())
    )
    growth_rate = 0.0
    if previous and previous.total_posts:
        growth_rate = (total_posts - previous.total_posts) / previous.total_posts

    cache = db.scalar(select(AnalyticsCache).where(AnalyticsCache.source_id == source_id, AnalyticsCache.date == today))
    values = {
        "total_posts": total_posts,
        "total_comments": total_comments,
        "total_score": total_score,
        "avg_comments_per_post": total_comments / total_posts if total_posts else 0,
        "avg_score_per_post": total_score / total_posts if total_posts else 0,
        "top_post_id": top_post_id,
        "growth_rate": growth_rate,
        "cached_at": utc_now(),
    }
    if cache is None:
        cache = AnalyticsCache(source_id=source_id, date=today, **values)
        db.add(cache)
    else:
        for key, value in values.items():
            setattr(cache, key, value)
    db.flush()
    return cache


def schedule_tier_from_latest_cache(db: Session, source_id: int) -> int:
    cache = db.scalar(select(AnalyticsCache).where(AnalyticsCache.source_id == source_id).order_by(AnalyticsCache.date.desc()))
    if cache is None:
        return 5
    return schedule_tier_for(cache.total_posts, cache.total_comments, cache.total_score)
