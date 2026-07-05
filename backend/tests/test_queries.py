from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.embeddings.base import EMBEDDING_DIM
from jobscout.models import Job
from jobscout.queries import (
    delete_saved_job,
    get_profile,
    get_saved_job,
    jobs_first_seen_since,
    jobs_missing_embeddings,
    jobs_with_embeddings,
    list_saved_jobs,
    search_jobs,
    upsert_profile,
    upsert_saved_job_status,
)


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


async def test_search_jobs_orders_by_first_seen_desc_and_paginates(session: AsyncSession) -> None:
    old = make_job(
        canonical_url="https://example.com/old", first_seen=datetime(2026, 1, 1, tzinfo=UTC)
    )
    mid = make_job(
        canonical_url="https://example.com/mid", first_seen=datetime(2026, 2, 1, tzinfo=UTC)
    )
    new = make_job(
        canonical_url="https://example.com/new", first_seen=datetime(2026, 3, 1, tzinfo=UTC)
    )
    session.add_all([old, mid, new])
    await session.commit()

    page1 = await search_jobs(session, limit=2)
    assert [job.canonical_url for job in page1] == [
        "https://example.com/new",
        "https://example.com/mid",
    ]

    page2 = await search_jobs(session, limit=2, offset=2)
    assert [job.canonical_url for job in page2] == ["https://example.com/old"]


async def test_search_jobs_filters_by_location(session: AsyncSession) -> None:
    sf_job = make_job(canonical_url="https://example.com/sf", location="San Francisco, CA")
    ny_job = make_job(canonical_url="https://example.com/ny", location="New York, NY")
    session.add_all([sf_job, ny_job])
    await session.commit()

    result = await search_jobs(session, location="San Francisco")
    assert [job.canonical_url for job in result] == ["https://example.com/sf"]


async def test_upsert_profile_creates_then_replaces_the_single_row(session: AsyncSession) -> None:
    assert await get_profile(session) is None

    created = await upsert_profile(
        session,
        resume_text="Python engineer.",
        embedding=make_embedding(0.1),
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await session.commit()
    assert created.resume_text == "Python engineer."

    updated = await upsert_profile(
        session,
        resume_text="Python and Go engineer.",
        embedding=make_embedding(0.2),
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    await session.commit()

    assert updated.id == created.id
    fetched = await get_profile(session)
    assert fetched is not None
    assert fetched.resume_text == "Python and Go engineer."


async def test_saved_job_lifecycle(session: AsyncSession) -> None:
    job = make_job(canonical_url="https://example.com/1")
    session.add(job)
    await session.commit()

    assert await get_saved_job(session, job.id) is None

    saved = await upsert_saved_job_status(
        session, job.id, "saved", now=datetime(2026, 1, 1, tzinfo=UTC)
    )
    await session.commit()
    assert saved.status == "saved"

    updated = await upsert_saved_job_status(
        session, job.id, "applied", now=datetime(2026, 1, 2, tzinfo=UTC)
    )
    await session.commit()
    assert updated.id == saved.id
    assert updated.status == "applied"

    listed = await list_saved_jobs(session)
    assert [s.job_id for s in listed] == [job.id]
    assert listed[0].job.canonical_url == "https://example.com/1"

    assert await delete_saved_job(session, job.id) is True
    assert await get_saved_job(session, job.id) is None
    assert await delete_saved_job(session, job.id) is False
