from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import metric_tier_for, next_metric_update_for, utc_now
from app.db.models import Comment, PipelineJob, Post, PostMetric, Source, SourcePost
from app.services.reddit_client import reddit_datetime


def normalise_permalink(permalink: str) -> str:
    if permalink.startswith("http://") or permalink.startswith("https://"):
        return permalink.rstrip("/") + "/"
    return "https://www.reddit.com" + permalink.rstrip("/") + "/"


def infer_post_type(data: dict[str, Any]) -> str:
    url = str(data.get("url") or "")
    if data.get("is_self"):
        return "text"
    if data.get("is_gallery"):
        return "gallery"
    if data.get("is_video") or data.get("post_hint") == "hosted:video":
        return "video"
    if data.get("post_hint") == "image":
        return "image"
    if url and "reddit.com" not in url:
        return "link"
    if data.get("poll_data"):
        return "poll"
    return "other"


def upsert_post_from_reddit(db: Session, source: Source, data: dict[str, Any], job: PipelineJob) -> tuple[Post, bool]:
    settings = get_settings()
    now = utc_now()
    reddit_post_id = data["id"]
    post = db.scalar(select(Post).where(Post.reddit_post_id == reddit_post_id))
    is_new = post is None
    post_created_at = reddit_datetime(data.get("created_utc"))
    permalink = normalise_permalink(data.get("permalink") or f"/comments/{reddit_post_id}/")
    metric_tier = metric_tier_for(data.get("score", 0), data.get("num_comments", 0))
    tracking_until = post_created_at + timedelta(hours=settings.lookback_hours)
    next_metric = next_metric_update_for(now, metric_tier, tracking_until)

    values = {
        "source_id": source.id if is_new else post.source_id,
        "subreddit_name": data.get("subreddit") or source.identifier,
        "title": data.get("title") or "",
        "permalink": permalink,
        "external_url": data.get("url"),
        "author_name": data.get("author") if data.get("author") != "[deleted]" else None,
        "author_fullname": data.get("author_fullname"),
        "post_type": infer_post_type(data),
        "selftext": data.get("selftext"),
        "link_flair_text": data.get("link_flair_text"),
        "is_self": bool(data.get("is_self", False)),
        "is_nsfw": bool(data.get("over_18", False)),
        "is_stickied": bool(data.get("stickied", False)),
        "is_locked": bool(data.get("locked", False)),
        "post_created_at": post_created_at,
        "is_tracked": now < tracking_until,
        "tracking_until": tracking_until,
        "last_metric_update": now,
        "next_metric_update": next_metric,
        "metric_tier": metric_tier,
    }
    if post is None:
        post = Post(reddit_post_id=reddit_post_id, created_at=now, is_deleted=False, **values)
        db.add(post)
        db.flush()
    else:
        for key, value in values.items():
            setattr(post, key, value)
        db.flush()

    upsert_source_post(db, source.id, post.id)
    add_metric_snapshot(db, post.id, data.get("score", 0), data.get("num_comments", 0), job.id)
    return post, is_new


def upsert_source_post(db: Session, source_id: int, post_id: int) -> SourcePost:
    now = utc_now()
    mapping = db.get(SourcePost, {"source_id": source_id, "post_id": post_id})
    if mapping is None:
        mapping = SourcePost(source_id=source_id, post_id=post_id, first_seen_at=now, last_seen_at=now)
        db.add(mapping)
    else:
        mapping.last_seen_at = now
    db.flush()
    return mapping


def add_metric_snapshot(db: Session, post_id: int, score: int | None, comments_count: int | None, job_id: int | None) -> PostMetric:
    metric = PostMetric(
        post_id=post_id,
        score=score or 0,
        comments_count=comments_count or 0,
        recorded_at=utc_now(),
        job_id=job_id,
    )
    db.add(metric)
    db.flush()
    return metric


def update_post_metric_from_reddit(db: Session, post: Post, data: dict[str, Any], job: PipelineJob) -> None:
    now = utc_now()
    score = data.get("score", 0)
    comments_count = data.get("num_comments", 0)
    tier = metric_tier_for(score, comments_count)
    post.title = data.get("title") or post.title
    post.permalink = normalise_permalink(data.get("permalink") or post.permalink)
    post.external_url = data.get("url") or post.external_url
    post.last_metric_update = now
    post.metric_tier = tier
    if post.tracking_until and now >= post.tracking_until:
        post.is_tracked = False
        post.next_metric_update = None
    elif post.tracking_until:
        post.is_tracked = True
        post.next_metric_update = next_metric_update_for(now, tier, post.tracking_until)
    add_metric_snapshot(db, post.id, score, comments_count, job.id)


def upsert_comment_from_reddit(db: Session, post_id: int, data: dict[str, Any]) -> Comment:
    now = utc_now()
    reddit_comment_id = data["id"]
    comment = db.scalar(select(Comment).where(Comment.reddit_comment_id == reddit_comment_id))
    deleted = data.get("author") in {None, "[deleted]"} or data.get("body") == "[deleted]"
    values = {
        "post_id": post_id,
        "parent_reddit_id": data.get("parent_id"),
        "author_name": None if deleted else data.get("author"),
        "author_fullname": data.get("author_fullname"),
        "body": data.get("body"),
        "score": data.get("score", 0) or 0,
        "depth": data.get("depth", 0) or 0,
        "is_submitter": bool(data.get("is_submitter", False)),
        "is_stickied": bool(data.get("stickied", False)),
        "is_deleted": bool(deleted),
        "comment_created_at": reddit_datetime(data.get("created_utc")),
    }
    if comment is None:
        comment = Comment(reddit_comment_id=reddit_comment_id, created_at=now, **values)
        db.add(comment)
    else:
        for key, value in values.items():
            setattr(comment, key, value)
    db.flush()
    return comment
