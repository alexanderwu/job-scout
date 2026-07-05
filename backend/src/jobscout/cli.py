"""The ``jobscout`` CLI: ingestion (Phase 1) plus embedding and resume
matching (Phase 2) — the daily-driver interface PLAN.md's Phase 2
milestone calls for, no frontend required.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from jobscout.db import make_engine, make_session_factory
from jobscout.embed import embed_pending_jobs
from jobscout.embeddings.local import LocalEmbeddingProvider
from jobscout.matching import extract_keywords, rank_jobs
from jobscout.pipeline import ingest
from jobscout.queries import jobs_first_seen_since, jobs_with_embeddings
from jobscout.resume import read_resume_text
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


async def _cmd_embed(args: argparse.Namespace) -> None:
    engine = make_engine()
    try:
        session_factory = make_session_factory(engine)
        provider = LocalEmbeddingProvider()
        async with session_factory() as session:
            count = await embed_pending_jobs(session, provider, batch_size=args.batch_size)
            await session.commit()
        print(f"embedded {count} job(s)")
    finally:
        await engine.dispose()


def _cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("jobscout.api.app:app", host=args.host, port=args.port, reload=args.reload)


async def _cmd_match(args: argparse.Namespace) -> None:
    engine = make_engine()
    try:
        resume_text = read_resume_text(Path(args.resume))
        provider = LocalEmbeddingProvider()
        (resume_embedding,) = provider.embed([resume_text])
        resume_keywords = extract_keywords(resume_text)

        session_factory = make_session_factory(engine)
        async with session_factory() as session:
            candidates = await jobs_with_embeddings(session, location=args.location)
            matches = rank_jobs(
                list(candidates), resume_embedding, resume_keywords, limit=args.limit
            )

        for rank, match in enumerate(matches, start=1):
            job = match.job
            print(f"{rank}. [{match.score:.3f}] {job.title} @ {job.company or 'unknown'}")
            print(f"   {job.canonical_url}")
            if match.matched_keywords:
                print(f"   matched: {', '.join(match.matched_keywords)}")
        print(f"{len(matches)} match(es)")
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

    embed_parser = subcommands.add_parser(
        "embed", help="Embed jobs that have a description but no embedding yet."
    )
    embed_parser.add_argument("--batch-size", type=int, default=32)
    embed_parser.set_defaults(func=_cmd_embed)

    match_parser = subcommands.add_parser(
        "match", help="Rank jobs against a resume, with visible reasoning."
    )
    match_parser.add_argument("resume", help="Path to a resume (.pdf, .txt, or .md).")
    match_parser.add_argument("--location", default=None, help="Filter jobs by location.")
    match_parser.add_argument("--limit", type=int, default=10)
    match_parser.set_defaults(func=_cmd_match)

    serve_parser = subcommands.add_parser(
        "serve", help="Run the Phase 3 API (FastAPI, via uvicorn)."
    )
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--reload", action="store_true")
    serve_parser.set_defaults(func=_cmd_serve, is_async=False)

    args = parser.parse_args()
    if getattr(args, "is_async", True):
        asyncio.run(args.func(args))
    else:
        args.func(args)


if __name__ == "__main__":
    main()
