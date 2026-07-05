"""Pipeline tests: fetch -> normalize -> dedupe -> store (PLAN.md Phase 1)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.models import Job, JobPosting
from jobscout.pipeline import ingest
from jobscout.sources.base import JobSource, RawPosting


class HiringCafeFake(JobSource):
    name = "hiring_cafe"

    def __init__(self, postings: list[RawPosting]) -> None:
        self._postings = postings

    async def fetch(self) -> AsyncIterator[RawPosting]:
        for posting in self._postings:
            yield posting


class GreenhouseFake(JobSource):
    name = "greenhouse"

    def __init__(self, postings: list[RawPosting]) -> None:
        self._postings = postings

    async def fetch(self) -> AsyncIterator[RawPosting]:
        for posting in self._postings:
            yield posting


def make_posting(**overrides: object) -> RawPosting:
    defaults: dict[str, object] = {
        "source": "hiring_cafe",
        "external_id": "1",
        "url": "https://example.com/jobs/1",
        "title": "Data Engineer",
        "company": "Acme Corp",
        "fetched_at": datetime.now(tz=UTC),
        "raw": {"id": "1"},
    }
    return RawPosting(**{**defaults, **overrides})  # type: ignore[arg-type]


async def job_count(session: AsyncSession) -> int:
    return (await session.scalar(select(func.count()).select_from(Job))) or 0


async def posting_count(session: AsyncSession) -> int:
    return (await session.scalar(select(func.count()).select_from(JobPosting))) or 0


async def test_new_posting_creates_a_job(session: AsyncSession) -> None:
    stats = await ingest([HiringCafeFake([make_posting()])], session)

    assert stats.jobs_created == 1
    assert stats.fetched_by_source == {"hiring_cafe": 1}
    assert await job_count(session) == 1
    assert await posting_count(session) == 1


async def test_repeat_external_id_updates_instead_of_duplicating(session: AsyncSession) -> None:
    first_seen = datetime(2026, 1, 1, tzinfo=UTC)
    later = datetime(2026, 1, 2, tzinfo=UTC)

    await ingest([HiringCafeFake([make_posting(fetched_at=first_seen)])], session)
    stats = await ingest(
        [HiringCafeFake([make_posting(fetched_at=later, raw={"id": "1", "v": 2})])],
        session,
    )

    assert stats.jobs_created == 0
    assert stats.postings_updated == 1
    assert await job_count(session) == 1

    job = await session.scalar(select(Job))
    assert job is not None
    assert job.first_seen == first_seen
    assert job.last_seen == later


async def test_same_canonical_url_from_different_source_merges(session: AsyncSession) -> None:
    await ingest(
        [HiringCafeFake([make_posting(source="hiring_cafe", external_id="1")])],
        session,
    )
    await ingest(
        [
            GreenhouseFake(
                [
                    make_posting(
                        source="greenhouse",
                        external_id="gh-1",
                        url="https://example.com/jobs/1?utm_source=x",
                        title="Different Title Text",
                        company="Someone Else",
                    )
                ],
            )
        ],
        session,
    )

    assert await job_count(session) == 1
    assert await posting_count(session) == 2


async def test_same_normalized_title_and_company_merges(session: AsyncSession) -> None:
    await ingest(
        [
            HiringCafeFake(
                [make_posting(url="https://a.example.com/1", title="Senior  Data Engineer ")],
            )
        ],
        session,
    )
    await ingest(
        [
            GreenhouseFake(
                [
                    make_posting(
                        source="greenhouse",
                        external_id="gh-2",
                        url="https://boards.greenhouse.io/acme/jobs/2",
                        title="senior data engineer",
                        company="acme corp",
                    )
                ],
            )
        ],
        session,
    )

    assert await job_count(session) == 1
    assert await posting_count(session) == 2


async def test_different_jobs_stay_separate(session: AsyncSession) -> None:
    await ingest(
        [
            HiringCafeFake(
                [
                    make_posting(
                        external_id="1", url="https://a.example.com/1", title="Data Engineer"
                    ),
                    make_posting(
                        external_id="2",
                        url="https://a.example.com/2",
                        title="Product Manager",
                        company="Other Co",
                    ),
                ],
            )
        ],
        session,
    )

    assert await job_count(session) == 2
    assert await posting_count(session) == 2
