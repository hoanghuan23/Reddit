import logging

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.core.constants import utc_now
from app.db.models import PipelineJob, Post, Source, SourcePost
from app.services.job_service import create_job, log_warning_or_error, mark_job_done, mark_job_failed, mark_job_running
from app.services.post_service import update_post_metric_from_reddit
from app.services.reddit_client import RedditClient


logger = logging.getLogger("reddit_api.metrics")


def update_due_metrics(
    db: Session,
    reddit_client: RedditClient | None = None,
    limit: int = 100,
    commit_per_source: bool = False,
) -> list[PipelineJob]:
    client = reddit_client or RedditClient()
    jobs: list[PipelineJob] = []
    for source_id in due_metric_source_ids(db):
        source = db.get(Source, source_id)
        source_name = source.identifier if source is not None else "unknown"
        expired_count = due_posts_expired_count(db, source_id)
        posts = due_posts(db, source_id=source_id, limit=limit)
        if not posts:
            if expired_count:
                logger.info(
                    "Hoan tat cap nhat metrics | source=%s id=%s updated=0 failed=0 posts_expired=%s",
                    source_name,
                    source_id,
                    expired_count,
                )
                if commit_per_source:
                    db.commit()
            continue
        job = create_job(db, "update_metrics", source_id)
        mark_job_running(job)
        job.posts_found = len(posts)
        logger.info(
            "Bat dau cap nhat metrics | source=%s id=%s posts=%s posts_expired=%s",
            source_name,
            source_id,
            len(posts),
            expired_count,
        )
        try:
            for post in posts:
                try:
                    data = client.fetch_post_metric(post.permalink)
                    update_post_metric_from_reddit(db, post, data, job)
                    job.posts_updated += 1
                except Exception as exc:
                    job.items_failed += 1
                    log_warning_or_error(db, "Không update được metric cho post.", job.id, source_id, exc)
                    continue
            mark_job_done(job)
            logger.info(
                "Hoan tat cap nhat metrics | source=%s id=%s updated=%s failed=%s posts_expired=%s",
                source_name,
                source_id,
                job.posts_updated,
                job.items_failed,
                expired_count,
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
