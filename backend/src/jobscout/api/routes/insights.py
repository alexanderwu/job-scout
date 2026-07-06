"""Market-insight endpoints (Phase 5) — thin serialization over insights.py."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from jobscout.api.deps import SessionDep
from jobscout.insights import salary_report, skill_trends

router = APIRouter(prefix="/insights", tags=["insights"])


class SalaryStatsOut(BaseModel):
    count: int
    p25: int | None
    median: int | None
    p75: int | None


class LocationSalaryOut(BaseModel):
    location: str
    stats: SalaryStatsOut


class SalaryReportOut(BaseModel):
    role: str | None
    overall: SalaryStatsOut
    by_location: list[LocationSalaryOut]


class WeekCountOut(BaseModel):
    week_start: str
    count: int


class SkillTrendOut(BaseModel):
    skill: str
    total: int
    weekly: list[WeekCountOut]


class SkillTrendReportOut(BaseModel):
    weeks: int
    sampled_jobs: int
    skills: list[SkillTrendOut]


@router.get("/salary")
async def salary(
    session: SessionDep,
    role: str | None = Query(None, description="Filter to titles containing this."),
    location: str | None = Query(None, description="Filter to locations containing this."),
) -> SalaryReportOut:
    report = await salary_report(session, role=role, location=location)
    return SalaryReportOut(
        role=report.role,
        overall=SalaryStatsOut(**vars(report.overall)),
        by_location=[
            LocationSalaryOut(location=e.location, stats=SalaryStatsOut(**vars(e.stats)))
            for e in report.by_location
        ],
    )


@router.get("/skills")
async def skills(
    session: SessionDep,
    weeks: int = Query(8, ge=1, le=52),
    role: str | None = Query(None),
) -> SkillTrendReportOut:
    report = await skill_trends(session, weeks=weeks, role=role)
    return SkillTrendReportOut(
        weeks=report.weeks,
        sampled_jobs=report.sampled_jobs,
        skills=[
            SkillTrendOut(
                skill=t.skill,
                total=t.total,
                weekly=[WeekCountOut(**vars(w)) for w in t.weekly],
            )
            for t in report.skills
        ],
    )
