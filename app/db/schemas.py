from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SourceType = Literal["subreddit", "keyword", "user", "latest"]


class SourceCreate(BaseModel):
    source_type: SourceType
    identifier: str = Field(min_length=1, max_length=300)
    include_comments: bool = False


class SourceUpdate(BaseModel):
    identifier: str | None = Field(default=None, min_length=1, max_length=300)
    is_active: bool | None = None
    is_accessible: bool | None = None
    include_comments: bool | None = None
    schedule_override_minutes: int | None = Field(default=None, ge=1)


class SourceRead(BaseModel):
    id: int
    source_type: str
    identifier: str
    is_active: bool
    is_accessible: bool
    include_comments: bool
    created_at: datetime
    last_scraped: datetime | None
    next_scrape: datetime | None
    schedule_tier: int | None
    schedule_override_minutes: int | None

    model_config = ConfigDict(from_attributes=True)


class SourceCreateResponse(BaseModel):
    source: SourceRead
    job: "PipelineJobRead | None" = None


class PostRead(BaseModel):
    id: int
    reddit_post_id: str
    source_id: int | None
    subreddit_name: str
    title: str
    permalink: str
    external_url: str | None
    author_name: str | None
    author_fullname: str | None
    post_type: str
    selftext: str | None
    link_flair_text: str | None
    is_self: bool
    is_nsfw: bool
    is_stickied: bool
    is_locked: bool
    post_created_at: datetime
    created_at: datetime
    is_tracked: bool
    tracking_until: datetime | None
    is_deleted: bool
    last_metric_update: datetime | None
    next_metric_update: datetime | None
    metric_tier: str

    model_config = ConfigDict(from_attributes=True)


class CommentRead(BaseModel):
    id: int
    post_id: int
    reddit_comment_id: str
    parent_reddit_id: str | None
    author_name: str | None
    author_fullname: str | None
    body: str | None
    score: int
    depth: int
    is_submitter: bool
    is_stickied: bool
    is_deleted: bool
    comment_created_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PostMetricRead(BaseModel):
    id: int
    post_id: int
    score: int
    comments_count: int
    recorded_at: datetime
    job_id: int | None

    model_config = ConfigDict(from_attributes=True)


class PipelineJobRead(BaseModel):
    id: int
    job_type: str
    source_id: int | None
    status: str
    posts_found: int
    posts_new: int
    posts_updated: int
    items_failed: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PipelineLogRead(BaseModel):
    id: int
    job_id: int | None
    source_id: int | None
    log_level: str
    message: str
    error_type: str | None
    error_details: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunDueResponse(BaseModel):
    source_jobs: list[PipelineJobRead]
    metric_jobs: list[PipelineJobRead] = Field(default_factory=list)


SourceCreateResponse.model_rebuild()
