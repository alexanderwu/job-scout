"""Read queries over the normalized schema (Phase 1 milestone: "jobs added
in the last 24h"; Phase 2 adds the embedding-pipeline and matching queries;
Phase 3 adds the profile and saved-job-tracking queries the API needs).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from jobscout.models import Job, Profile, SavedJob


async def jobs_first_seen_since(session: AsyncSession, since: datetime) -> Sequence[Job]:
    result = await session.scalars(
        select(Job).where(Job.first_seen >= since).order_by(Job.first_seen.desc())
    )
    return result.all()


async def jobs_missing_embeddings(session: AsyncSession, *, limit: int = 100) -> Sequence[Job]:
    """Jobs with a description to embed but no embedding yet — the work
    queue for the Phase 2 embedding batch job."""
    result = await session.scalars(
        select(Job)
        .where(Job.description.is_not(None), Job.embedding.is_(None))
        .order_by(Job.id)
        .limit(limit)
    )
    return result.all()


async def jobs_with_embeddings(
    session: AsyncSession, *, location: str | None = None
) -> Sequence[Job]:
    """Embedded jobs eligible for resume matching, optionally narrowed by
    location. Cosine ranking itself happens in Python (see matching.py)."""
    query = select(Job).where(Job.embedding.is_not(None))
    if location is not None:
        query = query.where(Job.location.ilike(f"%{location}%"))
    result = await session.scalars(query)
    return result.all()


async def search_jobs(
    session: AsyncSession,
    *,
    location: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> Sequence[Job]:
    """Paginated job browse list (Phase 3 ``GET /api/jobs``), most
    recently first-seen first."""
    query = select(Job).order_by(Job.first_seen.desc()).limit(limit).offset(offset)
    if location is not None:
        query = query.where(Job.location.ilike(f"%{location}%"))
    result = await session.scalars(query)
    return result.all()


async def get_profile(session: AsyncSession) -> Profile | None:
    """The single persisted resume/profile, if one has been uploaded yet."""
    profile: Profile | None = await session.scalar(select(Profile).order_by(Profile.id).limit(1))
    return profile


async def upsert_profile(
    session: AsyncSession, *, resume_text: str, embedding: list[float], now: datetime
) -> Profile:
    """Replace the one profile row's resume text/embedding, creating it on
    first upload. Singleton by convention (see ``models.Profile``), not by
    a DB constraint — the API only ever calls this, never raw inserts."""
    profile = await get_profile(session)
    if profile is None:
        profile = Profile(resume_text=resume_text, embedding=embedding, updated_at=now)
        session.add(profile)
    else:
        profile.resume_text = resume_text
        profile.embedding = embedding
        profile.updated_at = now
    await session.flush()
    return profile


async def get_saved_job(session: AsyncSession, job_id: int) -> SavedJob | None:
    saved: SavedJob | None = await session.scalar(select(SavedJob).where(SavedJob.job_id == job_id))
    return saved


async def list_saved_jobs(session: AsyncSession) -> Sequence[SavedJob]:
    result = await session.scalars(
        select(SavedJob).options(selectinload(SavedJob.job)).order_by(SavedJob.updated_at.desc())
    )
    return result.all()


async def upsert_saved_job_status(
    session: AsyncSession, job_id: int, status: str, now: datetime
) -> SavedJob:
    """Track ``job_id`` with ``status``, creating the tracking row on
    first save and just updating status/timestamp on later status
    changes (e.g. saved -> applied)."""
    saved = await get_saved_job(session, job_id)
    if saved is None:
        saved = SavedJob(job_id=job_id, status=status, created_at=now, updated_at=now)
        session.add(saved)
    else:
        saved.status = status
        saved.updated_at = now
    await session.flush()
    return saved


async def delete_saved_job(session: AsyncSession, job_id: int) -> bool:
    """Stop tracking ``job_id``. Returns whether a row was actually deleted."""
    saved = await get_saved_job(session, job_id)
    if saved is None:
        return False
    await session.delete(saved)
    await session.flush()
    return True
