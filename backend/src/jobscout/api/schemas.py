"""API request/response models (pydantic).

Separate from the ORM models on purpose — the classic "API schema is
not the DB schema" boundary:

- responses expose exactly what the UI needs (e.g. a job's best apply
  URL, computed from its postings) and hide internals (raw payloads,
  norm columns, vectors — an embedding in a JSON response would be 384
  floats of noise on every row);
- ORM objects change shape with migrations; these change shape with
  the frontend. Coupling them means every schema migration is an
  accidental API break.

``model_config = ConfigDict(from_attributes=True)`` lets each schema
be built straight from an ORM instance where fields do line up.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PostingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    url: str
    posted_at: datetime | None
    first_seen: datetime
    last_seen: datetime


class JobSummary(BaseModel):
    """Compact job card for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    company: str | None
    location: str | None
    remote: bool | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    first_seen: datetime
    last_seen: datetime


class JobDetail(JobSummary):
    description: str | None
    postings: list[PostingOut]


class ExplanationOut(BaseModel):
    overlapping: list[str]
    missing: list[str]
    summary: str


class MatchOut(BaseModel):
    job: JobSummary
    score: float
    apply_url: str | None
    explanation: ExplanationOut


class MatchResponse(BaseModel):
    resume_skills: list[str]
    matches: list[MatchOut]


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    updated_at: datetime
    skills: list[str] = Field(default_factory=list)


class FeedResponse(BaseModel):
    """New jobs (first_seen after `since`) ranked against a profile."""

    since: datetime
    matches: list[MatchOut]


class ApplicationCreate(BaseModel):
    job_id: int
    profile_id: int | None = None
    status: str = "saved"


class ApplicationUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None


class ApplicationEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    at: datetime


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job: JobSummary
    profile_id: int | None
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime
    events: list[ApplicationEventOut]
