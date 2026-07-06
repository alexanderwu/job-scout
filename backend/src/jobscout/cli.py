"""The ``jobscout`` command-line interface.

Typer over click/argparse: it generates the CLI from type-hinted
function signatures, which matches this codebase's strict-mypy style
(argparse would duplicate every option as untyped strings; click is
what typer wraps anyway). The CLI is deliberately thin — every command
parses args, calls into the same library code the worker/API use, and
prints. No business logic lives here.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import typer

app = typer.Typer(
    help="Job Scout: ingest job postings, then match them against your resume.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,  # real tracebacks; we're the only user
)


@app.command()
def ingest(
    queue: bool = typer.Option(
        False,
        "--queue",
        "-q",
        help="Enqueue for the RQ worker instead of running inline.",
    ),
) -> None:
    """Fetch from all configured sources, dedupe, and store.

    Inline by default so first-time use needs no worker running;
    --queue hands the same function to RQ for background execution.
    """
    if queue:
        from redis import Redis
        from rq import Queue

        from jobscout.config import get_settings
        from jobscout.worker import QUEUE_NAME, run_ingestion

        q = Queue(QUEUE_NAME, connection=Redis.from_url(get_settings().redis_url))
        job = q.enqueue(run_ingestion)
        typer.echo(f"enqueued ingestion as RQ job {job.id} on queue '{QUEUE_NAME}'")
        return

    from jobscout.worker import run_ingestion

    summary = run_ingestion()
    sources = summary.get("sources")
    if not sources:
        typer.echo("nothing ingested — configure sources in .env (see .env.example)")
        raise typer.Exit(code=1)
    assert isinstance(sources, list)
    for s in sources:
        if s["failed"]:
            typer.echo(f"  {s['source']}: FAILED — {s['error']}")
        else:
            typer.echo(
                f"  {s['source']}: fetched {s['fetched']} "
                f"({s['new_jobs']} new jobs, {s['cross_posts']} cross-posts, "
                f"{s['refreshed']} refreshed)"
            )
    if any(s["failed"] for s in sources):
        raise typer.Exit(code=1)


@app.command()
def recent(
    hours: int = typer.Option(24, help="Look-back window."),
    limit: int = typer.Option(50, help="Max rows to print."),
) -> None:
    """Jobs first seen in the last N hours — the Phase 1 milestone query."""

    async def _query() -> list[tuple[str, str | None, str | None, datetime]]:
        from sqlalchemy import select

        from jobscout.db import session_scope
        from jobscout.models import Job

        cutoff = datetime.now(tz=UTC) - timedelta(hours=hours)
        async with session_scope() as session:
            rows = await session.execute(
                select(Job.title, Job.company, Job.location, Job.first_seen)
                .where(Job.first_seen >= cutoff)
                .order_by(Job.first_seen.desc())
                .limit(limit)
            )
            return [tuple(r) for r in rows]

    rows = asyncio.run(_query())
    if not rows:
        typer.echo(f"no jobs first seen in the last {hours}h")
        return
    for title, company, location, first_seen in rows:
        typer.echo(f"{first_seen:%Y-%m-%d %H:%M}  {title}  @ {company or '?'}  ({location or '?'})")
    typer.echo(f"\n{len(rows)} job(s) first seen in the last {hours}h")


def main() -> None:  # console-script entrypoint (pyproject [project.scripts])
    app()


if __name__ == "__main__":
    main()
