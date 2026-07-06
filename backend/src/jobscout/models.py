"""ORM models: the two-table core of the ingestion pipeline.

Design notes
------------
**Why two tables.** A *posting* is what one source said (one row per
``(source, external_id)``, raw payload included); a *job* is the
deduplicated real-world opening that one or more postings describe.
Cross-posted roles — same job on Greenhouse and hiring.cafe — become one
``Job`` with two ``Posting`` rows, so "how did we know these were the
same?" stays inspectable instead of one row silently overwriting the
other. The rejected alternative, a single table with a
``duplicate_of_id`` self-reference, saves a join but makes the canonical
job a soft convention: every downstream query would need
``WHERE duplicate_of_id IS NULL`` and merges would be destructive.

**Why ``*_norm`` columns are stored, not computed on the fly.**
Tier-2 dedupe looks up "does a job with this normalized title+company
exist?" on every incoming posting. Storing the normalized forms (and
indexing them) makes that an index lookup; normalizing at query time
would force a sequential scan or a functional index tied to a SQL
reimplementation of the Python normalizer — two normalizers to keep in
sync.

**Timestamps** are ``timestamptz`` (``DateTime(timezone=True)``) and
always UTC. ``first_seen``/``last_seen`` drive freshness ("added in the
last 24h") and staleness (a job whose postings all stopped appearing is
presumed filled/closed) without needing a mutable ``is_active`` flag —
activity is *derived* from evidence, never asserted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base all models inherit; Alembic reads its metadata."""


class Job(Base):
    """A deduplicated job opening — the entity everything downstream uses."""

    __tablename__ = "jobs"
    __table_args__ = (
        # The tier-2 dedupe lookup key. Location is part of it: see
        # ingest/dedupe.py for why we'd rather miss a merge than merge
        # two different-city roles into one.
        Index("ix_jobs_dedupe_key", "title_norm", "company_norm", "location_norm"),
        Index("ix_jobs_last_seen", "last_seen"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # Display fields, taken from the first posting and backfilled from
    # later postings when the first one lacked them.
    title: Mapped[str] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    # Normalized dedupe keys (see normalize.py).
    title_norm: Mapped[str] = mapped_column(Text)
    company_norm: Mapped[str | None] = mapped_column(Text)
    location_norm: Mapped[str | None] = mapped_column(Text)

    # Annual figures in whole currency units; parsed from structured
    # source fields when available, else regex over the description.
    salary_min: Mapped[int | None] = mapped_column(BigInteger)
    salary_max: Mapped[int | None] = mapped_column(BigInteger)
    salary_currency: Mapped[str | None] = mapped_column(Text)

    remote: Mapped[bool | None]
    """True/False when a source said so explicitly; None = unknown."""

    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    postings: Mapped[list[Posting]] = relationship(back_populates="job")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Job {self.id}: {self.title!r} @ {self.company!r}>"


class Posting(Base):
    """One source's record of a job — raw payload kept verbatim.

    ``raw`` (JSONB) is the source's full response for this posting, so
    when the normalized schema grows a field, old postings can be
    re-normalized without re-fetching (the point made in sources/base.py).
    """

    __tablename__ = "postings"
    __table_args__ = (
        # Tier-1 identity: a source's own ID for a posting is unique
        # within that source. Seeing it again is a refresh, not a new row.
        UniqueConstraint("source", "external_id", name="uq_postings_source_external_id"),
        # Tier-1 cross-source match: same canonical URL from two sources
        # means the same underlying job.
        Index("ix_postings_url_canon", "url_canon"),
        Index("ix_postings_job_id", "job_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("jobs.id", ondelete="CASCADE"))

    source: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str] = mapped_column(Text)

    url: Mapped[str] = mapped_column(Text)
    url_canon: Mapped[str] = mapped_column(Text)

    title: Mapped[str] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)

    job: Mapped[Job] = relationship(back_populates="postings")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Posting {self.source}:{self.external_id} job={self.job_id}>"
