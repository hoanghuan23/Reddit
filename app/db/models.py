from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    identifier: Mapped[str] = mapped_column(String(300), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_accessible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_comments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    last_scraped: Mapped[object | None] = mapped_column(DateTime)
    next_scrape: Mapped[object | None] = mapped_column(DateTime)
    schedule_tier: Mapped[int | None] = mapped_column(Integer)
    schedule_override_minutes: Mapped[int | None] = mapped_column(Integer)

    posts = relationship("Post", secondary="source_posts", back_populates="sources")


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reddit_post_id: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    subreddit_name: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    permalink: Mapped[str] = mapped_column(Text, nullable=False)
    external_url: Mapped[str | None] = mapped_column(Text)
    author_name: Mapped[str | None] = mapped_column(String(100))
    author_fullname: Mapped[str | None] = mapped_column(String(30))
    post_type: Mapped[str] = mapped_column(String(20), nullable=False, default="link")
    selftext: Mapped[str | None] = mapped_column(Text)
    link_flair_text: Mapped[str | None] = mapped_column(String(200))
    is_self: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_nsfw: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_stickied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    post_created_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    is_tracked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tracking_until: Mapped[object | None] = mapped_column(DateTime)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_metric_update: Mapped[object | None] = mapped_column(DateTime)
    next_metric_update: Mapped[object | None] = mapped_column(DateTime)
    metric_tier: Mapped[str] = mapped_column(String(20), nullable=False, default="very_low")

    sources = relationship("Source", secondary="source_posts", back_populates="posts")


class SourcePost(Base):
    __tablename__ = "source_posts"

    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)
    first_seen_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[object] = mapped_column(DateTime, nullable=False)


class AnalyticsCache(Base):
    __tablename__ = "analytics_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[object] = mapped_column(Date, nullable=False)
    total_posts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_comments_per_post: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    avg_score_per_post: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    top_post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id", ondelete="SET NULL"))
    growth_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    cached_at: Mapped[object] = mapped_column(DateTime, nullable=False)


class PipelineJob(Base):
    __tablename__ = "pipeline_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(30), nullable=False, default="scrape_posts")
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    posts_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    posts_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    posts_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[object | None] = mapped_column(DateTime)
    finished_at: Mapped[object | None] = mapped_column(DateTime)
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False)


class PostMetric(Base):
    __tablename__ = "post_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recorded_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_jobs.id", ondelete="SET NULL"))


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    reddit_comment_id: Mapped[str] = mapped_column(String(20), nullable=False)
    parent_reddit_id: Mapped[str | None] = mapped_column(String(30))
    author_name: Mapped[str | None] = mapped_column(String(100))
    author_fullname: Mapped[str | None] = mapped_column(String(30))
    body: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_submitter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_stickied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    comment_created_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False)


class PipelineLog(Base):
    __tablename__ = "pipeline_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_jobs.id", ondelete="SET NULL"))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    log_level: Mapped[str] = mapped_column(String(20), nullable=False, default="ERROR")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(100))
    error_details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False)
