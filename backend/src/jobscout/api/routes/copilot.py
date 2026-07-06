"""Copilot endpoints: skill gap, tailoring, cover letters, reminders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from jobscout.api.deps import LLMDep, SessionDep
from jobscout.api.schemas import ApplicationOut
from jobscout.copilot.cover_letter import draft_cover_letter
from jobscout.copilot.skill_gap import skill_gap
from jobscout.copilot.tailor import tailor
from jobscout.llm import LLMError
from jobscout.matching.explain import extract_skills
from jobscout.models import Application, Job, Profile

router = APIRouter(tags=["copilot"])

TERMINAL_STATUSES = ("offer", "rejected")


class SkillDemandOut(BaseModel):
    skill: str
    count: int
    share: float


class SkillGapOut(BaseModel):
    role: str
    sampled_jobs: int
    have: list[SkillDemandOut]
    missing: list[SkillDemandOut]


class TailorOut(BaseModel):
    job_id: int
    suggestions: list[str]
    emphasized_skills: list[str]
    gap_skills: list[str]
    prose: str | None


class CoverLetterOut(BaseModel):
    job_id: int
    body: str
    generated_by: str


@router.get("/profiles/{profile_id}/skill-gap")
async def profile_skill_gap(
    profile_id: int,
    session: SessionDep,
    role: str = Query(..., min_length=2, description="Target role, e.g. 'data engineer'"),
) -> SkillGapOut:
    profile = await _profile(session, profile_id)
    report = await skill_gap(session, role, extract_skills(profile.resume_text))
    return SkillGapOut(
        role=report.role,
        sampled_jobs=report.sampled_jobs,
        have=[SkillDemandOut(**vars(d)) for d in report.have],
        missing=[SkillDemandOut(**vars(d)) for d in report.missing],
    )


@router.post("/jobs/{job_id}/tailor")
async def tailor_resume(
    job_id: int, profile_id: int, session: SessionDep, llm: LLMDep
) -> TailorOut:
    job, profile = await _job_and_profile(session, job_id, profile_id)
    try:
        advice = await tailor(job, profile.resume_text, llm)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TailorOut(
        job_id=advice.job_id,
        suggestions=advice.suggestions,
        emphasized_skills=advice.emphasized_skills,
        gap_skills=advice.gap_skills,
        prose=advice.prose,
    )


@router.post("/jobs/{job_id}/cover-letter")
async def cover_letter(
    job_id: int, profile_id: int, session: SessionDep, llm: LLMDep
) -> CoverLetterOut:
    job, profile = await _job_and_profile(session, job_id, profile_id)
    try:
        letter = await draft_cover_letter(job, profile.resume_text, llm)
    except LLMError as exc:
        # 502: the upstream generator failed, the request was fine. The
        # detail string tells the user exactly what to fix (start
        # Ollama / set a key / switch provider).
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return CoverLetterOut(job_id=letter.job_id, body=letter.body, generated_by=letter.generated_by)


@router.get("/applications/reminders")
async def reminders(
    session: SessionDep,
    days: int = Query(7, ge=1, description="Flag applications idle this many days."),
) -> list[ApplicationOut]:
    """Applications that need a nudge: active status, no update in N days.

    Derived on read, not scheduled: a personal tool's reminders only
    matter when you're looking — a cron job writing 'reminder rows'
    would just duplicate this query's answer into state that can drift.
    """
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    stale = await session.scalars(
        select(Application)
        .options(selectinload(Application.job), selectinload(Application.events))
        .where(Application.status.not_in(TERMINAL_STATUSES), Application.updated_at < cutoff)
        .order_by(Application.updated_at)
    )
    return [ApplicationOut.model_validate(a) for a in stale]


async def _profile(session: SessionDep, profile_id: int) -> Profile:
    profile = await session.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    return profile


async def _job_and_profile(
    session: SessionDep, job_id: int, profile_id: int
) -> tuple[Job, Profile]:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job, await _profile(session, profile_id)
