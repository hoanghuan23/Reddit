from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.core.constants import utc_now
from app.db.models import PipelineJob, Post, SourcePost
from app.services.job_service import create_job, log_warning_or_error, mark_job_done, mark_job_failed, mark_job_running
from app.services.post_service import update_post_metric_from_reddit
from app.services.reddit_client import RedditClient


def update_due_metrics(db: Session, reddit_client: RedditClient | None = None, limit: int = 100) -> list[PipelineJob]:
    client = reddit_client or RedditClient()
    jobs: list[PipelineJob] = []
    for source_id in due_metric_source_ids(db):
        posts = due_posts(db, source_id=source_id, limit=limit)
        if not posts:
            continue
        job = create_job(db, "update_metrics", source_id)
        mark_job_running(job)
        job.posts_found = len(posts)
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
        except Exception as exc:
            mark_job_failed(job, exc)
            log_warning_or_error(db, "Update metrics batch thất bại.", job.id, source_id, exc)
            raise
        finally:
            db.flush()
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
