"""Job browsing endpoints: recent list + detail."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from jobscout.api.deps import SessionDep
from jobscout.api.schemas import JobDetail, JobSummary, PostingOut
from jobscout.models import Job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(
    session: SessionDep,
    q: str | None = Query(None, description="Substring match on title/company."),
    hours: int = Query(24 * 7, description="Only jobs seen in the last N hours."),
    limit: int = Query(50, le=200),
    offset: int = 0,
) -> list[JobSummary]:
    """Recent jobs, newest first — the browsing view.

    Plain ILIKE substring search, not full-text: with a personal-scale
    corpus and semantic /match as the primary discovery path, tsvector
    machinery would be complexity without a user. Revisit if browsing
    outgrows it.
    """
    stmt = (
        select(Job)
        .where(Job.last_seen >= datetime.now(tz=UTC) - timedelta(hours=hours))
        .order_by(Job.first_seen.desc())
        .limit(limit)
        .offset(offset)
    )
    if q:
        stmt = stmt.where(Job.title.icontains(q) | Job.company.icontains(q))
    jobs = (await session.scalars(stmt)).all()
    return [JobSummary.model_validate(j) for j in jobs]


@router.get("/{job_id}")
async def get_job(job_id: int, session: SessionDep) -> JobDetail:
    job = await session.get(Job, job_id, options=[selectinload(Job.postings)])
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    detail = JobDetail.model_validate(job)
    detail.postings = [PostingOut.model_validate(p) for p in job.postings]
    return detail
