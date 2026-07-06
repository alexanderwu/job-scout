"""The match engine: resume text in, ranked+explained jobs out.

The ranking query is one SQL statement: cosine distance between the
resume vector and each job's vector, ORDER BY distance, with plain
relational WHERE clauses for the hard filters. Doing filters in SQL
(not in Python after the ANN pass) matters: pgvector applies them
before/alongside the index scan, so "remote jobs over $150k" doesn't
require over-fetching thousands of candidates to survive
post-filtering. This one-statement-does-everything is exactly the
argument for pgvector over a separate vector DB (PLAN.md): relational
filters and vector search in the same engine, no sync problem.

Scores: cosine *similarity* (1 - distance), so higher = better, roughly
in [0, 1] for unit vectors. Displayed as a percentage; treat it as
ordinal ("this beats that"), not calibrated probability.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from jobscout.matching.embed_jobs import job_text
from jobscout.matching.embeddings import EmbeddingProvider
from jobscout.matching.explain import MatchExplanation, explain_match, extract_skills
from jobscout.models import Job

DEFAULT_MAX_AGE_DAYS = 45
"""Jobs not seen by ingestion for this long are presumed filled/closed
and excluded — staleness derived from evidence (last_seen), per the
models.py design note."""


@dataclass
class MatchFilters:
    """Hard constraints, applied in SQL before ranking."""

    location_contains: str | None = None
    remote_only: bool = False
    min_salary: int | None = None
    max_age_days: int = DEFAULT_MAX_AGE_DAYS


@dataclass
class JobMatch:
    job: Job
    score: float
    explanation: MatchExplanation


@dataclass
class MatchResult:
    matches: list[JobMatch] = field(default_factory=list)
    resume_skills: set[str] = field(default_factory=set)
    embeddable_jobs: int = 0
    """How many jobs carried a current-signature vector — 0 with a
    non-empty jobs table means "run `jobscout embed`", and the CLI says
    so instead of silently returning nothing."""


async def match_resume(
    session: AsyncSession,
    provider: EmbeddingProvider,
    resume_text: str,
    *,
    filters: MatchFilters | None = None,
    limit: int = 20,
) -> MatchResult:
    """Rank jobs against raw resume text (the CLI path).

    Embeds the query with the SAME provider the corpus used —
    embeddings.py explains why this is non-negotiable — then defers to
    :func:`rank_jobs`, which the API also uses with stored profile
    vectors.
    """
    (query_vec,) = await asyncio.to_thread(provider.embed, [resume_text])
    return await rank_jobs(
        session,
        provider,
        query_vec,
        extract_skills(resume_text),
        filters=filters,
        limit=limit,
    )


async def rank_jobs(
    session: AsyncSession,
    provider: EmbeddingProvider,
    query_vec: list[float],
    resume_skills: set[str],
    *,
    filters: MatchFilters | None = None,
    limit: int = 20,
    first_seen_after: datetime | None = None,
) -> MatchResult:
    """The one ranking query everything funnels through.

    ``first_seen_after`` powers the "new jobs for your profile" feed:
    same ranking, restricted to jobs that appeared since a timestamp.
    """
    filters = filters or MatchFilters()

    stmt = (
        select(Job, Job.embedding.cosine_distance(query_vec).label("distance"))
        # Eager-load postings: callers always want the apply URL, and
        # with the async engine a lazy load *after* the session closes
        # doesn't quietly run a query like sync SQLAlchemy would — it
        # raises. selectinload = one extra query for all rows, not N.
        .options(selectinload(Job.postings))
        .where(Job.embedding_sig == provider.signature)
        .where(Job.embedding.is_not(None))
    )
    if filters.max_age_days:
        cutoff = datetime.now(tz=UTC) - timedelta(days=filters.max_age_days)
        stmt = stmt.where(Job.last_seen >= cutoff)
    if filters.remote_only:
        stmt = stmt.where(Job.remote.is_(True))
    if filters.min_salary is not None:
        # A job qualifies if the top of its range clears the bar; jobs
        # with no salary data are excluded when the user filters on
        # salary (unknown ≠ qualifying), which is conservative but
        # honest — no bait rows the filter was meant to remove.
        stmt = stmt.where(Job.salary_max >= filters.min_salary)
    if filters.location_contains:
        stmt = stmt.where(Job.location.icontains(filters.location_contains))
    if first_seen_after is not None:
        stmt = stmt.where(Job.first_seen >= first_seen_after)
    stmt = stmt.order_by(Job.embedding.cosine_distance(query_vec)).limit(limit)

    rows = (await session.execute(stmt)).all()

    result = MatchResult(resume_skills=resume_skills, embeddable_jobs=len(rows))
    for job, distance in rows:
        result.matches.append(
            JobMatch(
                job=job,
                score=1.0 - float(distance),
                explanation=explain_match(resume_skills, job_text(job)),
            )
        )
    return result
