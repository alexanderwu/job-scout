"""API tests (PLAN.md Phase 3): profile upload -> matches, job detail,
save/apply tracking, and the polling feed — end to end through the FastAPI
app, with a sqlite session factory and a fake embedding provider injected
via ``create_app``'s constructor overrides (see ``api/app.py``).

Also covers the Phase 4 career-copilot endpoints: skill-gap, tailoring
suggestions, cover letters (via a fake LLM provider, the same injection
pattern ``FakeProvider`` uses), and application-tracker timestamps/reminders.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jobscout.api.app import create_app
from jobscout.embeddings.base import EMBEDDING_DIM, EmbeddingProvider
from jobscout.llm.base import LLMProvider
from jobscout.models import Job


class FakeProvider(EmbeddingProvider):
    """Embeds each text to a vector keyed on its length, so texts that
    share words end up closer together than unrelated ones — enough
    signal for rank-ordering assertions without a real model."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text) % 97)] + [0.0] * (EMBEDDING_DIM - 1) for text in texts]


class FakeLLMProvider(LLMProvider):
    """Deterministic, no-network cover-letter "generation" for tests."""

    async def generate(self, prompt: str) -> str:
        return f"Cover letter for prompt of length {len(prompt)}."


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
    app = create_app(
        session_factory=session_factory,
        embedding_provider=FakeProvider(),
        llm_provider=FakeLLMProvider(),
    )
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


