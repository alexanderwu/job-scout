"""Integration tests: the dedupe tiers against a real Postgres.

Each test tells one dedupe story end to end. The source is a tiny
in-memory JobSource — the adapter tests already cover HTTP; here the
subject is what the pipeline does with postings once it has them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.ingest.pipeline import ingest_all
from jobscout.models import Job, Posting
from jobscout.sources.base import JobSource, RawPosting

T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


class ListSource(JobSource):
    """A JobSource that yields a canned list — the test double the
    adapter interface was designed to make trivial."""

    name = "test"

    def __init__(self, postings: list[RawPosting], name: str = "test") -> None:
        self._postings = postings
        # ClassVar in the contract, but per-instance here so one test
        # can simulate two distinct sources.
        self.name = name  # type: ignore[misc]

    async def fetch(self) -> AsyncIterator[RawPosting]:
        for p in self._postings:
            yield p


class BrokenSource(JobSource):
    name = "broken"

    async def fetch(self) -> AsyncIterator[RawPosting]:
        raise RuntimeError("API shape changed under us")
        yield  # pragma: no cover - makes this an async generator


def posting(**overrides: Any) -> RawPosting:
    defaults: dict[str, Any] = {
        "source": "test",
        "external_id": "ext-1",
        "url": "https://jobs.example.com/1",
        "title": "Data Engineer",
        "company": "Acme",
        "location": "SF",
        "fetched_at": T0,
        "raw": {"k": "v"},
    }
    return RawPosting(**{**defaults, **overrides})


async def counts(session: AsyncSession) -> tuple[int, int]:
    jobs = await session.scalar(select(func.count()).select_from(Job))
    postings = await session.scalar(select(func.count()).select_from(Posting))
    assert jobs is not None
    assert postings is not None
    return jobs, postings


async def test_new_posting_creates_job_and_posting(db_session: AsyncSession) -> None:
    report = await ingest_all(db_session, [ListSource([posting()])])

    assert (await counts(db_session)) == (1, 1)
    assert report.sources[0].new_jobs == 1
    job = (await db_session.scalars(select(Job))).one()
    assert job.title == "Data Engineer"
    assert job.title_norm == "data engineer"
    assert job.first_seen == job.last_seen == T0


async def test_tier1a_same_posting_refreshes_not_duplicates(db_session: AsyncSession) -> None:
    await ingest_all(db_session, [ListSource([posting()])])
    later = T0 + timedelta(days=1)
    report = await ingest_all(
        db_session, [ListSource([posting(fetched_at=later, raw={"k": "v2"})])]
    )

    assert (await counts(db_session)) == (1, 1)
    assert report.sources[0].refreshed == 1
    row = (await db_session.scalars(select(Posting))).one()
    assert row.first_seen == T0
    assert row.last_seen == later
    assert row.raw == {"k": "v2"}  # latest payload kept for re-normalization
    job = (await db_session.scalars(select(Job))).one()
    assert job.last_seen == later


async def test_tier1b_same_canonical_url_cross_source(db_session: AsyncSession) -> None:
    await ingest_all(db_session, [ListSource([posting()], name="greenhouse")])
    # Another source, its own ID, tracking params on the same URL.
    cross = posting(
        source="hiring_cafe",
        external_id="hc-9",
        url="https://jobs.example.com/1?utm_source=aggregator",
    )
    report = await ingest_all(db_session, [ListSource([cross], name="hiring_cafe")])

    assert (await counts(db_session)) == (1, 2)  # one job, two postings
    assert report.sources[0].cross_posts == 1


async def test_tier2_title_company_location_match(db_session: AsyncSession) -> None:
    await ingest_all(db_session, [ListSource([posting()])])
    same_role = posting(
        source="other",
        external_id="o-1",
        url="https://completely.different.example/apply/42",
        title="Data  Engineer",  # normalizes identically
        company="Acme, Inc.",  # suffix ignored
    )
    await ingest_all(db_session, [ListSource([same_role], name="other")])

    assert (await counts(db_session)) == (1, 2)


async def test_tier2_requires_matching_location(db_session: AsyncSession) -> None:
    await ingest_all(db_session, [ListSource([posting()])])
    other_city = posting(external_id="ext-2", url="https://x.example/2", location="NYC")
    await ingest_all(db_session, [ListSource([other_city])])

    # Same title+company, different city: two jobs, on purpose.
    assert (await counts(db_session)) == (2, 2)


async def test_tier2_skipped_without_company(db_session: AsyncSession) -> None:
    await ingest_all(db_session, [ListSource([posting(company=None)])])
    lookalike = posting(company=None, external_id="ext-2", url="https://x.example/2")
    await ingest_all(db_session, [ListSource([lookalike])])

    # Title alone is too weak a key to merge on.
    assert (await counts(db_session)) == (2, 2)


async def test_backfill_fills_gaps_but_never_overwrites(db_session: AsyncSession) -> None:
    await ingest_all(db_session, [ListSource([posting(description=None, salary_min=None)])])
    richer = posting(
        source="other",
        external_id="o-1",
        url="https://jobs.example.com/1",  # tier 1b match
        description="Great job. $150,000 - $180,000.",
        salary_min=150_000,
        salary_max=180_000,
        salary_currency="USD",
    )
    await ingest_all(db_session, [ListSource([richer], name="other")])

    job = (await db_session.scalars(select(Job))).one()
    assert job.description == "Great job. $150,000 - $180,000."
    assert (job.salary_min, job.salary_max) == (150_000, 180_000)
    assert job.title == "Data Engineer"  # original display fields kept


async def test_salary_regex_fallback_from_description(db_session: AsyncSession) -> None:
    await ingest_all(
        db_session,
        [ListSource([posting(description="Pay: $120k-$150k plus equity")])],
    )
    job = (await db_session.scalars(select(Job))).one()
    assert (job.salary_min, job.salary_max, job.salary_currency) == (120_000, 150_000, "USD")


async def test_one_broken_source_does_not_block_others(db_session: AsyncSession) -> None:
    report = await ingest_all(db_session, [BrokenSource(), ListSource([posting()])])

    assert (await counts(db_session)) == (1, 1)
    broken, ok = report.sources
    assert broken.failed
    assert broken.error is not None
    assert "RuntimeError" in broken.error
    assert not ok.failed
    assert ok.new_jobs == 1
