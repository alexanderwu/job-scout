from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.embeddings.base import EMBEDDING_DIM
from jobscout.models import Job
from jobscout.queries import jobs_first_seen_since, jobs_missing_embeddings, jobs_with_embeddings


def make_embedding(seed: float) -> list[float]:
    return [seed] + [0.0] * (EMBEDDING_DIM - 1)


def make_job(**overrides: object) -> Job:
    defaults: dict[str, object] = {
        "normalized_title": "data engineer",
        "normalized_company": "acme corp",
        "canonical_url": "https://example.com/1",
        "title": "Data Engineer",
        "company": "Acme Corp",
        "location": None,
        "posted_at": None,
        "first_seen": datetime(2026, 1, 1, tzinfo=UTC),
        "last_seen": datetime(2026, 1, 1, tzinfo=UTC),
    }
    return Job(**{**defaults, **overrides})


async def test_jobs_first_seen_since_filters_and_orders(session: AsyncSession) -> None:
    old = make_job(
        canonical_url="https://example.com/old", first_seen=datetime(2025, 1, 1, tzinfo=UTC)
    )
    recent = make_job(
        canonical_url="https://example.com/recent", first_seen=datetime(2026, 6, 1, tzinfo=UTC)
    )
    newest = make_job(
        canonical_url="https://example.com/newest", first_seen=datetime(2026, 6, 15, tzinfo=UTC)
    )
    session.add_all([old, recent, newest])
    await session.commit()

    result = await jobs_first_seen_since(session, since=datetime(2026, 1, 1, tzinfo=UTC))

    assert [job.canonical_url for job in result] == [
        "https://example.com/newest",
        "https://example.com/recent",
    ]


async def test_jobs_missing_embeddings_excludes_embedded_and_description_less_jobs(
    session: AsyncSession,
) -> None:
    no_description = make_job(canonical_url="https://example.com/1", description=None)
    pending = make_job(
        canonical_url="https://example.com/2", description="Build things.", embedding=None
    )
    already_embedded = make_job(
        canonical_url="https://example.com/3",
        description="Build other things.",
        embedding=make_embedding(0.1),
    )
    session.add_all([no_description, pending, already_embedded])
    await session.commit()

    result = await jobs_missing_embeddings(session)

    assert [job.canonical_url for job in result] == ["https://example.com/2"]


async def test_jobs_with_embeddings_filters_by_location(session: AsyncSession) -> None:
    sf_job = make_job(
        canonical_url="https://example.com/sf",
        location="San Francisco, CA",
        embedding=make_embedding(0.1),
    )
    ny_job = make_job(
        canonical_url="https://example.com/ny",
        location="New York, NY",
        embedding=make_embedding(0.3),
    )
    unembedded = make_job(canonical_url="https://example.com/none", embedding=None)
    session.add_all([sf_job, ny_job, unembedded])
    await session.commit()

    all_embedded = await jobs_with_embeddings(session)
    assert {job.canonical_url for job in all_embedded} == {
        "https://example.com/sf",
        "https://example.com/ny",
    }

    sf_only = await jobs_with_embeddings(session, location="San Francisco")
    assert [job.canonical_url for job in sf_only] == ["https://example.com/sf"]
