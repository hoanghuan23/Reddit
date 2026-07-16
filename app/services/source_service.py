from datetime import timedelta
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import next_scrape_for, schedule_tier_for, utc_now
from app.db.models import PipelineJob, Source
from app.db.schemas import SourceCreate, SourceUpdate
from app.repositories.source_repository import get_source_by_key
from app.services.analytics_service import rebuild_source_analytics_for_today
from app.services.job_service import create_job, log_warning_or_error, mark_job_done, mark_job_failed, mark_job_running
from app.services.post_service import upsert_comment_from_reddit, upsert_post_from_reddit
from app.services.reddit_client import RedditClient, RedditClientError, reddit_datetime


def normalize_identifier(source_type: str, identifier: str) -> str:
    value = identifier.strip()
    if source_type == "latest":
        return "all"
    parsed = urlparse(value)
    path = parsed.path.strip("/") if parsed.netloc else value.strip("/")
    if source_type == "subreddit":
        if path.startswith("r/"):
            return path.split("/", 2)[1]
        return path.replace("r/", "", 1)
    if source_type == "user":
        if path.startswith("u/") or path.startswith("user/"):
            return path.split("/", 2)[1]
        return path.replace("u/", "", 1)
    return value


def create_or_update_source(db: Session, payload: SourceCreate) -> Source:
    now = utc_now()
    identifier = normalize_identifier(payload.source_type, payload.identifier)
    source = get_source_by_key(db, payload.source_type, identifier)
    if source is None:
        source = Source(
            source_type=payload.source_type,
            identifier=identifier,
            include_comments=payload.include_comments,
            is_active=True,
            is_accessible=True,
            created_at=now,
            schedule_tier=5,
            next_scrape=now,
        )
        db.add(source)
    else:
        source.include_comments = payload.include_comments
        source.is_active = True
    db.flush()
    return source


def update_source(db: Session, source: Source, payload: SourceUpdate) -> Source:
    if payload.identifier is not None:
        source.identifier = normalize_identifier(source.source_type, payload.identifier)
    for field in ("is_active", "is_accessible", "include_comments", "schedule_override_minutes"):
        value = getattr(payload, field)
        if value is not None:
            setattr(source, field, value)
    db.flush()
    return source


def soft_delete_source(db: Session, source: Source) -> Source:
    source.is_active = False
    db.flush()
    return source


def scrape_source(
    db: Session,
    source: Source,
    reddit_client: RedditClient | None = None,
    job_type: str = "scrape_posts",
) -> PipelineJob:
    settings = get_settings()
    client = reddit_client or RedditClient()
    job = create_job(db, job_type, source.id)
    mark_job_running(job)
    db.flush()
    try:
        posts = client.fetch_listing(source.source_type, source.identifier, settings.max_posts_per_source)
        cutoff = utc_now() - timedelta(hours=settings.lookback_hours)
        job.posts_found = len(posts)
        reached_old_posts = False
        for data in posts:
            try:
                if reddit_datetime(data.get("created_utc")) < cutoff:
                    break
                post, is_new = upsert_post_from_reddit(db, source, data, job)
                if is_new:
                    job.posts_new += 1
                else:
                    job.posts_updated += 1
                if source.include_comments:
                    for comment_data in client.fetch_comments(post.permalink):
                        upsert_comment_from_reddit(db, post.id, comment_data)
            except Exception as exc:
                job.items_failed += 1
                log_warning_or_error(db, "Không xử lý được một post Reddit.", job.id, source.id, exc)
                continue
        source.last_scraped = utc_now()
        cache = rebuild_source_analytics_for_today(db, source.id)
        source.schedule_tier = schedule_tier_for(cache.total_posts, cache.total_comments, cache.total_score)
        source.next_scrape = next_scrape_for(utc_now(), source.schedule_tier, source.schedule_override_minutes)
        source.is_accessible = True
        mark_job_done(job)
    except RedditClientError as exc:
        if exc.permanent and exc.status_code in {403, 404}:
            source.is_accessible = False
        mark_job_failed(job, exc)
        log_warning_or_error(db, "Scrape source thất bại.", job.id, source.id, exc)
        raise
    except Exception as exc:
        mark_job_failed(job, exc)
        log_warning_or_error(db, "Scrape source thất bại.", job.id, source.id, exc)
        raise
    finally:
        db.flush()
    return job


def due_sources(db: Session) -> list[Source]:
    now = utc_now()
    return list(
        db.scalars(
            select(Source)
            .where(Source.is_active.is_(True), Source.is_accessible.is_(True), Source.next_scrape <= now)
            .order_by(Source.next_scrape.asc())
        )
    )
