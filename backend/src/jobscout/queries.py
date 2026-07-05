"""Read queries over the normalized schema (Phase 1 milestone: "jobs added
in the last 24h"; Phase 2 adds the embedding-pipeline and matching queries).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.models import Job


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
