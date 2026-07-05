"""On-demand ingestion CLI (Phase 1 milestone: run ingestion on demand and
query recent jobs, no manual DB queries required).

A daily-driver ``jobscout match`` command arrives in Phase 2; this module
only needs to prove the ingestion pipeline end to end.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

import httpx

from jobscout.db import make_engine, make_session_factory
from jobscout.pipeline import ingest
from jobscout.queries import jobs_first_seen_since
from jobscout.sources.base import JobSource
from jobscout.sources.hiring_cafe import HiringCafeSource


def configured_sources(http: httpx.AsyncClient, *, max_pages: int | None) -> list[JobSource]:
    """The sources a real ingestion run pulls from.

    Adding a source is a one-line change here, per PLAN.md's adapter
    interface — the pipeline itself doesn't change.
    """
    return [HiringCafeSource(http, max_pages=max_pages)]


async def _cmd_ingest(args: argparse.Namespace) -> None:
    engine = make_engine()
    try:
        session_factory = make_session_factory(engine)
        async with httpx.AsyncClient(timeout=30) as http:
            sources = configured_sources(http, max_pages=args.max_pages)
            async with session_factory() as session:
                stats = await ingest(sources, session)
                await session.commit()
        for source, count in stats.fetched_by_source.items():
            print(f"{source}: fetched {count} postings")
        print(f"jobs created: {stats.jobs_created}, postings updated: {stats.postings_updated}")
    finally:
        await engine.dispose()


async def _cmd_recent(args: argparse.Namespace) -> None:
    engine = make_engine()
    try:
        session_factory = make_session_factory(engine)
        since = datetime.now(tz=UTC) - timedelta(hours=args.hours)
        async with session_factory() as session:
            jobs = await jobs_first_seen_since(session, since)
        for job in jobs:
            when = f"{job.first_seen:%Y-%m-%d %H:%M}"
            print(f"[{when}] {job.title} @ {job.company or 'unknown'} — {job.canonical_url}")
        print(f"{len(jobs)} job(s) first seen in the last {args.hours}h")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="jobscout")
    subcommands = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subcommands.add_parser(
        "ingest", help="Run ingestion against all configured sources."
    )
    ingest_parser.add_argument("--max-pages", type=int, default=None)
    ingest_parser.set_defaults(func=_cmd_ingest)

    recent_parser = subcommands.add_parser(
        "recent", help="List jobs first seen in a recent time window."
    )
    recent_parser.add_argument("--hours", type=float, default=24)
    recent_parser.set_defaults(func=_cmd_recent)

    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
