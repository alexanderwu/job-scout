"""Ops metrics (Phase 6): proof the system's health is observable.

Every number here is *derived from systems already running* — Postgres
statistics views, Redis INFO, RQ's registries, and one timed probe
query — rather than from a metrics pipeline. At single-user scale,
Prometheus+Grafana would be more moving parts than the app itself; the
teaching point is knowing where the built-in gauges live:

- pg_stat_database: block cache hit ratio (how often Postgres served
  reads from shared_buffers instead of disk);
- Redis INFO stats: keyspace hit ratio + queue depth via RQ;
- a timed vector search: the user-facing latency that matters here,
  measured end to end through the real engine (index included);
- corpus counts: rows, embedding coverage, and freshness (staleness is
  *derived* from last_seen, consistent with the models.py design).

Everything degrades gracefully: Redis down -> nulls in that section,
not a 500 — an ops page that dies when a dependency dies is useless
exactly when you need it.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select, text

from jobscout.api.deps import ProviderDep, SessionDep
from jobscout.config import get_settings
from jobscout.matching.engine import rank_jobs
from jobscout.models import Job, Posting

router = APIRouter(prefix="/ops", tags=["ops"])

STALE_AFTER_DAYS = 45


class CorpusStats(BaseModel):
    jobs: int
    postings: int
    embedded: int
    embedding_coverage: float
    new_last_24h: int
    active: int
    stale: int


class QueueStats(BaseModel):
    reachable: bool
    queue_depth: int | None = None
    failed_jobs: int | None = None
    keyspace_hit_ratio: float | None = None


class OpsReport(BaseModel):
    corpus: CorpusStats
    newest_job_seen: datetime | None
    last_ingest_activity: datetime | None
    match_latency_ms: float
    pg_cache_hit_ratio: float | None
    queue: QueueStats


@router.get("")
async def ops(session: SessionDep, provider: ProviderDep) -> OpsReport:
    now = datetime.now(tz=UTC)
    stale_cutoff = now - timedelta(days=STALE_AFTER_DAYS)

    jobs = await session.scalar(select(func.count()).select_from(Job)) or 0
    postings = await session.scalar(select(func.count()).select_from(Posting)) or 0
    embedded = (
        await session.scalar(
            select(func.count()).select_from(Job).where(Job.embedding.is_not(None))
        )
        or 0
    )
    new_24h = (
        await session.scalar(
            select(func.count()).select_from(Job).where(Job.first_seen >= now - timedelta(hours=24))
        )
        or 0
    )
    active = (
        await session.scalar(
            select(func.count()).select_from(Job).where(Job.last_seen >= stale_cutoff)
        )
        or 0
    )
    newest_seen = await session.scalar(select(func.max(Job.first_seen)))
    last_activity = await session.scalar(select(func.max(Posting.last_seen)))

    # Timed probe: a real vector search through the real engine. This
    # is the latency a user feels on the matches page.
    probe_started = time.perf_counter()
    (probe_vec,) = await asyncio.to_thread(provider.embed, ["ops latency probe: data engineer"])
    await rank_jobs(session, provider, probe_vec, set(), limit=10)
    match_latency_ms = (time.perf_counter() - probe_started) * 1000

    pg_ratio = await session.scalar(
        text(
            "SELECT round(blks_hit::numeric / nullif(blks_hit + blks_read, 0), 4) "
            "FROM pg_stat_database WHERE datname = current_database()"
        )
    )

    return OpsReport(
        corpus=CorpusStats(
            jobs=jobs,
            postings=postings,
            embedded=embedded,
            embedding_coverage=round(embedded / jobs, 4) if jobs else 0.0,
            new_last_24h=new_24h,
            active=active,
            stale=jobs - active,
        ),
        newest_job_seen=newest_seen,
        last_ingest_activity=last_activity,
        match_latency_ms=round(match_latency_ms, 1),
        pg_cache_hit_ratio=float(pg_ratio) if pg_ratio is not None else None,
        queue=await asyncio.to_thread(_queue_stats),
    )


def _queue_stats() -> QueueStats:
    """Redis/RQ gauges; sync redis client, so called via to_thread."""
    try:
        from redis import Redis
        from rq import Queue

        redis = Redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
        queue = Queue("ingest", connection=redis)
        info = redis.info("stats")
        assert isinstance(info, dict)
        hits = int(info.get("keyspace_hits", 0))
        misses = int(info.get("keyspace_misses", 0))
        ratio = round(hits / (hits + misses), 4) if hits + misses else None
        return QueueStats(
            reachable=True,
            queue_depth=queue.count,
            failed_jobs=queue.failed_job_registry.count,
            keyspace_hit_ratio=ratio,
        )
    except Exception:  # any Redis failure = "unreachable", not a 500
        return QueueStats(reachable=False)
