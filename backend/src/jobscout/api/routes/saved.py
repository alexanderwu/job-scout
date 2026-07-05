"""Save/apply-tracking endpoints (PLAN.md Phase 3): save a job, move it
through a status pipeline, or drop tracking entirely."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.api.deps import get_session
from jobscout.api.schemas import SavedJobOut, SavedJobTrackingIn, SaveJobStatusIn
from jobscout.models import Job
from jobscout.queries import (
    delete_saved_job,
    list_due_reminders,
    list_saved_jobs,
    upsert_saved_job_status,
    upsert_saved_job_tracking,
)

router = APIRouter(tags=["saved"])


@router.get("/saved", response_model=list[SavedJobOut])
async def get_saved(session: AsyncSession = Depends(get_session)) -> list[SavedJobOut]:
    saved = await list_saved_jobs(session)
    return [SavedJobOut.from_saved_job(s) for s in saved]


async def _set_status(session: AsyncSession, job_id: int, status: str) -> SavedJobOut:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    saved = await upsert_saved_job_status(session, job_id, status, datetime.now(UTC))
    await session.commit()
    saved.job = job
    return SavedJobOut.from_saved_job(saved)


@router.post("/jobs/{job_id}/save", response_model=SavedJobOut)
async def save_job(
    job_id: int,
    body: SaveJobStatusIn | None = None,
    session: AsyncSession = Depends(get_session),
) -> SavedJobOut:
    status = body.status if body is not None else "saved"
    return await _set_status(session, job_id, status)


@router.patch("/jobs/{job_id}/save", response_model=SavedJobOut)
async def update_saved_job_status(
    job_id: int, body: SaveJobStatusIn, session: AsyncSession = Depends(get_session)
) -> SavedJobOut:
    return await _set_status(session, job_id, body.status)


@router.delete("/jobs/{job_id}/save", status_code=204)
async def unsave_job(job_id: int, session: AsyncSession = Depends(get_session)) -> None:
    deleted = await delete_saved_job(session, job_id)
    await session.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="Job is not saved")


@router.patch("/jobs/{job_id}/tracking", response_model=SavedJobOut)
async def update_tracking(
    job_id: int,
    body: SavedJobTrackingIn,
    session: AsyncSession = Depends(get_session),
) -> SavedJobOut:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    saved = await upsert_saved_job_tracking(
        session, job_id, reminder_at=body.reminder_at, notes=body.notes
    )
    if saved is None:
        raise HTTPException(status_code=404, detail="Job is not saved")
    await session.commit()
    saved.job = job
    return SavedJobOut.from_saved_job(saved)


@router.get("/reminders", response_model=list[SavedJobOut])
async def get_reminders(
    within_hours: float = 72,
    session: AsyncSession = Depends(get_session),
) -> list[SavedJobOut]:
    before = datetime.now(UTC) + timedelta(hours=within_hours)
    due = await list_due_reminders(session, before=before)
    return [SavedJobOut.from_saved_job(s) for s in due]
