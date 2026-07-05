"""The Phase 1 ingestion pipeline: fetch -> normalize -> dedupe -> store.

Dedupe runs in the tiers PLAN.md specifies, cheapest first, stopping at
the first match:

1. Exact ``(source, external_id)`` match — we've already stored this
   exact posting; just refresh it.
2. Canonical-URL match — a different source pointing at the same URL
   (e.g. both linking straight to the same Greenhouse posting).
3. Normalized title + company match — same role, different URL, most
   likely a cross-posting fingerprinted by ATS-shaped text rather than
   its posting.

The pipeline itself never changes when a new ``JobSource`` is added
(PLAN.md guiding decision #2) — callers just pass a longer ``sources``
list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.models import Job, JobPosting
from jobscout.normalize import normalize_company, normalize_title, normalize_url
from jobscout.sources.base import JobSource, RawPosting


@dataclass
class IngestionStats:
    """Summary of one ``ingest()`` run, for CLI/log output."""

    fetched_by_source: dict[str, int] = field(default_factory=dict)
    jobs_created: int = 0
    postings_updated: int = 0


async def ingest(sources: list[JobSource], session: AsyncSession) -> IngestionStats:
    """Fetch every source and upsert into ``session`` (caller commits)."""
    stats = IngestionStats()
    for source in sources:
        count = 0
        async for posting in source.fetch():
            await _ingest_posting(session, posting, stats)
            count += 1
        stats.fetched_by_source[source.name] = count
    return stats


async def _ingest_posting(
    session: AsyncSession, posting: RawPosting, stats: IngestionStats
) -> None:
    existing_posting = await session.scalar(
        select(JobPosting).where(
            JobPosting.source == posting.source,
            JobPosting.external_id == posting.external_id,
        )
    )
    if existing_posting is not None:
        existing_posting.url = posting.url
        existing_posting.raw = posting.raw
        existing_posting.fetched_at = posting.fetched_at
        existing_posting.job.last_seen = max(
            _as_utc(existing_posting.job.last_seen), _as_utc(posting.fetched_at)
        )
        if posting.description is not None:
            existing_posting.job.description = posting.description
        _apply_salary(existing_posting.job, posting)
        stats.postings_updated += 1
        return

    canonical_url = normalize_url(posting.url)
    normalized_title = normalize_title(posting.title)
    normalized_company = normalize_company(posting.company)

    job = await session.scalar(select(Job).where(Job.canonical_url == canonical_url))
    if job is None and normalized_company is not None:
        job = await session.scalar(
            select(Job).where(
                Job.normalized_title == normalized_title,
                Job.normalized_company == normalized_company,
            )
        )

    if job is None:
        job = Job(
            normalized_title=normalized_title,
            normalized_company=normalized_company,
            canonical_url=canonical_url,
            title=posting.title,
            company=posting.company,
            location=posting.location,
            description=posting.description,
            posted_at=posting.posted_at,
            salary_min=posting.salary_min,
            salary_max=posting.salary_max,
            salary_currency=posting.salary_currency,
            first_seen=posting.fetched_at,
            last_seen=posting.fetched_at,
        )
        session.add(job)
        stats.jobs_created += 1
    else:
        job.last_seen = max(_as_utc(job.last_seen), _as_utc(posting.fetched_at))
        if posting.description is not None:
            job.description = posting.description
        _apply_salary(job, posting)

    session.add(
        JobPosting(
            job=job,
            source=posting.source,
            external_id=posting.external_id,
            url=posting.url,
            fetched_at=posting.fetched_at,
            raw=posting.raw,
        )
    )


def _as_utc(value: datetime) -> datetime:
    # asyncpg always returns tz-aware timestamps for our timestamptz
    # columns, but sqlite (test-only, see conftest.py) doesn't reliably
    # round-trip tzinfo across a re-fetch — a freshly-loaded ``Job`` can
    # come back with a naive ``last_seen`` and crash the ``max()``
    # comparison above against an aware ``fetched_at``. A no-op in
    # production; the same "assume UTC if naive" rule schemas.py already
    # applies to inbound reminder timestamps.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _apply_salary(job: Job, posting: RawPosting) -> None:
    """Refresh a job's comp figures from a re-fetched posting, same
    "only overwrite what the new posting actually reports" rule as
    ``description`` above — a later sighting with no salary data
    shouldn't blank out an earlier one that had it."""
    if posting.salary_min is not None:
        job.salary_min = posting.salary_min
    if posting.salary_max is not None:
        job.salary_max = posting.salary_max
    if posting.salary_currency is not None:
        job.salary_currency = posting.salary_currency
