"""Job embeddings for semantic search (Phase 2).

Drafted with autogenerate, then hand-fixed — two things it can't do:

- it emits ``pgvector.sqlalchemy.vector.VECTOR`` without generating the
  import (a known autogenerate gap for third-party types);
- it knows nothing about vector *indexes*. The HNSW index below is the
  thing that makes ANN search fast: without it every match query scans
  and re-scores all rows. HNSW over IVFFlat because it needs no
  training step on existing data (an empty, freshly-migrated table
  can't train IVFFlat centroids) and has better recall at this scale;
  the cost — slower inserts — is irrelevant at thousands of rows.
  ``vector_cosine_ops`` matches the ORDER BY in matching/engine.py; an
  index only accelerates the operator class it was built for.

Revision ID: 7cdcbf954cdc
Revises: 92da916861bd
Create Date: 2026-07-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "7cdcbf954cdc"
down_revision = "92da916861bd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("embedding", Vector(dim=384), nullable=True))
    op.add_column("jobs", sa.Column("embedding_sig", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_jobs_embedding_hnsw",
        "jobs",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_embedding_hnsw", table_name="jobs")
    op.drop_column("jobs", "embedded_at")
    op.drop_column("jobs", "embedding_sig")
    op.drop_column("jobs", "embedding")
