"""RQ job functions + the cron schedule that enqueues them.

Architecture recap (PLAN.md "Caching / queueing"): Redis + RQ. Three
processes cooperate:

- ``rq worker``  — pops jobs off the ``ingest`` queue and runs them.
- ``rq cron``    — enqueues :func:`run_ingestion` on an interval, using
  RQ >= 2.4's built-in cron scheduler. (PLAN.md suggested rq-scheduler
  or APScheduler; RQ has since grown native cron, so the extra
  dependency is no longer justified.)
- the app/CLI    — can also enqueue on demand (``jobscout ingest -q``).

Why a queue at all, when a cron entry calling ``jobscout ingest`` would
work? Retry semantics (a failed run is visible in RQ's failed registry,
not lost in a cron mail nobody reads), no overlapping runs, and queue
depth/latency become observable — which Phase 6's ops view wants anyway.

RQ jobs must be importable sync functions with picklable args, so this
module is the sync bridge: it owns ``asyncio.run`` and builds fresh
engine/client objects *inside* the job (a forked worker process must
never inherit event loops or connection pools from the parent).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from jobscout.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from jobscout.ingest.pipeline import IngestReport, ingest_all
from jobscout.ingest.registry import configured_sources, default_http_client

logger = logging.getLogger(__name__)

QUEUE_NAME = "ingest"


def run_ingestion() -> dict[str, object]:
    """The RQ job: ingest every configured source once.

    Returns a plain dict (not IngestReport) because RQ stores results in
    Redis — keep them JSON-ish and small.
    """
    report = asyncio.run(_run())
    summary: dict[str, object] = {
        "started_at": report.started_at.isoformat() if report.started_at else None,
        "sources": [
            {
                "source": s.source,
                "fetched": s.fetched,
                "new_jobs": s.new_jobs,
                "cross_posts": s.cross_posts,
                "refreshed": s.refreshed,
                "failed": s.failed,
                "error": s.error,
            }
            for s in report.sources
        ],
    }
    logger.info("ingestion run: %s", summary)
    return summary


async def _run() -> IngestReport:
    # Local imports of engine machinery keep module import light —
    # `rq cron` imports this module just to *register* the schedule.
    from jobscout.db import session_scope

    settings = get_settings()
    async with default_http_client() as http:
        sources = configured_sources(settings, http)
        if not sources:
            logger.warning(
                "no sources configured — set GREENHOUSE_BOARDS/LEVER_SITES "
                "(or HIRING_CAFE_ENABLED) in .env"
            )
            return IngestReport()
        async with session_scope() as session:
            report = await ingest_all(session, sources)
            # Chain embedding so fresh jobs are searchable immediately;
            # a separate schedule would add a lag window for no benefit.
            # Failures here don't invalidate the ingest (data is safely
            # committed) — the next run retries whatever's unembedded.
            try:
                await _embed_new(session)
            except Exception:
                logger.exception("post-ingest embedding failed; ingest data is intact")
            return report


async def _embed_new(session: AsyncSession) -> None:
    from jobscout.matching.embed_jobs import embed_pending_jobs
    from jobscout.matching.embeddings import provider_from_settings

    stats = await embed_pending_jobs(session, provider_from_settings(get_settings()))
    if stats.embedded:
        logger.info("embedded %d new/changed jobs (%s)", stats.embedded, stats.signature)


def register_cron() -> None:
    """Register the periodic ingestion job (imported by ``rq cron``).

    Usage:  rq cron jobscout.schedules  (see schedules.py / justfile)
    """
    from rq import cron

    cron.register(
        run_ingestion,
        queue_name=QUEUE_NAME,
        interval=get_settings().ingest_interval_minutes * 60,
    )
