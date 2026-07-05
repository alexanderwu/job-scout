"""The Phase 2 embedding batch job: fill in ``Job.embedding`` for jobs that
have a description but no embedding yet.

Separate from ingestion (``pipeline.py``) on purpose — ingestion's job is
fetch/normalize/dedupe and it runs per-source on every posting; embedding
is comparatively expensive (local model inference) and only needs to run
over whatever accumulated since the last pass, in batches sized for the
model rather than one posting at a time.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.embeddings.base import EmbeddingProvider
from jobscout.queries import jobs_missing_embeddings


async def embed_pending_jobs(
    session: AsyncSession,
    provider: EmbeddingProvider,
    *,
    batch_size: int = 32,
    max_jobs: int | None = None,
) -> int:
    """Embed jobs missing an embedding, ``batch_size`` at a time.

    Returns the number of jobs embedded. Caller commits.
    """
    embedded = 0
    while max_jobs is None or embedded < max_jobs:
        limit = batch_size if max_jobs is None else min(batch_size, max_jobs - embedded)
        jobs = await jobs_missing_embeddings(session, limit=limit)
        if not jobs:
            break
        texts = [f"{job.title}\n\n{job.description or ''}" for job in jobs]
        vectors = provider.embed(texts)
        for job, vector in zip(jobs, vectors, strict=True):
            job.embedding = vector
        await session.flush()
        embedded += len(jobs)
    return embedded
