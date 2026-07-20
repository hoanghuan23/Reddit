import logging
import time

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import utc_now
from app.db.models import PipelineJob, Post, Source, SourcePost
from app.services.job_service import create_job, log_warning_or_error, mark_job_done, mark_job_failed, mark_job_running
from app.services.post_service import update_post_metric_from_reddit
from app.services.reddit_client import RedditClient, RedditClientError


logger = logging.getLogger("reddit_api.metrics")


def update_due_metrics(
    db: Session,
    reddit_client: RedditClient | None = None,
    limit: int | None = None,
    commit_per_source: bool = False,
    request_delay_seconds: float | None = None,
) -> list[PipelineJob]:
    settings = get_settings()
    batch_size = limit if limit is not None else settings.metrics_update_batch_size
    delay_seconds = settings.metrics_request_delay_seconds if request_delay_seconds is None else request_delay_seconds
    client = reddit_client or RedditClient()
    if running_metric_job_exists(db):
        logger.info("Bo qua cap nhat metrics | reason=job_running")
        return []
    jobs: list[PipelineJob] = []
    for source_id in due_metric_source_ids(db):
        source = db.get(Source, source_id)
        source_name = source.identifier if source is not None else "unknown"
        expired_count = due_posts_expired_count(db, source_id)
        posts = due_posts(db, source_id=source_id, limit=batch_size)
        if not posts:
            if expired_count:
                logger.info(
                    "Hoan tat cap nhat metrics | source=%s id=%s updated=0 failed=0 rate_limited=0 posts_expired=%s batch_size=%s",
                    source_name,
                    source_id,
                    expired_count,
                    batch_size,
                )
                if commit_per_source:
                    db.commit()
            continue
        job = create_job(db, "update_metrics", source_id)
        mark_job_running(job)
        job.posts_found = len(posts)
        rate_limited_count = 0
        logger.info(
            "Bat dau cap nhat metrics | source=%s id=%s posts=%s posts_expired=%s batch_size=%s delay_seconds=%s",
            source_name,
            source_id,
            len(posts),
            expired_count,
            batch_size,
            delay_seconds,
        )
        try:
            for post in posts:
                if job.posts_updated + job.items_failed > 0 and delay_seconds > 0:
                    time.sleep(delay_seconds)
                try:
                    data = client.fetch_post_metric(post.permalink)
                    update_post_metric_from_reddit(db, post, data, job)
                    job.posts_updated += 1
                except RedditClientError as exc:
                    job.items_failed += 1
                    if exc.status_code == 429:
                        rate_limited_count += 1
                        wait_seconds = exc.retry_after if exc.retry_after is not None else delay_seconds
                        log_warning_or_error(
                            db,
                            "Bị rate limited khi update metric cho post.",
                            job.id,
                            source_id,
                            exc,
                            level="WARNING",
                            context={
                                "post_id": post.id,
                                "permalink": post.permalink,
                                "status_code": exc.status_code,
                                "retry_after": exc.retry_after,
                            },
                        )
                        logger.warning(
                            "Cap nhat metrics bi rate limit | source=%s id=%s post_id=%s retry_after=%s",
                            source_name,
                            source_id,
                            post.id,
                            wait_seconds,
                        )
                        if wait_seconds and wait_seconds > 0:
                            time.sleep(wait_seconds)
                        break
                except Exception as exc:
                    job.items_failed += 1
                    log_warning_or_error(
                        db,
                        "Không update được metric cho post.",
                        job.id,
                        source_id,
                        exc,
                        context={
                            "post_id": post.id,
                            "permalink": post.permalink,
                        },
                    )
                    continue
            mark_job_done(job)
            logger.info(
                "Hoan tat cap nhat metrics | source=%s id=%s updated=%s failed=%s rate_limited=%s posts_expired=%s batch_size=%s",
                source_name,
                source_id,
                job.posts_updated,
                job.items_failed,
                rate_limited_count,
                expired_count,
                batch_size,
            )
        except Exception as exc:
            mark_job_failed(job, exc)
            log_warning_or_error(db, "Update metrics batch thất bại.", job.id, source_id, exc)
            logger.exception(
                "Cap nhat metrics that bai | source=%s id=%s updated=%s failed=%s error=%s",
                source_name,
                source_id,
                job.posts_updated,
                job.items_failed,
                exc,
            )
            raise
        finally:
            db.flush()
            if commit_per_source:
                db.commit()
        jobs.append(job)
    return jobs


def due_metric_source_ids(db: Session) -> list[int]:
    now = utc_now()
    return list(
        db.scalars(
            select(distinct(SourcePost.source_id))
            .join(Post, Post.id == SourcePost.post_id)
            .where(Post.is_tracked.is_(True), Post.next_metric_update <= now)
            .order_by(SourcePost.source_id.asc())
        )
    )


def running_metric_job_exists(db: Session) -> bool:
    return bool(
        db.scalar(
            select(func.count(PipelineJob.id)).where(
                PipelineJob.job_type == "update_metrics",
                PipelineJob.status == "running",
            )
        )
    )


def due_posts_expired_count(db: Session, source_id: int) -> int:
    now = utc_now()
    return db.scalar(
        select(func.count(Post.id))
        .join(SourcePost, SourcePost.post_id == Post.id)
        .where(
            SourcePost.source_id == source_id,
            Post.is_tracked.is_(True),
            Post.tracking_until <= now,
        )
    ) or 0


def due_posts(db: Session, source_id: int | None = None, limit: int = 100) -> list[Post]:
    now = utc_now()
    expired_query = select(Post).where(Post.is_tracked.is_(True), Post.tracking_until <= now)
    if source_id is not None:
        expired_query = expired_query.join(SourcePost, SourcePost.post_id == Post.id).where(SourcePost.source_id == source_id)
    expired = list(db.scalars(expired_query.limit(limit)))
    for post in expired:
        post.is_tracked = False
        post.next_metric_update = None
    remaining = max(limit - len(expired), 0)
    if remaining <= 0:
        db.flush()
        return []
    posts_query = select(Post).where(Post.is_tracked.is_(True), Post.next_metric_update <= now)
    if source_id is not None:
        posts_query = posts_query.join(SourcePost, SourcePost.post_id == Post.id).where(SourcePost.source_id == source_id)
    posts = list(db.scalars(posts_query.order_by(Post.next_metric_update.asc()).limit(remaining)))
    db.flush()
    return posts
