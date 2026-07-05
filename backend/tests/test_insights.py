"""Salary and skill-trend aggregation tests (PLAN.md Phase 5, stretch)."""

from __future__ import annotations

from datetime import UTC, datetime

from jobscout.insights import overall_salary_stats, salary_stats_by_group, skill_trends
from jobscout.models import Job


def make_job(**overrides: object) -> Job:
    defaults: dict[str, object] = {
        "normalized_title": "data engineer",
        "canonical_url": "https://example.com/1",
        "title": "Data Engineer",
        "company": None,
        "location": None,
        "description": None,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "first_seen": datetime(2026, 1, 1, tzinfo=UTC),
        "last_seen": datetime(2026, 1, 1, tzinfo=UTC),
    }
    return Job(**{**defaults, **overrides})


def test_salary_stats_by_group_computes_bounds_and_average() -> None:
    jobs = [
        make_job(
            normalized_title="data engineer",
            canonical_url="https://example.com/1",
            salary_min=100_000,
            salary_max=140_000,
        ),
        make_job(
            normalized_title="data engineer",
            canonical_url="https://example.com/2",
            salary_min=120_000,
            salary_max=160_000,
        ),
        make_job(
            normalized_title="product manager",
            canonical_url="https://example.com/3",
            salary_min=150_000,
            salary_max=150_000,
        ),
    ]

    groups = salary_stats_by_group(jobs, group_by="title")

    assert [g.group for g in groups] == ["data engineer", "product manager"]
    data_eng = groups[0]
    assert data_eng.job_count == 2
    assert data_eng.min_salary == 100_000
    assert data_eng.max_salary == 160_000
    assert data_eng.avg_salary == (120_000 + 140_000) / 2


def test_salary_stats_by_group_treats_one_sided_ranges_as_a_single_point() -> None:
    jobs = [
        make_job(canonical_url="https://example.com/1", salary_min=200_000, salary_max=None),
    ]

    groups = salary_stats_by_group(jobs, group_by="title")

    assert groups[0].min_salary == 200_000
    assert groups[0].max_salary == 200_000
    assert groups[0].avg_salary == 200_000


def test_salary_stats_by_group_excludes_jobs_without_salary_data() -> None:
    jobs = [
        make_job(canonical_url="https://example.com/1", salary_min=None, salary_max=None),
    ]

    assert salary_stats_by_group(jobs, group_by="title") == []


def test_salary_stats_by_group_limits_and_orders_by_job_count() -> None:
    jobs = [
        make_job(
            normalized_title="a",
            canonical_url="https://example.com/1",
            salary_min=100_000,
            salary_max=100_000,
        ),
        make_job(
            normalized_title="b",
            canonical_url="https://example.com/2",
            salary_min=100_000,
            salary_max=100_000,
        ),
        make_job(
            normalized_title="b",
            canonical_url="https://example.com/3",
            salary_min=100_000,
            salary_max=100_000,
        ),
    ]

    groups = salary_stats_by_group(jobs, group_by="title", limit=1)

    assert [g.group for g in groups] == ["b"]


def test_salary_stats_by_group_can_group_by_location() -> None:
    jobs = [
        make_job(
            canonical_url="https://example.com/1",
            location="Remote",
            salary_min=100_000,
            salary_max=120_000,
        ),
    ]

    groups = salary_stats_by_group(jobs, group_by="location")

    assert groups[0].group == "Remote"


def test_overall_salary_stats_aggregates_across_groups() -> None:
    jobs = [
        make_job(canonical_url="https://example.com/1", salary_min=100_000, salary_max=100_000),
        make_job(canonical_url="https://example.com/2", salary_min=200_000, salary_max=200_000),
    ]

    overall = overall_salary_stats(jobs)

    assert overall is not None
    assert overall.job_count == 2
    assert overall.min_salary == 100_000
    assert overall.max_salary == 200_000
    assert overall.avg_salary == 150_000


def test_overall_salary_stats_is_none_without_any_salary_data() -> None:
    jobs = [make_job(canonical_url="https://example.com/1")]
    assert overall_salary_stats(jobs) is None


def test_skill_trends_buckets_by_week_and_ranks_by_total_frequency() -> None:
    start = datetime(2026, 1, 5, tzinfo=UTC)  # a Monday
    week1_job = make_job(
        title="Q",
        canonical_url="https://example.com/1",
        description="Python and SQL experience needed.",
        first_seen=start,
    )
    week2_job_a = make_job(
        title="Q",
        canonical_url="https://example.com/2",
        description="Python and Rust in demand this quarter.",
        first_seen=start.replace(day=12),
    )
    week2_job_b = make_job(
        title="Q",
        canonical_url="https://example.com/3",
        description="Python and Rust remain popular choices.",
        first_seen=start.replace(day=13),
    )

    trends = skill_trends([week1_job, week2_job_a, week2_job_b], start=start, weeks=2, top_n=5)

    by_keyword = {trend.keyword: trend for trend in trends}
    assert "python" in by_keyword
    assert [p.count for p in by_keyword["python"].points] == [1, 2]
    assert [p.count for p in by_keyword["rust"].points] == [0, 2]
    # most-mentioned overall (python, in all 3 postings) ranks first
    assert trends[0].keyword == "python"


def test_skill_trends_ignores_jobs_outside_the_window() -> None:
    start = datetime(2026, 1, 5, tzinfo=UTC)
    outside = make_job(
        canonical_url="https://example.com/1",
        description="Python engineer.",
        first_seen=datetime(2025, 1, 1, tzinfo=UTC),
    )

    trends = skill_trends([outside], start=start, weeks=2, top_n=5)

    assert trends == []
