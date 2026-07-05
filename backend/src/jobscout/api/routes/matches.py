"""Ranked matches against the persisted profile (PLAN.md Phase 3), the
same ``rank_jobs`` logic ``jobscout match`` uses on the CLI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.api.deps import get_session
from jobscout.api.schemas import JobSummary, MatchResultOut
from jobscout.matching import extract_keywords, rank_jobs
from jobscout.queries import get_profile, jobs_with_embeddings

router = APIRouter(tags=["matches"])


@router.get("/matches", response_model=list[MatchResultOut])
async def list_matches(
    location: str | None = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
) -> list[MatchResultOut]:
    profile = await get_profile(session)
    if profile is None:
        raise HTTPException(status_code=404, detail="No profile uploaded yet")

    resume_keywords = extract_keywords(profile.resume_text)
    candidates = await jobs_with_embeddings(session, location=location)
    results = rank_jobs(list(candidates), list(profile.embedding), resume_keywords, limit=limit)
    return [
        MatchResultOut(
            job=JobSummary.from_job(r.job), score=r.score, matched_keywords=r.matched_keywords
        )
        for r in results
    ]
