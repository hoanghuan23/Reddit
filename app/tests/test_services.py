from datetime import timedelta

from app.core.constants import utc_now
from app.db.schemas import SourceCreate
from app.services.job_service import create_job
from app.services.post_service import upsert_comment_from_reddit, upsert_post_from_reddit
from app.services.source_service import create_or_update_source, normalize_identifier, soft_delete_source


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
    job = create_job(db_session, "scrape_new_posts", source.id)
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
    job = create_job(db_session, "scrape_new_posts", source.id)
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
