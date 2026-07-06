"""Initial schema: jobs + postings (see models.py for the design notes).

Drafted with `alembic revision --autogenerate`, then hand-reviewed —
the one manual addition is enabling the pgvector extension, which
autogenerate can't know about (Phase 2 stores embeddings in a `vector`
column; docker-compose.yml points here for the CREATE EXTENSION).

Revision ID: 92da916861bd
Revises:
Create Date: 2026-07-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "92da916861bd"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: on databases where the extension was already
    # enabled by an admin (it needs superuser), this is a no-op instead
    # of a permissions error.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("title_norm", sa.Text(), nullable=False),
        sa.Column("company_norm", sa.Text(), nullable=True),
        sa.Column("location_norm", sa.Text(), nullable=True),
        sa.Column("salary_min", sa.BigInteger(), nullable=True),
        sa.Column("salary_max", sa.BigInteger(), nullable=True),
        sa.Column("salary_currency", sa.Text(), nullable=True),
        sa.Column("remote", sa.Boolean(), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_jobs_dedupe_key", "jobs", ["title_norm", "company_norm", "location_norm"], unique=False
    )
    op.create_index("ix_jobs_last_seen", "jobs", ["last_seen"], unique=False)
    op.create_table(
        "postings",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_canon", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_postings_source_external_id"),
    )
    op.create_index("ix_postings_job_id", "postings", ["job_id"], unique=False)
    op.create_index("ix_postings_url_canon", "postings", ["url_canon"], unique=False)


def downgrade() -> None:
    # The extension is deliberately NOT dropped here: other schemas may
    # use it, and downgrading the app schema shouldn't break them.
    op.drop_index("ix_postings_url_canon", table_name="postings")
    op.drop_index("ix_postings_job_id", table_name="postings")
    op.drop_table("postings")
    op.drop_index("ix_jobs_last_seen", table_name="jobs")
    op.drop_index("ix_jobs_dedupe_key", table_name="jobs")
    op.drop_table("jobs")
