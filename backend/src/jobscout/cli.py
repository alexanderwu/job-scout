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


@app.command()
def embed() -> None:
    """Embed all jobs that lack a current-model vector.

    Ingestion normally chains this automatically; run it by hand after
    switching EMBEDDING_PROVIDER/EMBEDDING_MODEL to re-embed the corpus.
    """

    async def _embed() -> int:
        from jobscout.config import get_settings
        from jobscout.db import session_scope
        from jobscout.matching.embed_jobs import embed_pending_jobs
        from jobscout.matching.embeddings import provider_from_settings

        provider = provider_from_settings(get_settings())
        async with session_scope() as session:
            stats = await embed_pending_jobs(session, provider)
        typer.echo(f"embedded {stats.embedded} job(s) with {stats.signature}")
        return stats.embedded

    asyncio.run(_embed())


@app.command()
def match(
    resume: str = typer.Argument(..., help="Path to your resume (.pdf, .txt, or .md)."),
    top: int = typer.Option(20, help="How many matches to show."),
    location: str | None = typer.Option(
        None, help="Only jobs whose location contains this substring."
    ),
    remote: bool = typer.Option(False, "--remote", help="Only jobs explicitly marked remote."),
    min_salary: int | None = typer.Option(
        None, help="Only jobs whose salary range reaches this (annual)."
    ),
    max_age_days: int = typer.Option(45, help="Ignore jobs not seen in this many days."),
) -> None:
    """Rank stored jobs against your resume — the Phase 2 milestone.

    Every match prints its score and the shared-skill reasoning, so you
    can see *why* it ranked where it did.
    """
    from pathlib import Path

    from jobscout.matching.resume import load_resume_text

    resume_text = load_resume_text(Path(resume))

    async def _match() -> None:
        from jobscout.config import get_settings
        from jobscout.db import session_scope
        from jobscout.matching.embeddings import provider_from_settings
        from jobscout.matching.engine import MatchFilters, match_resume

        provider = provider_from_settings(get_settings())
        filters = MatchFilters(
            location_contains=location,
            remote_only=remote,
            min_salary=min_salary,
            max_age_days=max_age_days,
        )
        async with session_scope() as session:
            result = await match_resume(session, provider, resume_text, filters=filters, limit=top)

        if not result.matches:
            typer.echo(
                "no matches. Either nothing is ingested yet (`jobscout ingest`), "
                "nothing is embedded with the current model (`jobscout embed`), "
                "or the filters excluded everything."
            )
            raise typer.Exit(code=1)

        if result.resume_skills:
            typer.echo(f"resume skills detected: {', '.join(sorted(result.resume_skills))}\n")
        for rank, m in enumerate(result.matches, start=1):
            job = m.job
            salary = ""
            if job.salary_min or job.salary_max:
                lo = f"{job.salary_min:,}" if job.salary_min else "?"
                hi = f"{job.salary_max:,}" if job.salary_max else "?"
                salary = f"  {lo}-{hi} {job.salary_currency or ''}".rstrip()
            typer.echo(
                f"{rank:>2}. [{m.score:.0%}] {job.title} @ {job.company or '?'}"
                f"  ({job.location or '?'}){salary}"
            )
            typer.echo(f"    {m.explanation.summary()}")
            url = job.postings[0].url if job.postings else None
            if url:
                typer.echo(f"    {url}")

    asyncio.run(_match())


def main() -> None:  # console-script entrypoint (pyproject [project.scripts])
    app()


if __name__ == "__main__":
    main()
