"""Add saved_jobs tracking fields (Phase 4: application tracker).

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-05

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("saved_jobs", sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "saved_jobs", sa.Column("interviewing_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("saved_jobs", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("saved_jobs", sa.Column("offer_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("saved_jobs", sa.Column("reminder_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("saved_jobs", sa.Column("notes", sa.Text(), nullable=True))
    op.create_index("ix_saved_jobs_reminder_at", "saved_jobs", ["reminder_at"])


def downgrade() -> None:
    op.drop_index("ix_saved_jobs_reminder_at", table_name="saved_jobs")
    op.drop_column("saved_jobs", "notes")
    op.drop_column("saved_jobs", "reminder_at")
    op.drop_column("saved_jobs", "offer_at")
    op.drop_column("saved_jobs", "rejected_at")
    op.drop_column("saved_jobs", "interviewing_at")
    op.drop_column("saved_jobs", "applied_at")
