from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.models import Job
from jobscout.queries import jobs_first_seen_since


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
