"""API tests (PLAN.md Phase 3): profile upload -> matches, job detail,
save/apply tracking, and the polling feed — end to end through the FastAPI
app, with a sqlite session factory and a fake embedding provider injected
via ``create_app``'s constructor overrides (see ``api/app.py``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jobscout.api.app import create_app
from jobscout.embeddings.base import EMBEDDING_DIM, EmbeddingProvider
from jobscout.models import Job


class FakeProvider(EmbeddingProvider):
    """Embeds each text to a vector keyed on its length, so texts that
    share words end up closer together than unrelated ones — enough
    signal for rank-ordering assertions without a real model."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text) % 97)] + [0.0] * (EMBEDDING_DIM - 1) for text in texts]


def make_job(**overrides: object) -> Job:
    defaults: dict[str, object] = {
        "normalized_title": "data engineer",
        "canonical_url": "https://example.com/1",
        "title": "Data Engineer",
        "company": "Acme Corp",
        "location": "Remote",
        "first_seen": datetime(2026, 1, 1, tzinfo=UTC),
        "last_seen": datetime(2026, 1, 1, tzinfo=UTC),
    }
    return Job(**{**defaults, **overrides})


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(session_factory=session_factory, embedding_provider=FakeProvider())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def test_job_detail_404_for_missing_job(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/jobs/999")
    assert response.status_code == 404


async def test_job_list_and_detail(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        session.add(make_job())
        await session.commit()

    listed = await client.get("/api/jobs")
    assert listed.status_code == 200
    [job] = listed.json()
    assert job["title"] == "Data Engineer"

    detail = await client.get(f"/api/jobs/{job['id']}")
    assert detail.status_code == 200
    assert detail.json()["saved_status"] is None


async def test_matches_404_without_a_profile(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/matches")
    assert response.status_code == 404


async def test_profile_upload_then_matches(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    assert (await client.get("/api/profile")).json() == {
        "has_profile": False,
        "updated_at": None,
        "resume_preview": None,
    }

    async with session_factory() as session:
        session.add_all(
            [
                make_job(
                    canonical_url="https://example.com/embedded",
                    description="Python and SQL data pipelines.",
                    embedding=[1.0] + [0.0] * (EMBEDDING_DIM - 1),
                ),
                make_job(
                    canonical_url="https://example.com/unembedded",
                    title="No Embedding Yet",
                    embedding=None,
                ),
            ]
        )
        await session.commit()

    upload = await client.post(
        "/api/profile",
        files={"resume": ("resume.txt", b"Python engineer, SQL, data pipelines.", "text/plain")},
    )
    assert upload.status_code == 200
    assert upload.json()["has_profile"] is True

    matches = await client.get("/api/matches")
    assert matches.status_code == 200
    [match] = matches.json()
    assert match["job"]["canonical_url"] == "https://example.com/embedded"
    assert "python" in match["matched_keywords"]


async def test_save_update_status_and_unsave(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        job = make_job()
        session.add(job)
        await session.commit()
        job_id = job.id

    save = await client.post(f"/api/jobs/{job_id}/save")
    assert save.status_code == 200
    assert save.json()["status"] == "saved"

    update = await client.patch(f"/api/jobs/{job_id}/save", json={"status": "applied"})
    assert update.status_code == 200
    assert update.json()["status"] == "applied"

    listed = await client.get("/api/saved")
    assert [s["status"] for s in listed.json()] == ["applied"]

    detail = await client.get(f"/api/jobs/{job_id}")
    assert detail.json()["saved_status"] == "applied"

    unsave = await client.delete(f"/api/jobs/{job_id}/save")
    assert unsave.status_code == 204

    missing_unsave = await client.delete(f"/api/jobs/{job_id}/save")
    assert missing_unsave.status_code == 404


async def test_save_rejects_unknown_job(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/jobs/999/save")
    assert response.status_code == 404


async def test_feed_filters_by_since_and_ranks_against_profile(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        session.add_all(
            [
                make_job(
                    canonical_url="https://example.com/old",
                    first_seen=datetime(2025, 1, 1, tzinfo=UTC),
                    embedding=[1.0] + [0.0] * (EMBEDDING_DIM - 1),
                ),
                make_job(
                    canonical_url="https://example.com/new",
                    first_seen=datetime(2026, 6, 1, tzinfo=UTC),
                    description="Python and SQL data pipelines.",
                    embedding=[1.0] + [0.0] * (EMBEDDING_DIM - 1),
                ),
            ]
        )
        await session.commit()

    since = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    feed = await client.get("/api/feed", params={"since": since})
    assert feed.status_code == 200
    body = feed.json()
    assert [item["job"]["canonical_url"] for item in body["jobs"]] == ["https://example.com/new"]
    assert body["jobs"][0]["score"] is None  # no profile uploaded yet

    await client.post(
        "/api/profile",
        files={"resume": ("resume.txt", b"Python engineer, SQL, data pipelines.", "text/plain")},
    )

    feed_with_profile = await client.get("/api/feed", params={"since": since})
    [item] = feed_with_profile.json()["jobs"]
    assert item["score"] is not None
