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

from jobscout.models import Job, SavedJob

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

    @classmethod
    def from_saved_job(cls, saved: SavedJob) -> SavedJobOut:
        return cls(
            job=JobSummary.from_job(saved.job),
            status=saved.status,  # type: ignore[arg-type]
            created_at=saved.created_at,
            updated_at=saved.updated_at,
        )


class SaveJobStatusIn(BaseModel):
    status: SavedJobStatus
