"""Auto-drafted cover letters (PLAN.md Phase 4): one persisted,
regenerable draft per job, generated from the profile's resume text and
the job's title/company/description via an ``LLMProvider``."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.api.deps import get_llm_provider, get_session
from jobscout.api.schemas import CoverLetterOut
from jobscout.cover_letters import build_cover_letter_prompt
from jobscout.llm.base import LLMProvider
from jobscout.models import Job
from jobscout.queries import get_cover_letter, get_profile, upsert_cover_letter

router = APIRouter(tags=["cover-letters"])


@router.get("/jobs/{job_id}/cover-letter", response_model=CoverLetterOut)
async def read_cover_letter(
    job_id: int, session: AsyncSession = Depends(get_session)
) -> CoverLetterOut:
    cover = await get_cover_letter(session, job_id)
    if cover is None:
        raise HTTPException(status_code=404, detail="No cover letter drafted yet")
    return CoverLetterOut.from_model(cover)


@router.post("/jobs/{job_id}/cover-letter", response_model=CoverLetterOut)
async def generate_cover_letter(
    job_id: int,
    session: AsyncSession = Depends(get_session),
    llm: LLMProvider = Depends(get_llm_provider),
) -> CoverLetterOut:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    profile = await get_profile(session)
    if profile is None:
        raise HTTPException(status_code=404, detail="No profile uploaded yet")

    prompt = build_cover_letter_prompt(
        resume_text=profile.resume_text,
        job_title=job.title,
        company=job.company,
        job_description=job.description,
    )
    content = await llm.generate(prompt)
    cover = await upsert_cover_letter(
        session, job_id=job_id, content=content, now=datetime.now(UTC)
    )
    await session.commit()
    return CoverLetterOut.from_model(cover)
