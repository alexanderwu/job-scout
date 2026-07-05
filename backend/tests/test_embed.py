"""Embedding batch job tests (PLAN.md Phase 2)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.embed import embed_pending_jobs
from jobscout.embeddings.base import EMBEDDING_DIM, EmbeddingProvider
from jobscout.models import Job


class FakeProvider(EmbeddingProvider):
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[float(len(text))] + [0.0] * (EMBEDDING_DIM - 1) for text in texts]


def make_job(**overrides: object) -> Job:
    defaults: dict[str, object] = {
        "normalized_title": "data engineer",
        "canonical_url": "https://example.com/1",
        "title": "Data Engineer",
        "first_seen": datetime(2026, 1, 1, tzinfo=UTC),
        "last_seen": datetime(2026, 1, 1, tzinfo=UTC),
    }
    return Job(**{**defaults, **overrides})


async def test_embeds_jobs_missing_embeddings(session: AsyncSession) -> None:
    job = make_job(description="Build data pipelines.")
    session.add(job)
    await session.commit()

    provider = FakeProvider()
    count = await embed_pending_jobs(session, provider)
    await session.commit()

    assert count == 1
    refreshed = await session.scalar(select(Job))
    assert refreshed is not None
    assert refreshed.embedding is not None


async def test_skips_jobs_without_a_description(session: AsyncSession) -> None:
    session.add(make_job(canonical_url="https://example.com/none", description=None))
    await session.commit()

    provider = FakeProvider()
    count = await embed_pending_jobs(session, provider)

    assert count == 0
    assert provider.calls == []


async def test_batches_across_multiple_passes(session: AsyncSession) -> None:
    for i in range(5):
        session.add(
            make_job(
                canonical_url=f"https://example.com/{i}",
                description=f"Job number {i}.",
            )
        )
    await session.commit()

    provider = FakeProvider()
    count = await embed_pending_jobs(session, provider, batch_size=2)

    assert count == 5
    assert [len(batch) for batch in provider.calls] == [2, 2, 1]
