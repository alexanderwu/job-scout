"""Pydantic request/response models for the Phase 3 API.

Kept separate from ``jobscout.models`` (the SQLAlchemy schema) on purpose:
these shape what crosses the wire to the frontend, not what's stored, and
the two diverge immediately (e.g. ``JobDetail.saved_status`` is joined in
from a different table, ``ProfileOut`` never exposes the embedding).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from jobscout.matching import SkillGapResult, TailoringSuggestions
from jobscout.models import CoverLetter, Job, SavedJob

SavedJobStatus = Literal["saved", "applied", "interviewing", "rejected", "offer"]


class JobSummary(BaseModel):
    id: int
    title: str
    company: str | None
    location: str | None
    posted_at: datetime | None
    first_seen: datetime
    canonical_url: str | None

    @classmethod
    def from_job(cls, job: Job) -> JobSummary:
        return cls(
            id=job.id,
            title=job.title,
            company=job.company,
            location=job.location,
            posted_at=job.posted_at,
            first_seen=job.first_seen,
            canonical_url=job.canonical_url,
        )


class JobDetail(JobSummary):
    description: str | None
    saved_status: SavedJobStatus | None

    @classmethod
    def from_job(cls, job: Job, *, saved_status: str | None = None) -> JobDetail:
        return cls(
            id=job.id,
            title=job.title,
            company=job.company,
            location=job.location,
            posted_at=job.posted_at,
            first_seen=job.first_seen,
            canonical_url=job.canonical_url,
            description=job.description,
            saved_status=saved_status,  # type: ignore[arg-type]
        )


class MatchResultOut(BaseModel):
    job: JobSummary
    score: float
    matched_keywords: list[str]


class FeedItemOut(BaseModel):
    job: JobSummary
    score: float | None
    matched_keywords: list[str]


class FeedOut(BaseModel):
    checked_at: datetime
    jobs: list[FeedItemOut]


class ProfileOut(BaseModel):
    has_profile: bool
    updated_at: datetime | None
    resume_preview: str | None


class SavedJobOut(BaseModel):
    job: JobSummary
    status: SavedJobStatus
    created_at: datetime
    updated_at: datetime
    applied_at: datetime | None
    interviewing_at: datetime | None
    rejected_at: datetime | None
    offer_at: datetime | None
    reminder_at: datetime | None
    notes: str | None

    @classmethod
    def from_saved_job(cls, saved: SavedJob) -> SavedJobOut:
        return cls(
            job=JobSummary.from_job(saved.job),
            status=saved.status,  # type: ignore[arg-type]
            created_at=saved.created_at,
            updated_at=saved.updated_at,
            applied_at=saved.applied_at,
            interviewing_at=saved.interviewing_at,
            rejected_at=saved.rejected_at,
            offer_at=saved.offer_at,
            reminder_at=saved.reminder_at,
            notes=saved.notes,
        )


class SaveJobStatusIn(BaseModel):
    status: SavedJobStatus


class SavedJobTrackingIn(BaseModel):
    reminder_at: datetime | None = None
    notes: str | None = None


class KeywordFrequency(BaseModel):
    keyword: str
    count: int


class SkillGapOut(BaseModel):
    role: str
    postings_considered: int
    missing_keywords: list[KeywordFrequency]
    matched_keywords: list[KeywordFrequency]

    @classmethod
    def from_result(cls, role: str, result: SkillGapResult) -> SkillGapOut:
        return cls(
            role=role,
            postings_considered=result.postings_considered,
            missing_keywords=[
                KeywordFrequency(keyword=k, count=c) for k, c in result.missing_keywords
            ],
            matched_keywords=[
                KeywordFrequency(keyword=k, count=c) for k, c in result.matched_keywords
            ],
        )


class TailoringOut(BaseModel):
    job_id: int
    matched_keywords: list[str]
    missing_keywords: list[str]

    @classmethod
    def from_result(cls, job_id: int, result: TailoringSuggestions) -> TailoringOut:
        return cls(
            job_id=job_id,
            matched_keywords=result.matched_keywords,
            missing_keywords=result.missing_keywords,
        )


class CoverLetterOut(BaseModel):
    job_id: int
    content: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, cover: CoverLetter) -> CoverLetterOut:
        return cls(
            job_id=cover.job_id,
            content=cover.content,
            created_at=cover.created_at,
            updated_at=cover.updated_at,
        )
