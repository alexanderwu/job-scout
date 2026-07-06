"""Application tracker endpoints (saved -> applied -> ... pipeline).

Every status change appends an ApplicationEvent — the tracker's
history is derived data the UI (and Phase 4 reminders) read, never
something the client is trusted to maintain.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from jobscout.api.deps import SessionDep
from jobscout.api.schemas import ApplicationCreate, ApplicationOut, ApplicationUpdate
from jobscout.models import APPLICATION_STATUSES, Application, ApplicationEvent, Job

router = APIRouter(prefix="/applications", tags=["applications"])

_LOAD = [selectinload(Application.job), selectinload(Application.events)]


@router.post("", status_code=201)
async def create_application(body: ApplicationCreate, session: SessionDep) -> ApplicationOut:
    _validate_status(body.status)
    if await session.get(Job, body.job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    existing = await session.scalar(
        select(Application).where(
            Application.job_id == body.job_id, Application.profile_id == body.profile_id
        )
    )
    if existing is not None:
        # Saving twice from the UI shouldn't 500 on the unique
        # constraint; return the existing row (idempotent create).
        return await _out(session, existing.id)

    now = datetime.now(tz=UTC)
    application = Application(
        job_id=body.job_id,
        profile_id=body.profile_id,
        status=body.status,
        created_at=now,
        updated_at=now,
    )
    session.add(application)
    await session.flush()
    session.add(ApplicationEvent(application_id=application.id, status=body.status, at=now))
    await session.flush()
    return await _out(session, application.id)


@router.get("")
async def list_applications(
    session: SessionDep,
    status: str | None = None,
    profile_id: int | None = None,
) -> list[ApplicationOut]:
    stmt = select(Application).options(*_LOAD).order_by(Application.updated_at.desc())
    if status is not None:
        _validate_status(status)
        stmt = stmt.where(Application.status == status)
    if profile_id is not None:
        stmt = stmt.where(Application.profile_id == profile_id)
    apps = (await session.scalars(stmt)).all()
    return [ApplicationOut.model_validate(a) for a in apps]


@router.patch("/{application_id}")
async def update_application(
    application_id: int, body: ApplicationUpdate, session: SessionDep
) -> ApplicationOut:
    application = await session.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="application not found")
    now = datetime.now(tz=UTC)
    if body.status is not None and body.status != application.status:
        _validate_status(body.status)
        application.status = body.status
        session.add(ApplicationEvent(application_id=application.id, status=body.status, at=now))
    if body.notes is not None:
        application.notes = body.notes
    application.updated_at = now
    await session.flush()
    return await _out(session, application.id)


@router.delete("/{application_id}", status_code=204)
async def delete_application(application_id: int, session: SessionDep) -> None:
    application = await session.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="application not found")
    await session.delete(application)


def _validate_status(status: str) -> None:
    if status not in APPLICATION_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {', '.join(APPLICATION_STATUSES)}",
        )


async def _out(session: SessionDep, application_id: int) -> ApplicationOut:
    application = await session.scalar(
        select(Application).options(*_LOAD).where(Application.id == application_id)
    )
    assert application is not None
    return ApplicationOut.model_validate(application)
