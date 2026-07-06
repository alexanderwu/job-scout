"""Market insights: what the ingested corpus says about pay and skills.

Two questions, straight from PLAN.md Phase 5:

- "What is this role paying right now?" — salary percentiles, overall
  and per location. Computed *in Postgres* with ``percentile_cont``:
  the database already has an ordered-set aggregate for exactly this,
  and shipping every salary row to Python to re-implement percentiles
  would be slower and buggier. Percentiles, not averages, because
  salary data is skewed and gappy — one $900k outlier shouldn't move
  the answer the user acts on.
- "What skills are trending?" — per-week counts of skill mentions.
  Skill extraction stays in Python (the curated matching vocabulary;
  SQL can't reuse it), over a bounded window of recent jobs. At
  personal-corpus scale (thousands of rows) recomputing per request
  costs milliseconds; if the corpus ever outgrows that, the upgrade
  path is materializing extracted skills onto jobs at ingest time —
  noted here so future-you doesn't rediscover it the hard way.

Caveat worth keeping visible: this is *your corpus*, not the market.
Numbers describe what you ingested (sources, boards, filters), and the
API surfaces sample sizes so the UI can say so.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Numeric, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.matching.explain import extract_skills
from jobscout.models import Job
from jobscout.normalize import normalize_title

MAX_SKILL_SAMPLE = 5000
TOP_LOCATIONS = 8
TOP_SKILLS = 15

# Salary midpoint: a single comparable number per job. Jobs listing
# only one end of a range use that end.
_MIDPOINT = func.coalesce((Job.salary_min + Job.salary_max) / 2.0, Job.salary_min, Job.salary_max)


@dataclass
class SalaryStats:
    count: int
    p25: int | None
    median: int | None
    p75: int | None


@dataclass
class LocationSalary:
    location: str
    stats: SalaryStats


@dataclass
class SalaryReport:
    role: str | None
    overall: SalaryStats
    by_location: list[LocationSalary] = field(default_factory=list)


@dataclass
class WeekCount:
    week_start: str  # ISO date of the Monday
    count: int


@dataclass
class SkillTrend:
    skill: str
    total: int
    weekly: list[WeekCount] = field(default_factory=list)


@dataclass
class SkillTrendReport:
    weeks: int
    sampled_jobs: int
    skills: list[SkillTrend] = field(default_factory=list)


def _percentiles() -> tuple[Any, Any, Any, Any]:
    """(count, p25, median, p75) column expressions over salary midpoints.

    Typed as Any: SQLAlchemy's generic-function expressions
    (percentile_cont(...).within_group(...)) don't carry useful static
    types, and pretending otherwise just moves the ignore comment
    around. The boundary back to real types is _stats().
    """
    ordered = _MIDPOINT
    return (
        func.count().filter(ordered.is_not(None)),
        func.percentile_cont(0.25).within_group(cast(ordered, Numeric)),
        func.percentile_cont(0.5).within_group(cast(ordered, Numeric)),
        func.percentile_cont(0.75).within_group(cast(ordered, Numeric)),
    )


def _to_int(value: float | None) -> int | None:
    return int(value) if value is not None else None


def _stats(row: tuple[int, float | None, float | None, float | None]) -> SalaryStats:
    count, p25, median, p75 = row
    return SalaryStats(count=count, p25=_to_int(p25), median=_to_int(median), p75=_to_int(p75))


async def salary_report(
    session: AsyncSession, *, role: str | None = None, location: str | None = None
) -> SalaryReport:
    count_col, p25, median, p75 = _percentiles()
    base = select(count_col, p25, median, p75).where(_MIDPOINT.is_not(None))
    if role:
        base = base.where(Job.title_norm.contains(normalize_title(role)))
    if location:
        base = base.where(Job.location.icontains(location))

    overall_row = (await session.execute(base)).one()
    report = SalaryReport(role=role, overall=_stats(tuple(overall_row)))

    count_col, p25, median, p75 = _percentiles()
    per_location = (
        select(Job.location, count_col, p25, median, p75)
        .where(_MIDPOINT.is_not(None), Job.location.is_not(None))
        .group_by(Job.location)
        .order_by(count_col.desc())
        .limit(TOP_LOCATIONS)
    )
    if role:
        per_location = per_location.where(Job.title_norm.contains(normalize_title(role)))
    for loc, *stats_row in await session.execute(per_location):
        report.by_location.append(LocationSalary(location=loc, stats=_stats(tuple(stats_row))))
    return report


def _monday(dt: datetime) -> datetime:
    day = dt.astimezone(UTC).date()
    monday = day - timedelta(days=day.weekday())
    return datetime(monday.year, monday.month, monday.day, tzinfo=UTC)


async def skill_trends(
    session: AsyncSession, *, weeks: int = 8, role: str | None = None
) -> SkillTrendReport:
    since = _monday(datetime.now(tz=UTC)) - timedelta(weeks=weeks - 1)
    stmt = (
        select(Job.first_seen, Job.description)
        .where(Job.first_seen >= since, Job.description.is_not(None))
        .order_by(Job.first_seen.desc())
        .limit(MAX_SKILL_SAMPLE)
    )
    if role:
        stmt = stmt.where(Job.title_norm.contains(normalize_title(role)))
    rows = (await session.execute(stmt)).all()

    totals: Counter[str] = Counter()
    weekly: dict[str, Counter[str]] = defaultdict(Counter)  # skill -> week -> count
    for first_seen, description in rows:
        week = _monday(first_seen).date().isoformat()
        for skill in extract_skills(description or ""):
            totals[skill] += 1
            weekly[skill][week] += 1

    # Emit a dense weekly series (zeros included) so the frontend can
    # draw aligned sparklines without re-deriving the calendar.
    week_keys = [(since + timedelta(weeks=i)).date().isoformat() for i in range(weeks)]
    report = SkillTrendReport(weeks=weeks, sampled_jobs=len(rows))
    for skill, total in totals.most_common(TOP_SKILLS):
        report.skills.append(
            SkillTrend(
                skill=skill,
                total=total,
                weekly=[WeekCount(week_start=w, count=weekly[skill].get(w, 0)) for w in week_keys],
            )
        )
    return report
