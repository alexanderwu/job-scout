"""Market-insights aggregation over the ingested corpus (PLAN.md Phase 5,
stretch): salary/comp by role or location, and in-demand-skill trends
over time. Both answer "what does *my* corpus say right now" from
``queries.jobs_with_salary``/``jobs_first_seen_between``, not an
external salary survey — aggregation itself runs in Python over
already-filtered rows, the same brute-force-is-fine-at-this-scale
approach ``matching.py`` uses for ranking.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from jobscout.matching import aggregate_keyword_frequencies
from jobscout.models import Job


def _salary_bounds(job: Job) -> tuple[int, int] | None:
    """Normalize a job's (possibly one-sided) salary figure to a
    ``(low, high)`` pair, or ``None`` if it has no salary data at all."""
    if job.salary_min is None and job.salary_max is None:
        return None
    low = job.salary_min if job.salary_min is not None else job.salary_max
    high = job.salary_max if job.salary_max is not None else job.salary_min
    assert low is not None
    assert high is not None
    return (low, high)


@dataclass(frozen=True)
class SalaryGroupStat:
    """Aggregate comp across a set of jobs that all reported at least a
    partial salary figure — one group's answer to "what's this paying
    right now"."""

    group: str
    job_count: int
    min_salary: int
    max_salary: int
    avg_salary: float


def _stat_from_bounds(group: str, bounds: list[tuple[int, int]]) -> SalaryGroupStat:
    lows = [b[0] for b in bounds]
    highs = [b[1] for b in bounds]
    midpoints = [(b[0] + b[1]) / 2 for b in bounds]
    return SalaryGroupStat(
        group=group,
        job_count=len(bounds),
        min_salary=min(lows),
        max_salary=max(highs),
        avg_salary=sum(midpoints) / len(midpoints),
    )


def salary_stats_by_group(
    jobs: list[Job], *, group_by: str, limit: int = 10
) -> list[SalaryGroupStat]:
    """Group ``jobs`` (all expected to carry at least a partial salary
    figure, e.g. from ``queries.jobs_with_salary``) by ``normalized_title``
    or ``location``, most-represented group first."""
    grouped: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for job in jobs:
        key = job.normalized_title if group_by == "title" else job.location
        bounds = _salary_bounds(job)
        if key and bounds is not None:
            grouped[key].append(bounds)

    stats = [_stat_from_bounds(group, bounds) for group, bounds in grouped.items()]
    stats.sort(key=lambda s: s.job_count, reverse=True)
    return stats[:limit]


def overall_salary_stats(jobs: list[Job]) -> SalaryGroupStat | None:
    """Aggregate comp across all of ``jobs``, ungrouped. ``None`` if none
    of them actually carry salary data."""
    bounds = [b for b in (_salary_bounds(job) for job in jobs) if b is not None]
    if not bounds:
        return None
    return _stat_from_bounds("overall", bounds)


@dataclass(frozen=True)
class SkillTrendPoint:
    week_start: date
    count: int


@dataclass(frozen=True)
class SkillTrend:
    """One keyword's weekly document-frequency series."""

    keyword: str
    points: list[SkillTrendPoint]


def _as_utc(value: datetime) -> datetime:
    # Postgres/asyncpg always returns tz-aware timestamps for our
    # timestamptz columns, but sqlite (test-only) doesn't reliably
    # round-trip tzinfo across a re-fetch — normalize so a naive
    # ``Job.first_seen`` never crashes the subtraction below.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _week_start(moment: datetime, *, start: datetime) -> date:
    """Bucket ``moment`` into the week-long window starting at ``start``
    that contains it. Floor-divides the full elapsed time between
    ``start`` and ``moment`` (not just their calendar dates), so a job
    first-seen after the last whole day but before ``start``'s exact
    time-of-day still lands in the final in-range bucket instead of
    spilling into a nonexistent one just past the requested range."""
    bucket_index = (_as_utc(moment) - start).days // 7
    return start.date() + timedelta(days=bucket_index * 7)


def skill_trends(
    jobs: list[Job], *, start: datetime, weeks: int, top_n: int = 10
) -> list[SkillTrend]:
    """Weekly document-frequency trend for the ``top_n`` most-mentioned
    keywords across ``jobs`` (already restricted to a date range/role by
    the caller's query), most-mentioned overall first. Reuses
    ``matching.aggregate_keyword_frequencies`` per week instead of
    inventing a separate skills taxonomy — same heuristic Phase 4's
    skill-gap analysis already relies on, just bucketed over time."""
    week_starts = [start.date() + timedelta(days=7 * i) for i in range(weeks)]
    buckets: dict[date, list[Job]] = {week: [] for week in week_starts}
    for job in jobs:
        bucket = _week_start(job.first_seen, start=start)
        if bucket in buckets:
            buckets[bucket].append(job)

    bucket_counts = {
        week: aggregate_keyword_frequencies(bucket_jobs) for week, bucket_jobs in buckets.items()
    }

    total_counts: Counter[str] = Counter()
    for counts in bucket_counts.values():
        total_counts.update(counts)
    top_keywords = [keyword for keyword, _ in total_counts.most_common(top_n)]

    return [
        SkillTrend(
            keyword=keyword,
            points=[
                SkillTrendPoint(week_start=week, count=bucket_counts[week][keyword])
                for week in week_starts
            ],
        )
        for keyword in top_keywords
    ]
