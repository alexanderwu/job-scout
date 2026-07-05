"""Job browse/search and detail endpoints (PLAN.md Phase 3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.api.deps import get_session
from jobscout.api.schemas import JobDetail, JobSummary
from jobscout.models import Job
from jobscout.queries import get_saved_job, search_jobs

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=list[JobSummary])
async def list_jobs(
    location: str | None = None,
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[JobSummary]:
    jobs = await search_jobs(session, location=location, limit=limit, offset=offset)
    return [JobSummary.from_job(job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=JobDetail)
async def get_job(job_id: int, session: AsyncSession = Depends(get_session)) -> JobDetail:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    saved = await get_saved_job(session, job_id)
    return JobDetail.from_job(job, saved_status=saved.status if saved else None)
