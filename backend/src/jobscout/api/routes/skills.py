"""Deterministic, keyword-diff-based career-copilot analysis (PLAN.md
Phase 4): skill-gap analysis against a target role's aggregate postings,
and per-job resume tailoring suggestions. No LLM involved — same
explainable keyword-overlap heuristic ``matching.rank_jobs`` already
uses for match explanations."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.api.deps import get_job_or_404, get_profile_or_404, get_session
from jobscout.api.schemas import SkillGapOut, TailoringOut
from jobscout.matching import extract_keywords, skill_gap, tailoring_suggestions
from jobscout.models import Job, Profile
from jobscout.queries import jobs_matching_role

router = APIRouter(tags=["skills"])


@router.get("/skill-gap", response_model=SkillGapOut)
async def get_skill_gap(
    role: str,
    limit: int = 200,
    top: int = 20,
    session: AsyncSession = Depends(get_session),
    profile: Profile = Depends(get_profile_or_404),
) -> SkillGapOut:
    resume_keywords = extract_keywords(profile.resume_text)
    jobs = await jobs_matching_role(session, role, limit=limit)
    result = skill_gap(resume_keywords, list(jobs), top_n=top)
    return SkillGapOut.from_result(role, result)


@router.get("/jobs/{job_id}/tailoring", response_model=TailoringOut)
async def get_tailoring(
    job_id: int,
    profile: Profile = Depends(get_profile_or_404),
    job: Job = Depends(get_job_or_404),
) -> TailoringOut:
    resume_keywords = extract_keywords(profile.resume_text)
    result = tailoring_suggestions(resume_keywords, job)
    return TailoringOut.from_result(job_id, result)
