import json
from datetime import timedelta

from sqlalchemy import select

from app.core.constants import utc_now
from app.db.models import PipelineJob, PipelineLog, Post
from app.db.schemas import SourceCreate
from app.services.job_service import create_job
from app.services.metric_service import update_due_metrics
from app.services.post_service import upsert_comment_from_reddit, upsert_post_from_reddit
from app.services.scheduler_service import run_due
from app.services.source_service import create_or_update_source, normalize_identifier, scrape_source, soft_delete_source
from app.services.reddit_client import RedditClientError


def reddit_post(post_id="abc123", score=3, comments=2):
    return {
        "id": post_id,
        "subreddit": "python",
        "title": "Example",
        "permalink": f"/r/python/comments/{post_id}/example/",
        "url": "https://example.com/article",
        "author": "alice",
        "author_fullname": "t2_alice",
        "selftext": "",
        "link_flair_text": None,
        "is_self": False,
        "over_18": False,
        "stickied": False,
        "locked": False,
        "created_utc": utc_now().timestamp(),
        "score": score,
        "num_comments": comments,
    }


def test_normalize_identifier():
    assert normalize_identifier("subreddit", "https://www.reddit.com/r/python/new/") == "python"
    assert normalize_identifier("user", "u/spez") == "spez"
    assert normalize_identifier("latest", "anything") == "all"


def test_upsert_post_metric_and_source_mapping(db_session):
    source = create_or_update_source(db_session, SourceCreate(source_type="subreddit", identifier="python"))
    job = create_job(db_session, "scrape_posts", source.id)
    post, is_new = upsert_post_from_reddit(db_session, source, reddit_post(), job)
    db_session.commit()

    assert is_new is True
    assert post.reddit_post_id == "abc123"
    assert post.permalink == "https://www.reddit.com/r/python/comments/abc123/example/"

    post_again, is_new_again = upsert_post_from_reddit(db_session, source, reddit_post(score=5, comments=3), job)
    db_session.commit()

    assert post_again.id == post.id
    assert is_new_again is False
    assert len(post_again.sources) == 1


def test_upsert_deleted_comment_and_soft_delete_source(db_session):
    source = create_or_update_source(db_session, SourceCreate(source_type="subreddit", identifier="python"))
    job = create_job(db_session, "scrape_posts", source.id)
    post, _ = upsert_post_from_reddit(db_session, source, reddit_post(), job)
    comment = upsert_comment_from_reddit(
        db_session,
        post.id,
        {
            "id": "c1",
            "parent_id": "t3_abc123",
            "author": "[deleted]",
            "body": "[deleted]",
            "score": 0,
            "depth": 0,
            "created_utc": (utc_now() - timedelta(minutes=1)).timestamp(),
        },
    )
    soft_delete_source(db_session, source)
    db_session.commit()

    assert comment.is_deleted is True
    assert comment.author_name is None
    assert source.is_active is False


def test_scrape_source_uses_scrape_posts_job_type(db_session):
    class FakeRedditClient:
        def fetch_listing(self, source_type, identifier, limit):
            return []

    source = create_or_update_source(db_session, SourceCreate(source_type="subreddit", identifier="python"))
    job = scrape_source(db_session, source, FakeRedditClient())
    db_session.commit()

    assert job.job_type == "scrape_posts"
    assert job.source_id == source.id


def test_run_due_sources_use_scrape_new_posts_job_type(db_session, monkeypatch):
    class FakeRedditClient:
        def fetch_listing(self, source_type, identifier, limit):
            return []

    source = create_or_update_source(db_session, SourceCreate(source_type="subreddit", identifier="python"))

    from app.services import scheduler_service

    def fake_scrape_source(db, source, reddit_client=None, job_type="scrape_posts"):
        return scrape_source(db, source, FakeRedditClient(), job_type)

    monkeypatch.setattr(scheduler_service, "scrape_source", fake_scrape_source)
    result = run_due(db_session)
    db_session.commit()

    assert len(result.source_jobs) == 1
    assert result.source_jobs[0].job_type == "scrape_new_posts"
    assert result.source_jobs[0].source_id == source.id


