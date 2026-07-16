from app.core.constants import utc_now
from app.db.models import Source


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_source_create_scrapes_with_mocked_client(client, monkeypatch):
    def fake_scrape(db, source):
        from app.services.job_service import create_job, mark_job_done, mark_job_running

        job = create_job(db, "scrape_new_posts", source.id)
        mark_job_running(job)
        mark_job_done(job)
        return job

    monkeypatch.setattr("app.api.sources.scrape_source", fake_scrape)
    response = client.post("/sources", json={"source_type": "latest", "identifier": "all", "include_comments": False})
    assert response.status_code == 200
    body = response.json()
    assert body["source"]["identifier"] == "all"
    assert body["job"]["status"] == "done"


def test_source_list_detail_patch_delete(client, db_session):
    source = Source(
        source_type="subreddit",
        identifier="python",
        is_active=True,
        is_accessible=True,
        include_comments=False,
        created_at=utc_now(),
        schedule_tier=5,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    assert client.get("/sources").status_code == 200
    patch = client.patch(f"/sources/{source.id}", json={"include_comments": True})
    assert patch.status_code == 200
    assert patch.json()["include_comments"] is True
    delete = client.delete(f"/sources/{source.id}")
    assert delete.status_code == 200
    assert delete.json()["is_active"] is False
