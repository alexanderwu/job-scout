"""Integration tests: embed batch + ranked matching against real pgvector.

Same philosophy as test_pipeline.py — the ANN query, signature filter,
and SQL filters are Postgres behavior, so they're tested on Postgres.
The HashingProvider keeps it dependency-free: for these corpora,
lexical similarity is plenty to make rankings assert-able.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.matching.embed_jobs import embed_pending_jobs
from jobscout.matching.embeddings import HashingProvider
from jobscout.matching.engine import MatchFilters, match_resume
from jobscout.models import Job

NOW = datetime.now(tz=UTC)

RESUME = """
Data engineer with 6 years of Python, SQL, Airflow and Spark.
Built streaming pipelines on Kafka and warehouses on Snowflake.
"""


def job(**overrides: Any) -> Job:
    defaults: dict[str, Any] = {
        "title": "Data Engineer",
        "company": "Acme",
        "location": "San Francisco, CA",
        "description": "Python SQL Airflow pipelines",
        "title_norm": "data engineer",
        "company_norm": "acme",
        "location_norm": "san francisco ca",
        "first_seen": NOW,
        "last_seen": NOW,
    }
    return Job(**{**defaults, **overrides})


async def seed(session: AsyncSession, *jobs: Job) -> None:
    session.add_all(jobs)
    await session.commit()


async def test_embed_pending_then_noop(db_session: AsyncSession) -> None:
    await seed(db_session, job(), job(title="ML Engineer", title_norm="ml engineer"))
    provider = HashingProvider()

    first = await embed_pending_jobs(db_session, provider)
    second = await embed_pending_jobs(db_session, provider)

    assert first.embedded == 2
    assert second.embedded == 0  # already current: no re-work
    sigs = set(await db_session.scalars(select(Job.embedding_sig)))
    assert sigs == {provider.signature}


async def test_signature_change_triggers_reembed(db_session: AsyncSession) -> None:
    await seed(db_session, job())
    await embed_pending_jobs(db_session, HashingProvider())

    changed = HashingProvider()
    changed.dimension = 384  # same dim (schema-compatible)...

    class V2(HashingProvider):
        @property
        def signature(self) -> str:
            return "hashing:v2-test:384"

    stats = await embed_pending_jobs(db_session, V2())
    assert stats.embedded == 1  # old-signature vector counted as stale


async def test_match_ranks_relevant_job_first_with_reasoning(db_session: AsyncSession) -> None:
    await seed(
        db_session,
        job(
            title="Senior Data Engineer",
            title_norm="senior data engineer",
            description="Own our Python + SQL + Airflow + Kafka pipelines.",
        ),
        job(
            title="Brand Designer",
            title_norm="brand designer",
            company="Pixel",
            company_norm="pixel",
            description="Figma, typography, illustration.",
        ),
    )
    provider = HashingProvider()
    await embed_pending_jobs(db_session, provider)

    result = await match_resume(db_session, provider, RESUME, limit=10)

    titles = [m.job.title for m in result.matches]
    assert titles[0] == "Senior Data Engineer"
    top = result.matches[0]
    assert top.score > result.matches[1].score
    assert "Python" in top.explanation.overlapping
    assert "Airflow" in top.explanation.overlapping
    # The designer job shares no skills; its explanation says so honestly.
    assert "no specific shared skills" in result.matches[1].explanation.summary()


async def test_match_result_usable_after_session_close(db_session: AsyncSession) -> None:
    """Regression: the CLI reads job.postings after the session closed.

    Async SQLAlchemy raises on post-session lazy loads instead of
    silently querying (sync behavior), so the engine must eager-load
    everything a caller renders.
    """
    from jobscout.ingest.pipeline import SourceStats, upsert_posting
    from jobscout.sources.base import RawPosting

    raw = RawPosting(
        source="t",
        external_id="x1",
        url="https://ex.com/apply/1",
        title="Data Engineer",
        company="Acme",
        fetched_at=NOW,
        description="Python SQL",
        raw={},
    )
    await upsert_posting(db_session, raw, SourceStats(source="t"))
    await db_session.commit()
    provider = HashingProvider()
    await embed_pending_jobs(db_session, provider)

    result = await match_resume(db_session, provider, RESUME)
    await db_session.close()

    assert result.matches[0].job.postings[0].url == "https://ex.com/apply/1"


async def test_match_ignores_other_signature_vectors(db_session: AsyncSession) -> None:
    await seed(db_session, job())
    await embed_pending_jobs(db_session, HashingProvider())

    class Other(HashingProvider):
        @property
        def signature(self) -> str:
            return "hashing:other:384"

    # Same dimension, different declared space: those vectors are
    # invisible to this provider's search — never silently compared.
    result = await match_resume(db_session, Other(), RESUME)
    assert result.matches == []


async def test_filters_salary_remote_location_and_staleness(db_session: AsyncSession) -> None:
    await seed(
        db_session,
        job(
            title="DE Remote High",
            title_norm="de remote high",
            remote=True,
            salary_min=150_000,
            salary_max=190_000,
        ),
        job(
            title="DE Onsite Low",
            title_norm="de onsite low",
            remote=False,
            salary_min=90_000,
            salary_max=120_000,
            location="Austin, TX",
            location_norm="austin tx",
        ),
        job(
            title="DE Stale",
            title_norm="de stale",
            remote=True,
            salary_max=200_000,
            first_seen=NOW - timedelta(days=90),
            last_seen=NOW - timedelta(days=60),
        ),
    )
    provider = HashingProvider()
    await embed_pending_jobs(db_session, provider)

    remote_high = await match_resume(
        db_session,
        provider,
        RESUME,
        filters=MatchFilters(remote_only=True, min_salary=150_000),
    )
    assert [m.job.title for m in remote_high.matches] == ["DE Remote High"]

    austin = await match_resume(
        db_session, provider, RESUME, filters=MatchFilters(location_contains="austin")
    )
    assert [m.job.title for m in austin.matches] == ["DE Onsite Low"]

    default = await match_resume(db_session, provider, RESUME)
    assert "DE Stale" not in [m.job.title for m in default.matches]
