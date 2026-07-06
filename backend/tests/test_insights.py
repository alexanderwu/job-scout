"""Insights aggregations against real Postgres (percentile_cont etc.)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.insights import salary_report, skill_trends
from jobscout.models import Job

NOW = datetime.now(tz=UTC)


def job(**overrides: Any) -> Job:
    defaults: dict[str, Any] = {
        "title": "Data Engineer",
        "title_norm": "data engineer",
        "company": "Acme",
        "company_norm": "acme",
        "location": "Remote",
        "first_seen": NOW,
        "last_seen": NOW,
    }
    return Job(**{**defaults, **overrides})


async def test_salary_percentiles_and_locations(db_session: AsyncSession) -> None:
    salaries = [(100, 120), (120, 140), (140, 160), (200, 240)]  # midpoints 110,130,150,220 (k)
    for i, (lo, hi) in enumerate(salaries):
        db_session.add(
            job(
                company=f"C{i}",
                company_norm=f"c{i}",
                location="Remote" if i < 3 else "New York, NY",
                salary_min=lo * 1000,
                salary_max=hi * 1000,
            )
        )
    db_session.add(job(company="NoPay", company_norm="nopay", location="Berlin"))
    await db_session.commit()

    report = await salary_report(db_session)

    assert report.overall.count == 4  # the salary-less job is excluded
    assert report.overall.median == 140_000  # (130k+150k)/2
    assert report.overall.p25 == 125_000
    assert report.overall.p75 == 167_500
    locations = {e.location: e.stats for e in report.by_location}
    assert locations["Remote"].count == 3
    assert locations["Remote"].median == 130_000
    assert locations["New York, NY"].median == 220_000
    assert "Berlin" not in locations  # nothing with pay there


async def test_salary_role_filter(db_session: AsyncSession) -> None:
    db_session.add(job(salary_min=100_000, salary_max=120_000))
    db_session.add(
        job(
            title="Product Designer",
            title_norm="product designer",
            company="P",
            company_norm="p",
            salary_min=300_000,
            salary_max=300_000,
        )
    )
    await db_session.commit()

    report = await salary_report(db_session, role="data engineer")
    assert report.overall.count == 1
    assert report.overall.median == 110_000


async def test_skill_trends_weekly_buckets(db_session: AsyncSession) -> None:
    this_week = NOW
    two_weeks_ago = NOW - timedelta(weeks=2)
    db_session.add(job(description="Python SQL", first_seen=this_week, last_seen=NOW))
    db_session.add(
        job(
            company="B",
            company_norm="b",
            description="Python Kafka",
            first_seen=two_weeks_ago,
            last_seen=NOW,
        )
    )
    await db_session.commit()

    report = await skill_trends(db_session, weeks=4)

    assert report.sampled_jobs == 2
    by_skill = {t.skill: t for t in report.skills}
    python = by_skill["Python"]
    assert python.total == 2
    assert len(python.weekly) == 4  # dense series, zeros included
    assert sum(w.count for w in python.weekly) == 2
    assert by_skill["Kafka"].total == 1
    # weeks are aligned across skills so sparklines line up
    assert [w.week_start for w in python.weekly] == [w.week_start for w in by_skill["Kafka"].weekly]
