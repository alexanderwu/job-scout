"""The normalized schema Phase 1 ingestion writes to.

Two tables, not one, because the same real-world opening routinely shows
up through more than one source (PLAN.md's cross-posting problem):

``Job`` is the deduplicated opening — one row per real job, carrying the
fields the rest of the app (search, matching) reads.

``JobPosting`` is one source's sighting of a ``Job`` — kept verbatim
(``raw``) so re-normalization never requires re-fetching, and so
provenance ("this job is cross-posted on hiring.cafe and Greenhouse") is
never lost by collapsing to a single row too early.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from jobscout.embeddings.base import EMBEDDING_DIM


class Base(DeclarativeBase):
    pass


class Job(Base):
    """A deduplicated job opening, merged from one or more source postings."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)

    normalized_title: Mapped[str] = mapped_column(index=True)
    normalized_company: Mapped[str | None] = mapped_column(index=True)
    canonical_url: Mapped[str | None] = mapped_column(unique=True, index=True)
    """Dedupe tier 1 key. Nullable in the schema only because URLs are
    optional in general; ``RawPosting.url`` is required, so in practice
    every ingested job has one."""

    title: Mapped[str]
    company: Mapped[str | None]
    location: Mapped[str | None]
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    description: Mapped[str | None] = mapped_column(Text)
    """Full posting text, kept for embedding (Phase 2) and display. Comes
    straight from the source's own description field, no reformatting."""

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    """Semantic embedding of ``description`` (Phase 2 matching), produced
    by whichever ``EmbeddingProvider`` last embedded this job. Null until
    an embedding batch job runs, since Phase 1 ingestion doesn't embed."""

    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    postings: Mapped[list[JobPosting]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobPosting(Base):
    """One source's raw sighting of a ``Job``."""

    __tablename__ = "job_postings"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_job_postings_source_external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))

    source: Mapped[str] = mapped_column(index=True)
    external_id: Mapped[str]
    url: Mapped[str]
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict[str, Any]] = mapped_column(JSON)

    job: Mapped[Job] = relationship(back_populates="postings")


class Profile(Base):
    """The user's resume, persisted once so the web app (Phase 3) can rank
    and poll for matches without re-uploading on every request.

    Singleton table: this is a personal, single-user tool (PLAN.md never
    introduces accounts), so there's exactly one row rather than a
    ``user_id`` foreign key. ``queries.get_profile``/``upsert_profile``
    enforce the "one row" convention.
    """

    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    resume_text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SavedJob(Base):
    """Application-tracking status for a job the user has saved (Phase 3
    "save/apply tracking"). One row per tracked job; untracked jobs simply
    have no row here."""

    __tablename__ = "saved_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)

    status: Mapped[str]
    """One of ``SAVED_JOB_STATUSES`` below. Plain string column (like
    ``JobPosting.source``) — validated at the API boundary, not the DB."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    job: Mapped[Job] = relationship()


SAVED_JOB_STATUSES = ("saved", "applied", "interviewing", "rejected", "offer")
