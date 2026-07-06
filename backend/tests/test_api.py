"""API tests: real HTTP semantics, no network.

httpx's ASGITransport drives the FastAPI app in-process — requests go
through routing, validation, serialization, and CORS exactly as they
would over a socket. Dependency overrides point the app at the test
database session and the HashingProvider; nothing inside the app is
mocked.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.api.app import create_app
from jobscout.api.deps import get_session
from jobscout.config import Settings
from jobscout.ingest.pipeline import SourceStats, upsert_posting
from jobscout.matching.embed_jobs import embed_pending_jobs
from jobscout.matching.embeddings import HashingProvider
from jobscout.sources.base import RawPosting

NOW = datetime.now(tz=UTC)


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings=Settings(), provider=HashingProvider())

    async def _test_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _test_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def seed_jobs(db_session: AsyncSession) -> None:
    stats = SourceStats(source="t")
    for i, (title, desc) in enumerate(
        [
            ("Senior Data Engineer", "Python SQL Airflow Kafka pipelines. $170,000 - $210,000"),
            ("Brand Designer", "Figma and typography."),
        ]
    ):
        await upsert_posting(
            db_session,
            RawPosting(
                source="t",
                external_id=f"j{i}",
                url=f"https://ex.com/{i}",
                title=title,
                company="Acme",
                location="Remote",
                description=desc,
                fetched_at=NOW,
                raw={},
            ),
            stats,
        )
    await db_session.commit()
    await embed_pending_jobs(db_session, HashingProvider())


async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_jobs_list_and_detail(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    await seed_jobs(db_session)

    listed = (await client.get("/jobs")).json()
    assert len(listed) == 2
    assert "raw" not in listed[0]  # internal fields stay internal

    searched = (await client.get("/jobs", params={"q": "designer"})).json()
    assert [j["title"] for j in searched] == ["Brand Designer"]

    detail_response = await client.get(f"/jobs/{listed[0]['id']}")
    detail = detail_response.json()
    assert detail["description"]
    assert detail["postings"][0]["url"].startswith("https://ex.com/")

    assert (await client.get("/jobs/999999")).status_code == 404


async def test_profile_upload_match_and_feed(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """The end-to-end browser flow: upload resume -> matches -> feed."""
    await seed_jobs(db_session)

    created = await client.post(
        "/profiles",
        data={"name": "data-eng", "text": "Python SQL Airflow data engineer"},
    )
    assert created.status_code == 201
    profile = created.json()
    assert "Python" in profile["skills"]

    matches = (await client.post(f"/profiles/{profile['id']}/match")).json()
    assert matches["matches"][0]["job"]["title"] == "Senior Data Engineer"
    assert "Airflow" in matches["matches"][0]["explanation"]["overlapping"]
    assert matches["matches"][0]["apply_url"] == "https://ex.com/0"

    feed = (await client.get(f"/profiles/{profile['id']}/feed", params={"hours": 1})).json()
    assert len(feed["matches"]) == 2  # both jobs are brand new
    old_feed = (await client.get(f"/profiles/{profile['id']}/feed", params={"hours": 0})).json()
    assert old_feed["matches"] == []


async def test_profile_upload_via_file(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/profiles",
        files={"file": ("resume.txt", b"Kubernetes and Go engineer", "text/plain")},
    )
    assert response.status_code == 201
    assert "Kubernetes" in response.json()["skills"]


async def test_profile_upload_requires_content(client: httpx.AsyncClient) -> None:
    assert (await client.post("/profiles", data={"name": "x"})).status_code == 422


async def test_application_lifecycle(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    await seed_jobs(db_session)
    job_id = (await client.get("/jobs")).json()[0]["id"]

    created = await client.post("/applications", json={"job_id": job_id})
    assert created.status_code == 201
    app_id = created.json()["id"]
    assert created.json()["status"] == "saved"

    # idempotent save: same job+profile returns the existing application
    again = await client.post("/applications", json={"job_id": job_id})
    assert again.json()["id"] == app_id

    updated = (
        await client.patch(f"/applications/{app_id}", json={"status": "applied", "notes": "!"})
    ).json()
    assert updated["status"] == "applied"
    assert [e["status"] for e in updated["events"]] == ["saved", "applied"]

    bad = await client.patch(f"/applications/{app_id}", json={"status": "ghosted"})
    assert bad.status_code == 422

    listed = (await client.get("/applications", params={"status": "applied"})).json()
    assert [a["id"] for a in listed] == [app_id]

    assert (await client.delete(f"/applications/{app_id}")).status_code == 204
    assert (await client.get("/applications")).json() == []


async def test_application_for_missing_job_404s(client: httpx.AsyncClient) -> None:
    assert (await client.post("/applications", json={"job_id": 424242})).status_code == 404
