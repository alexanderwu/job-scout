"""Initial schema: jobs and job_postings.

Revision ID: 0001
Revises:
Create Date: 2026-07-05

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector is enabled here (rather than deferred to Phase 2) per the
    # docker-compose.yml note that the extension setup lives in the
    # Phase 1 migrations, even though no vector column exists yet.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("normalized_title", sa.String(), nullable=False),
        sa.Column("normalized_company", sa.String(), nullable=True),
        sa.Column("canonical_url", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_jobs_normalized_title", "jobs", ["normalized_title"])
    op.create_index("ix_jobs_normalized_company", "jobs", ["normalized_company"])
    op.create_index("ix_jobs_canonical_url", "jobs", ["canonical_url"], unique=True)
    op.create_index("ix_jobs_first_seen", "jobs", ["first_seen"])

    op.create_table(
        "job_postings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.UniqueConstraint("source", "external_id", name="uq_job_postings_source_external_id"),
    )
    op.create_index("ix_job_postings_source", "job_postings", ["source"])
    op.create_index("ix_job_postings_job_id", "job_postings", ["job_id"])


def downgrade() -> None:
    op.drop_table("job_postings")
    op.drop_table("jobs")
