from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import utc_now
from app.db.models import PipelineJob, Post
from app.services.job_service import create_job, log_warning_or_error, mark_job_done, mark_job_failed, mark_job_running
from app.services.post_service import update_post_metric_from_reddit
from app.services.reddit_client import RedditClient


def update_due_metrics(db: Session, reddit_client: RedditClient | None = None, limit: int = 100) -> PipelineJob:
    client = reddit_client or RedditClient()
    job = create_job(db, "update_metrics")
    mark_job_running(job)
    posts = due_posts(db, limit=limit)
    job.posts_found = len(posts)
    try:
        for post in posts:
            try:
                data = client.fetch_post_metric(post.permalink)
                update_post_metric_from_reddit(db, post, data, job)
                job.posts_updated += 1
            except Exception as exc:
                job.items_failed += 1
                log_warning_or_error(db, "Không update được metric cho post.", job.id, post.source_id, exc)
                continue
        mark_job_done(job)
    except Exception as exc:
        mark_job_failed(job, exc)
        log_warning_or_error(db, "Update metrics batch thất bại.", job.id, None, exc)
        raise
    finally:
        db.flush()
    return job


def due_posts(db: Session, limit: int = 100) -> list[Post]:
    now = utc_now()
    expired = list(db.scalars(select(Post).where(Post.is_tracked.is_(True), Post.tracking_until <= now).limit(limit)))
    for post in expired:
        post.is_tracked = False
        post.next_metric_update = None
    remaining = max(limit - len(expired), 0)
    if remaining <= 0:
        db.flush()
        return []
    posts = list(
        db.scalars(
            select(Post)
            .where(Post.is_tracked.is_(True), Post.next_metric_update <= now)
            .order_by(Post.next_metric_update.asc())
            .limit(remaining)
        )
    )
    db.flush()
    return posts