def test_update_due_metrics_does_not_create_empty_job(db_session):
    metric_jobs = update_due_metrics(db_session)
    stored_jobs = list(db_session.scalars(select(PipelineJob)))

    assert metric_jobs == []
    assert stored_jobs == []


def test_update_due_metrics_creates_jobs_by_source(db_session):
    class FakeRedditClient:
        def fetch_post_metric(self, permalink):
            return {
                "id": "abc123",
                "title": "Updated",
                "permalink": "/r/python/comments/abc123/example/",
                "url": "https://example.com/updated",
                "score": 20,
                "num_comments": 4,
            }

    source = create_or_update_source(db_session, SourceCreate(source_type="subreddit", identifier="python"))
    scrape_job = create_job(db_session, "scrape_posts", source.id)
    post, _ = upsert_post_from_reddit(db_session, source, reddit_post(), scrape_job)
    post.next_metric_update = utc_now() - timedelta(minutes=1)
    db_session.commit()

    metric_jobs = update_due_metrics(db_session, FakeRedditClient())
    db_session.commit()

    assert len(metric_jobs) == 1
    assert metric_jobs[0].job_type == "update_metrics"
    assert metric_jobs[0].source_id == source.id
    assert metric_jobs[0].posts_updated == 1
    assert post.metric_tier == "medium"


def test_update_due_metrics_respects_batch_size_across_runs(db_session):
    class FakeRedditClient:
        def fetch_post_metric(self, permalink):
            if "/first/" in permalink:
                return {
                    "id": "first",
                    "title": "First updated",
                    "permalink": "/r/python/comments/first/example/",
                    "url": "https://example.com/first",
                    "score": 10,
                    "num_comments": 2,
                }
            return {
                "id": "second",
                "title": "Second updated",
                "permalink": "/r/python/comments/second/example/",
                "url": "https://example.com/second",
                "score": 12,
                "num_comments": 3,
            }

    source = create_or_update_source(db_session, SourceCreate(source_type="subreddit", identifier="python"))
    scrape_job = create_job(db_session, "scrape_posts", source.id)
    first_post, _ = upsert_post_from_reddit(db_session, source, reddit_post("first"), scrape_job)
    second_post, _ = upsert_post_from_reddit(db_session, source, reddit_post("second"), scrape_job)
    first_post.next_metric_update = utc_now() - timedelta(minutes=2)
    second_post.next_metric_update = utc_now() - timedelta(minutes=1)
    db_session.commit()

    first_jobs = update_due_metrics(db_session, FakeRedditClient(), limit=1, request_delay_seconds=0)
    second_jobs = update_due_metrics(db_session, FakeRedditClient(), limit=1, request_delay_seconds=0)
    db_session.commit()

    assert len(first_jobs) == 1
    assert len(second_jobs) == 1
    assert first_jobs[0].posts_updated == 1
    assert second_jobs[0].posts_updated == 1
    assert first_post.last_metric_update is not None
    assert second_post.last_metric_update is not None


def test_update_due_metrics_stops_on_rate_limit_and_logs_failure(db_session, monkeypatch):
    sleep_calls = []

    def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr("app.services.metric_service.time.sleep", fake_sleep)

    class RateLimitedRedditClient:
        def __init__(self):
            self.calls = 0

        def fetch_post_metric(self, permalink):
            self.calls += 1
            if self.calls == 1:
                return {
                    "id": "first",
                    "title": "First updated",
                    "permalink": "/r/python/comments/first/example/",
                    "url": "https://example.com/first",
                    "score": 10,
                    "num_comments": 2,
                }
            raise RedditClientError("rate limited", 429, retry_after=4)

    source = create_or_update_source(db_session, SourceCreate(source_type="subreddit", identifier="python"))
    scrape_job = create_job(db_session, "scrape_posts", source.id)
    first_post, _ = upsert_post_from_reddit(db_session, source, reddit_post("first"), scrape_job)
    second_post, _ = upsert_post_from_reddit(db_session, source, reddit_post("second"), scrape_job)
    first_post.next_metric_update = utc_now() - timedelta(minutes=2)
    second_post.next_metric_update = utc_now() - timedelta(minutes=1)
    db_session.commit()

    metric_jobs = update_due_metrics(db_session, RateLimitedRedditClient(), request_delay_seconds=0)

    logs = list(db_session.scalars(select(PipelineLog)))
    assert len(metric_jobs) == 1
    assert metric_jobs[0].posts_updated == 1
    assert metric_jobs[0].items_failed == 1
    assert len(logs) == 1
    assert logs[0].message == "Bị rate limited khi update metric cho post."
    assert logs[0].log_level == "WARNING"
    assert sleep_calls == [4]
    assert first_post.last_metric_update is not None
    assert second_post.metric_tier == "low"


