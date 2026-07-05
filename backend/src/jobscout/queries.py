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

from jobscout.models import STATUS_TIMESTAMP_COLUMNS, CoverLetter, Job, Profile, SavedJob


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


async def jobs_matching_role(
    session: AsyncSession, role: str, *, limit: int = 200
) -> Sequence[Job]:
    """Postings for a free-text target-role search — the corpus a Phase 4
    skill-gap analysis aggregates over. Matched by substring against
    ``Job.title`` (same ``ilike`` approach ``search_jobs``' location filter
    uses; there's no roles taxonomy to match against instead), restricted
    to postings with description text to extract keywords from."""
    result = await session.scalars(
        select(Job)
        .where(Job.title.ilike(f"%{role}%"), Job.description.is_not(None))
        .order_by(Job.first_seen.desc())
        .limit(limit)
    )
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
    changes (e.g. saved -> applied). Also stamps the matching
    ``STATUS_TIMESTAMP_COLUMNS`` timestamp so the UI can render a
    timeline of transitions, not just the current status."""
    saved = await get_saved_job(session, job_id)
    if saved is None:
        saved = SavedJob(job_id=job_id, status=status, created_at=now, updated_at=now)
        session.add(saved)
    else:
        saved.status = status
        saved.updated_at = now
    timestamp_column = STATUS_TIMESTAMP_COLUMNS.get(status)
    if timestamp_column is not None:
        setattr(saved, timestamp_column, now)
    await session.flush()
    return saved


async def upsert_saved_job_tracking(
    session: AsyncSession,
    job_id: int,
    *,
    reminder_at: datetime | None,
    notes: str | None,
) -> SavedJob | None:
    """Replace the reminder/notes fields on an already-tracked job.
    Returns ``None`` if ``job_id`` isn't tracked yet (caller 404s)."""
    saved = await get_saved_job(session, job_id)
    if saved is None:
        return None
    saved.reminder_at = reminder_at
    saved.notes = notes
    await session.flush()
    return saved


async def list_due_reminders(session: AsyncSession, *, before: datetime) -> Sequence[SavedJob]:
    """Tracked jobs with a reminder set at or before ``before``, soonest
    first — the "upcoming/due reminders" list Phase 4 surfaces."""
    result = await session.scalars(
        select(SavedJob)
        .options(selectinload(SavedJob.job))
        .where(SavedJob.reminder_at.is_not(None), SavedJob.reminder_at <= before)
        .order_by(SavedJob.reminder_at.asc())
    )
    return result.all()


async def delete_saved_job(session: AsyncSession, job_id: int) -> bool:
    """Stop tracking ``job_id``. Returns whether a row was actually deleted."""
    saved = await get_saved_job(session, job_id)
    if saved is None:
        return False
    await session.delete(saved)
    await session.flush()
    return True


async def get_cover_letter(session: AsyncSession, job_id: int) -> CoverLetter | None:
    cover: CoverLetter | None = await session.scalar(
        select(CoverLetter).where(CoverLetter.job_id == job_id)
    )
    return cover


async def upsert_cover_letter(
    session: AsyncSession, *, job_id: int, content: str, now: datetime
) -> CoverLetter:
    """Persist a job's cover-letter draft, creating it on first
    generation and overwriting ``content`` in place on regenerate
    (``created_at`` stays fixed, ``updated_at`` advances) — the same
    upsert shape as ``upsert_profile``."""
    cover = await get_cover_letter(session, job_id)
    if cover is None:
        cover = CoverLetter(job_id=job_id, content=content, created_at=now, updated_at=now)
        session.add(cover)
    else:
        cover.content = content
        cover.updated_at = now
    await session.flush()
    return cover
