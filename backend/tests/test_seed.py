"""Seeder tests: it must produce the world the demo features expect."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.models import Job, Posting
from jobscout.seed import seed, wipe_seed_data


async def test_seed_builds_weeks_of_history(db_session: AsyncSession) -> None:
    stats = await seed(db_session, weeks=4, jobs_per_week=6)

    jobs = (await db_session.scalars(select(Job))).all()
    assert stats.new_jobs == len(jobs) > 0
    assert stats.cross_posts > 0  # dedupe tiers actually exercised

    # History really spans weeks (trends need > 1 bucket)...
    oldest = min(j.first_seen for j in jobs)
    assert oldest < datetime.now(tz=UTC) - timedelta(weeks=2)
    # ...and both fresh and stale jobs exist (staleness features).
    now = datetime.now(tz=UTC)
    fresh = [j for j in jobs if j.last_seen > now - timedelta(days=2)]
    stale = [j for j in jobs if j.last_seen <= now - timedelta(days=2)]
    assert fresh
    assert stale
    # Salary + descriptions present so insights/matching have data.
    assert all(j.salary_min for j in jobs)
    assert all(j.description for j in jobs)


async def test_seed_is_deterministic(db_session: AsyncSession) -> None:
    first = await seed(db_session, weeks=2, jobs_per_week=5, wipe=True)
    second = await seed(db_session, weeks=2, jobs_per_week=5, wipe=True)
    assert first.new_jobs == second.new_jobs
    assert first.cross_posts == second.cross_posts


async def test_wipe_removes_only_seeded_rows(db_session: AsyncSession) -> None:
    now = datetime.now(tz=UTC)
    real = Job(
        title="Real Job",
        title_norm="real job",
        company="Real Co",
        company_norm="real co",
        first_seen=now,
        last_seen=now,
    )
    db_session.add(real)
    await db_session.commit()
    await seed(db_session, weeks=1, jobs_per_week=3)

    removed = await wipe_seed_data(db_session)

    assert removed >= 3
    remaining = (await db_session.scalars(select(Job.title))).all()
    assert remaining == ["Real Job"]
    orphaned = await db_session.scalar(select(func.count()).select_from(Posting))
    assert orphaned == 0  # cascade cleaned the postings too
