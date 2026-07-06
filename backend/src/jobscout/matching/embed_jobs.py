"""Batch job: embed every job that needs it.

"Needs it" = no vector yet, OR the vector was made by a different
provider/model than the current one. That single WHERE clause makes
model switches self-healing: change EMBEDDING_PROVIDER in .env, run
this, and the corpus converges to the new space — no bespoke
"re-embed everything" tooling, no flag files.

Runs after every ingestion (worker.py chains it) and on demand via
``jobscout embed``. Batched both ways: read in pages of rows, embed in
chunks sized for the model — local transformer models get big
throughput wins from batching that one-text-at-a-time calls throw away.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.matching.embeddings import EmbeddingProvider
from jobscout.models import Job

logger = logging.getLogger(__name__)

BATCH_SIZE = 64

# Job text is truncated before embedding: MiniLM reads only its first
# 256 tokens anyway, and the useful signal (title, skills, requirements)
# lives at the top of a posting; embedding 20 KB of benefits boilerplate
# would just be slower, not smarter.
MAX_CHARS = 4000


@dataclass
class EmbedStats:
    embedded: int = 0
    signature: str = ""


def job_text(job: Job) -> str:
    """The text a job is embedded from.

    Title/company/location are prepended even though description
    usually repeats them: for the many postings whose descriptions
    start with boilerplate, this keeps the strongest signal in the
    window the model actually reads. Must stay in sync with how
    *resumes* are embedded only in the sense that both are plain text —
    embedding models map any text into the same space.
    """
    parts = [job.title, job.company or "", job.location or "", job.description or ""]
    return "\n".join(p for p in parts if p)[:MAX_CHARS]


async def embed_pending_jobs(session: AsyncSession, provider: EmbeddingProvider) -> EmbedStats:
    stats = EmbedStats(signature=provider.signature)
    while True:
        jobs = list(
            await session.scalars(
                select(Job)
                .where(
                    or_(
                        Job.embedding.is_(None),
                        Job.embedding_sig != provider.signature,
                        Job.embedding_sig.is_(None),
                    )
                )
                .limit(BATCH_SIZE)
            )
        )
        if not jobs:
            return stats
        texts = [job_text(job) for job in jobs]
        # to_thread: providers are sync + CPU-bound; don't stall the
        # event loop for the duration of a transformer forward pass.
        vectors = await asyncio.to_thread(provider.embed, texts)
        now = datetime.now(tz=UTC)
        for job, vector in zip(jobs, vectors, strict=True):
            job.embedding = vector
            job.embedding_sig = provider.signature
            job.embedded_at = now
        await session.commit()
        stats.embedded += len(jobs)
        logger.info("embedded %d jobs (total %d)", len(jobs), stats.embedded)
