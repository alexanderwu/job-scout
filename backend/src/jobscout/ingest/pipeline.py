"""Ingest postings from sources into Postgres, deduplicating as we go.

Dedupe tiers (PLAN.md Phase 1), cheapest first — each tier only runs if
the previous one found nothing:

1a. ``(source, external_id)`` already known -> the *same posting* seen
    again. Refresh ``last_seen``/``raw``; no new rows. This is the hot
    path on every scheduled run (most postings persist day to day).
1b. Another posting has the same canonical URL -> a *cross-post* of a
    job we already track (e.g. hiring.cafe mirroring a Greenhouse ad
    that links to the same application page). New posting row, attached
    to the existing job.
2.  A job matches on normalized (title, company, location) -> same role
    advertised at different URLs. New posting row on that job.
3.  (Phase 2 bonus, not here) embedding similarity for fuzzy cross-posts.

Tier 2 requires the *company* to be known on both sides and includes
location in the key. Both choices trade recall for precision: merging
"Software Engineer @ ? " with anything, or merging the SF and NYC
variants of a role, would silently corrupt jobs — while a missed merge
just leaves a duplicate row that tier 3 can catch later. Wrong merges
are hard to detect and undo; duplicates are visible and harmless.

Transaction shape: one commit per posting *batch* (``COMMIT_EVERY``).
Per-posting commits would hammer the DB for no benefit; one commit per
source would mean a crash on posting 9,000 loses 8,999 good rows,
violating the "keep everything yielded so far" promise in
sources/base.py. Batching is the standard middle ground.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.models import Job, Posting
from jobscout.normalize import (
    canonicalize_url,
    extract_salary,
    normalize_company,
    normalize_location,
    normalize_title,
)
from jobscout.sources.base import JobSource, RawPosting

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

COMMIT_EVERY = 50


@dataclass
class SourceStats:
    """What one source's ingestion run did — the pipeline's receipt."""

    source: str
    fetched: int = 0
    refreshed: int = 0  # tier 1a: posting seen again
    cross_posts: int = 0  # tier 1b/2: new posting on an existing job
    new_jobs: int = 0  # no tier matched: genuinely new
    failed: bool = False
    error: str | None = None


@dataclass
class IngestReport:
    started_at: datetime | None = None
    finished_at: datetime | None = None
    sources: list[SourceStats] = field(default_factory=list)


async def ingest_all(session: AsyncSession, sources: Sequence[JobSource]) -> IngestReport:
    """Run every source; one source failing never blocks the others.

    A broken source raises inside its own ``fetch()`` (per the JobSource
    contract) — we record the failure and move on, because "hiring.cafe
    changed their API" must not stop Greenhouse ingestion (the whole
    point of multi-source redundancy).
    """
    report = IngestReport(started_at=datetime.now(tz=UTC))
    for source in sources:
        stats = SourceStats(source=source.name)
        report.sources.append(stats)
        try:
            await _ingest_source(session, source, stats)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            stats.failed = True
            stats.error = f"{type(exc).__name__}: {exc}"
            logger.exception("source %s failed", source.name)
    report.finished_at = datetime.now(tz=UTC)
    return report


async def _ingest_source(session: AsyncSession, source: JobSource, stats: SourceStats) -> None:
    async for raw in source.fetch():
        await upsert_posting(session, raw, stats)
        stats.fetched += 1
        if stats.fetched % COMMIT_EVERY == 0:
            await session.commit()


async def upsert_posting(session: AsyncSession, raw: RawPosting, stats: SourceStats) -> Posting:
    """Apply the dedupe tiers to one incoming posting."""
    url_canon = canonicalize_url(raw.url)

    # Tier 1a — have we seen this exact posting before?
    existing = await session.scalar(
        select(Posting).where(Posting.source == raw.source, Posting.external_id == raw.external_id)
    )
    if existing is not None:
        _refresh_posting(existing, raw, url_canon)
        await _refresh_job(session, existing.job_id, raw)
        stats.refreshed += 1
        return existing

    job = await _find_job(session, raw, url_canon)
    if job is None:
        job = _new_job(raw)
        session.add(job)
        await session.flush()  # assign job.id before the posting references it
        stats.new_jobs += 1
    else:
        _backfill_job(job, raw)
        stats.cross_posts += 1

    posting = Posting(
        job_id=job.id,
        source=raw.source,
        external_id=raw.external_id,
        url=raw.url,
        url_canon=url_canon,
        title=raw.title,
        company=raw.company,
        location=raw.location,
        posted_at=raw.posted_at,
        first_seen=raw.fetched_at,
        last_seen=raw.fetched_at,
        raw=raw.raw,
    )
    session.add(posting)
    await session.flush()
    return posting


async def _find_job(session: AsyncSession, raw: RawPosting, url_canon: str) -> Job | None:
    # Tier 1b — same canonical URL from a different source.
    job_id = await session.scalar(select(Posting.job_id).where(Posting.url_canon == url_canon))
    if job_id is not None:
        return await session.get(Job, job_id)

    # Tier 2 — normalized title+company(+location) match. Skipped when
    # the company is unknown: title alone is far too weak a key.
    company_norm = normalize_company(raw.company)
    if company_norm is None:
        return None
    # scalars().first() instead of scalar(): identical SQL, but it keeps
    # the Job type for mypy where scalar() erases to Any.
    result = await session.scalars(
        select(Job).where(
            Job.title_norm == normalize_title(raw.title),
            Job.company_norm == company_norm,
            Job.location_norm == normalize_location(raw.location),
        )
    )
    return result.first()


def _new_job(raw: RawPosting) -> Job:
    salary_min, salary_max, currency = _salary_for(raw)
    return Job(
        title=raw.title,
        company=raw.company,
        location=raw.location,
        description=raw.description,
        title_norm=normalize_title(raw.title),
        company_norm=normalize_company(raw.company),
        location_norm=normalize_location(raw.location),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=currency,
        remote=raw.remote,
        first_seen=raw.fetched_at,
        last_seen=raw.fetched_at,
    )


def _refresh_posting(posting: Posting, raw: RawPosting, url_canon: str) -> None:
    """Tier 1a: same posting seen again — update evidence, keep identity."""
    posting.last_seen = raw.fetched_at
    posting.raw = raw.raw
    posting.url = raw.url
    posting.url_canon = url_canon
    posting.title = raw.title  # sources do edit titles in place


async def _refresh_job(session: AsyncSession, job_id: int, raw: RawPosting) -> None:
    job = await session.get(Job, job_id)
    if job is not None:
        job.last_seen = max(job.last_seen, raw.fetched_at)
        _backfill_job(job, raw)


def _backfill_job(job: Job, raw: RawPosting) -> None:
    """Fill job fields the job doesn't have yet from a fresher posting.

    Existing values are never overwritten: with multiple sources
    describing one job, "first source wins, others fill gaps" is
    predictable, while "latest fetch wins" would make job fields
    flip-flop depending on ingestion order.
    """
    job.last_seen = max(job.last_seen, raw.fetched_at)
    if job.description is None and raw.description is not None:
        job.description = raw.description
    if job.salary_min is None and job.salary_max is None:
        salary_min, salary_max, currency = _salary_for(raw)
        job.salary_min = salary_min
        job.salary_max = salary_max
        job.salary_currency = currency
    if job.remote is None:
        job.remote = raw.remote
    if job.location is None:
        job.location = raw.location
        job.location_norm = normalize_location(raw.location)


def _salary_for(raw: RawPosting) -> tuple[int | None, int | None, str | None]:
    """Structured comp from the source when present, else text fallback."""
    if raw.salary_min is not None or raw.salary_max is not None:
        return raw.salary_min, raw.salary_max, raw.salary_currency
    if raw.description:
        return extract_salary(raw.description)
    return None, None, None
