"""Market insights over the ingested corpus (PLAN.md Phase 5, stretch):
comp by role/location and in-demand-skill trends, both computed from
your own data rather than an external salary survey."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.api.deps import get_session
from jobscout.api.schemas import SalaryInsightsOut, SkillTrendsOut
from jobscout.insights import overall_salary_stats, salary_stats_by_group, skill_trends
from jobscout.queries import jobs_first_seen_between, jobs_with_salary

router = APIRouter(tags=["insights"])


@router.get("/insights/salary", response_model=SalaryInsightsOut)
async def get_salary_insights(
    group_by: Literal["title", "location"] = "title",
    role: str | None = None,
    location: str | None = None,
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
) -> SalaryInsightsOut:
    jobs = list(await jobs_with_salary(session, role=role, location=location))
    groups = salary_stats_by_group(jobs, group_by=group_by, limit=limit)
    overall = overall_salary_stats(jobs)
    return SalaryInsightsOut.from_result(group_by=group_by, groups=groups, overall=overall)


@router.get("/insights/skills", response_model=SkillTrendsOut)
async def get_skill_trends(
    role: str | None = None,
    weeks: int = 12,
    top: int = 10,
    session: AsyncSession = Depends(get_session),
) -> SkillTrendsOut:
    end = datetime.now(tz=UTC)
    start = end - timedelta(weeks=weeks)
    jobs = list(await jobs_first_seen_between(session, start, end, role=role))
    trends = skill_trends(jobs, start=start, weeks=weeks, top_n=top)
    return SkillTrendsOut.from_result(weeks=weeks, trends=trends)