def test_update_due_metrics_skips_when_running_job_exists(db_session):
    source = create_or_update_source(db_session, SourceCreate(source_type="subreddit", identifier="python"))
    scrape_job = create_job(db_session, "scrape_posts", source.id)
    post, _ = upsert_post_from_reddit(db_session, source, reddit_post(), scrape_job)
    post.next_metric_update = utc_now() - timedelta(minutes=1)
    running_job = create_job(db_session, "update_metrics", source.id)
    running_job.status = "running"
    db_session.commit()

    metric_jobs = update_due_metrics(db_session)

    stored_jobs = list(db_session.scalars(select(PipelineJob)))
    assert metric_jobs == []
    assert len(stored_jobs) == 2
    assert all(job.job_type != "update_metrics" or job.status == "running" for job in stored_jobs)


def test_update_due_metrics_logs_failed_posts(db_session):
    class FailingRedditClient:
        def fetch_post_metric(self, permalink):
            raise RuntimeError("reddit fetch failed")

    source = create_or_update_source(db_session, SourceCreate(source_type="subreddit", identifier="python"))
    scrape_job = create_job(db_session, "scrape_posts", source.id)
    post, _ = upsert_post_from_reddit(db_session, source, reddit_post(), scrape_job)
    post.next_metric_update = utc_now() - timedelta(minutes=1)
    db_session.commit()

    metric_jobs = update_due_metrics(db_session, FailingRedditClient(), commit_per_source=True)

    logs = list(db_session.scalars(select(PipelineLog)))
    assert len(metric_jobs) == 1
    assert metric_jobs[0].items_failed == 1
    assert logs[0].job_id == metric_jobs[0].id
    assert logs[0].source_id == source.id
    assert logs[0].message == "Không update được metric cho post."
    assert logs[0].error_type == "RuntimeError"
    error_details = json.loads(logs[0].error_details)
    assert set(error_details) == {"post_id", "permalink", "error"}
    assert error_details["post_id"] == post.id
    assert error_details["permalink"] == "https://www.reddit.com/r/python/comments/abc123/example/"
    assert error_details["error"] == "reddit fetch failed"


def test_scrape_new_posts_stops_at_latest_existing_post(db_session):
    now = utc_now()
    newest = reddit_post("newest", score=1, comments=1)
    newest["created_utc"] = (now - timedelta(minutes=10)).timestamp()
    newer = reddit_post("newer", score=1, comments=1)
    newer["created_utc"] = (now - timedelta(minutes=5)).timestamp()
    older = reddit_post("older", score=1, comments=1)
    older["created_utc"] = (now - timedelta(minutes=20)).timestamp()

    class FakeRedditClient:
        def fetch_listing(self, source_type, identifier, limit):
            return [newer, newest, older]

    source = create_or_update_source(db_session, SourceCreate(source_type="subreddit", identifier="python"))
    scrape_job = create_job(db_session, "scrape_posts", source.id)
    upsert_post_from_reddit(db_session, source, newest, scrape_job)
    db_session.commit()

    job = scrape_source(db_session, source, FakeRedditClient(), job_type="scrape_new_posts")
    db_session.commit()

    post_ids = set(db_session.scalars(select(Post.reddit_post_id)))
    assert job.posts_new == 1
    assert "newer" in post_ids
    assert "older" not in post_ids
