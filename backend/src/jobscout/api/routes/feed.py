"""The polling half of PLAN.md Phase 3's "WebSocket or polling feed for
'new jobs matching your profile'": jobs first seen since the caller's
last check, ranked against the profile if one exists.

Polling over a websocket because there's no push source to wake a socket
for yet — ingestion is still CLI-triggered (``jobscout ingest``), not a
running scheduler — so a push channel would have nothing to push
proactively. The frontend just re-polls this on an interval.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.api.deps import get_session
from jobscout.api.schemas import FeedItemOut, FeedOut, JobSummary
from jobscout.matching import extract_keywords, rank_jobs
from jobscout.queries import get_profile, jobs_first_seen_since

router = APIRouter(tags=["feed"])


@router.get("/feed", response_model=FeedOut)
async def get_feed(
    since: datetime = Query(...),
    location: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> FeedOut:
    checked_at = datetime.now(UTC)
    jobs = list(await jobs_first_seen_since(session, since))
    if location is not None:
        needle = location.lower()
        jobs = [job for job in jobs if job.location and needle in job.location.lower()]

    profile = await get_profile(session)
    embedded_jobs = [job for job in jobs if job.embedding is not None]
    unembedded_jobs = [job for job in jobs if job.embedding is None]

    ranked_items: list[FeedItemOut] = []
    if profile is not None and embedded_jobs:
        resume_keywords = extract_keywords(profile.resume_text)
        ranked = rank_jobs(
            embedded_jobs, list(profile.embedding), resume_keywords, limit=len(embedded_jobs)
        )
        ranked_items = [
            FeedItemOut(
                job=JobSummary.from_job(r.job), score=r.score, matched_keywords=r.matched_keywords
            )
            for r in ranked
        ]
    else:
        # No profile to rank against yet — surface embedded jobs unscored
        # rather than hiding them.
        ranked_items = [
            FeedItemOut(job=JobSummary.from_job(job), score=None, matched_keywords=[])
            for job in embedded_jobs
        ]

    # Jobs without an embedding yet (embedding is a separate batch step)
    # always trail, unscored, rather than disappearing from the feed.
    unembedded_items = [
        FeedItemOut(job=JobSummary.from_job(job), score=None, matched_keywords=[])
        for job in unembedded_jobs
    ]
    return FeedOut(checked_at=checked_at, jobs=ranked_items + unembedded_items)
