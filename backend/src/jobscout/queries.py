"""Read queries over the normalized schema (Phase 1 milestone: "jobs added
in the last 24h")."""

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