async def test_skill_gap_404_without_a_profile(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/skill-gap", params={"role": "Data Engineer"})
    assert response.status_code == 404


async def test_skill_gap_returns_frequency_diff_against_matching_postings(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        session.add_all(
            [
                make_job(
                    canonical_url="https://example.com/1",
                    title="Senior Data Engineer",
                    description="Python and Kubernetes required.",
                ),
                make_job(
                    canonical_url="https://example.com/2",
                    title="Data Engineer II",
                    description="Python and Docker required.",
                ),
            ]
        )
        await session.commit()

    await client.post(
        "/api/profile",
        files={"resume": ("resume.txt", b"Experienced Python engineer.", "text/plain")},
    )

    response = await client.get("/api/skill-gap", params={"role": "Data Engineer"})
    assert response.status_code == 200
    body = response.json()
    assert body["postings_considered"] == 2
    missing = {entry["keyword"] for entry in body["missing_keywords"]}
    assert "kubernetes" in missing
    assert "docker" in missing


async def test_skill_gap_returns_empty_result_for_unmatched_role(
    client: httpx.AsyncClient,
) -> None:
    await client.post(
        "/api/profile",
        files={"resume": ("resume.txt", b"Experienced Python engineer.", "text/plain")},
    )

    response = await client.get("/api/skill-gap", params={"role": "Nonexistent Role"})
    assert response.status_code == 200
    assert response.json()["postings_considered"] == 0


async def test_tailoring_404_without_profile_or_unknown_job(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        job = make_job()
        session.add(job)
        await session.commit()
        job_id = job.id

    assert (await client.get(f"/api/jobs/{job_id}/tailoring")).status_code == 404

    await client.post(
        "/api/profile",
        files={"resume": ("resume.txt", b"Experienced Python engineer.", "text/plain")},
    )
    assert (await client.get("/api/jobs/999/tailoring")).status_code == 404


async def test_tailoring_returns_matched_and_missing_keywords(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        job = make_job(description="Build data pipelines with Python and Kubernetes.")
        session.add(job)
        await session.commit()
        job_id = job.id

    await client.post(
        "/api/profile",
        files={"resume": ("resume.txt", b"Experienced Python engineer.", "text/plain")},
    )

    response = await client.get(f"/api/jobs/{job_id}/tailoring")
    assert response.status_code == 200
    body = response.json()
    assert "python" in body["matched_keywords"]
    assert "kubernetes" in body["missing_keywords"]


def _parse_timestamp(value: str) -> datetime:
    # sqlite (unlike Postgres) doesn't preserve tzinfo across separate
    # sessions, so a value re-read in a later request may come back
    # without the "Z" suffix even though it's the same instant.
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


async def test_cover_letter_404_before_generation_then_persists_and_regenerates(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        job = make_job()
        session.add(job)
        await session.commit()
        job_id = job.id

    assert (await client.get(f"/api/jobs/{job_id}/cover-letter")).status_code == 404
    assert (await client.post(f"/api/jobs/{job_id}/cover-letter")).status_code == 404  # no profile

    await client.post(
        "/api/profile",
        files={"resume": ("resume.txt", b"Experienced Python engineer.", "text/plain")},
    )

    first = await client.post(f"/api/jobs/{job_id}/cover-letter")
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["content"]
    created_at = first_body["created_at"]

    fetched = await client.get(f"/api/jobs/{job_id}/cover-letter")
    assert fetched.status_code == 200
    assert fetched.json()["content"] == first_body["content"]

    second = await client.post(f"/api/jobs/{job_id}/cover-letter")
    assert second.status_code == 200
    second_body = second.json()
    assert _parse_timestamp(second_body["created_at"]) == _parse_timestamp(created_at)
    assert _parse_timestamp(second_body["updated_at"]) >= _parse_timestamp(first_body["updated_at"])


async def test_cover_letter_404_for_unknown_job(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/jobs/999/cover-letter")).status_code == 404


async def test_tracking_update_404_if_not_saved(client: httpx.AsyncClient) -> None:
    response = await client.patch("/api/jobs/999/tracking", json={"notes": "Follow up"})
    assert response.status_code == 404


async def test_tracking_update_reflected_in_saved_list(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        job = make_job()
        session.add(job)
        await session.commit()
        job_id = job.id

    await client.post(f"/api/jobs/{job_id}/save")

    reminder_at = datetime(2026, 8, 1, tzinfo=UTC).isoformat()
    update = await client.patch(
        f"/api/jobs/{job_id}/tracking", json={"reminder_at": reminder_at, "notes": "Follow up"}
    )
    assert update.status_code == 200
    assert update.json()["notes"] == "Follow up"

    listed = await client.get("/api/saved")
    [entry] = listed.json()
    assert entry["notes"] == "Follow up"
    assert entry["reminder_at"] is not None


async def test_reminders_returns_only_due_rows_soonest_first(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        soon = make_job(canonical_url="https://example.com/soon")
        later = make_job(canonical_url="https://example.com/later")
        no_reminder = make_job(canonical_url="https://example.com/none")
        session.add_all([soon, later, no_reminder])
        await session.commit()
        soon_id, later_id, no_reminder_id = soon.id, later.id, no_reminder.id

    for job_id in (soon_id, later_id, no_reminder_id):
        await client.post(f"/api/jobs/{job_id}/save")

    await client.patch(
        f"/api/jobs/{later_id}/tracking",
        json={"reminder_at": datetime(2026, 3, 1, tzinfo=UTC).isoformat()},
    )
    await client.patch(
        f"/api/jobs/{soon_id}/tracking",
        json={"reminder_at": datetime(2026, 2, 1, tzinfo=UTC).isoformat()},
    )

    response = await client.get("/api/reminders", params={"within_hours": 24 * 365 * 10})
    assert response.status_code == 200
    job_ids = [entry["job"]["id"] for entry in response.json()]
    assert job_ids == [soon_id, later_id]


async def test_status_transitions_stamp_timeline_timestamps(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        job = make_job()
        session.add(job)
        await session.commit()
        job_id = job.id

    await client.post(f"/api/jobs/{job_id}/save")
    await client.patch(f"/api/jobs/{job_id}/save", json={"status": "applied"})
    await client.patch(f"/api/jobs/{job_id}/save", json={"status": "interviewing"})

    listed = await client.get("/api/saved")
    [entry] = listed.json()
    assert entry["applied_at"] is not None
    assert entry["interviewing_at"] is not None
    assert entry["rejected_at"] is None
