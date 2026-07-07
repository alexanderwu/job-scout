"""Demo-data seeder: weeks of plausible ingestion history in seconds.

Phase 6's polish problem: freshness, trends, and staleness features
only *show* anything after weeks of scheduled ingestion. This seeder
fabricates that history — but it does it **through the real pipeline**
(``upsert_posting`` with backdated ``fetched_at``), not with direct
INSERTs, so seeded rows have exercised the same dedupe, salary-
extraction, and backfill code paths as live data. If the pipeline has
a bug, the seeder trips it; direct INSERTs would paper over it.

Deterministic (fixed RNG seed): running it twice produces the same
world, so demo walkthroughs and screenshots are reproducible. All rows
carry source names prefixed ``seed_`` — one WHERE clause separates
demo data from anything real, and ``jobscout seed --wipe`` clears only
its own mess.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.ingest.pipeline import SourceStats, upsert_posting
from jobscout.models import Job, Posting
from jobscout.sources.base import RawPosting

RNG_SEED = 42

COMPANIES = [
    ("Acme Analytics", "San Francisco, CA"),
    ("Globex", "New York, NY"),
    ("Initech", "Austin, TX"),
    ("Umbrella Data", "Remote"),
    ("Hooli", "Palo Alto, CA"),
    ("Stark Industries", "Boston, MA"),
    ("Wayne Enterprises", "Chicago, IL"),
    ("Pied Piper", "Remote"),
    ("Vandelay Systems", "Seattle, WA"),
    ("Wonka Compute", "Denver, CO"),
    ("Tyrell Corp", "Los Angeles, CA"),
    ("Aperture Labs", "Remote"),
]


@dataclass
class RoleTemplate:
    title: str
    skills: list[str]
    salary_band: tuple[int, int]  # midpoint range in thousands
    remote_share: float


ROLES = [
    RoleTemplate(
        "Data Engineer",
        ["Python", "SQL", "Airflow", "Spark", "Kafka", "dbt", "Snowflake", "AWS", "Terraform"],
        (140, 200),
        0.5,
    ),
    RoleTemplate(
        "Senior Data Engineer",
        ["Python", "SQL", "Airflow", "Kafka", "Spark", "Kubernetes", "data modeling", "GCP"],
        (170, 240),
        0.5,
    ),
    RoleTemplate(
        "Machine Learning Engineer",
        ["Python", "PyTorch", "MLOps", "Kubernetes", "embeddings", "LLMs", "AWS", "Ray"],
        (170, 260),
        0.4,
    ),
    RoleTemplate(
        "Analytics Engineer",
        ["SQL", "dbt", "Python", "BigQuery", "Looker", "data modeling"],
        (120, 170),
        0.6,
    ),
    RoleTemplate(
        "Backend Engineer",
        ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker", "Kubernetes", "REST"],
        (140, 210),
        0.4,
    ),
    RoleTemplate(
        "Frontend Engineer",
        ["TypeScript", "React", "Next.js", "CSS", "GraphQL"],
        (130, 190),
        0.4,
    ),
    RoleTemplate(
        "Platform Engineer",
        ["Kubernetes", "Terraform", "AWS", "Go", "Prometheus", "CI/CD", "observability"],
        (150, 220),
        0.5,
    ),
    RoleTemplate(
        "Product Designer",
        ["product management", "stakeholder management"],
        (110, 160),
        0.3,
    ),
]

_DESCRIPTION = """{company} is hiring a {title}.

About the role
We are looking for a {title} to join our {team} team. You will design,
build, and operate systems that {mission}.

What you'll need
{skill_bullets}

Compensation
The annual salary range for this role is ${lo:,} - ${hi:,} plus equity.
"""

_MISSIONS = [
    "power decision-making across the company",
    "serve millions of requests a day",
    "turn raw events into trustworthy datasets",
    "ship customer-facing features weekly",
    "keep our platform fast, observable, and boring",
]

_TEAMS = ["Data Platform", "Core Product", "Infrastructure", "Growth", "ML Platform"]


async def seed(
    session: AsyncSession, *, weeks: int = 8, jobs_per_week: int = 12, wipe: bool = False
) -> SourceStats:
    """Populate `weeks` of history. Returns pipeline stats for the run."""
    if wipe:
        await wipe_seed_data(session)

    rng = random.Random(RNG_SEED)
    now = datetime.now(tz=UTC)
    stats = SourceStats(source="seed")

    for week in range(weeks):
        week_start = now - timedelta(weeks=weeks - 1 - week)
        for i in range(jobs_per_week):
            role = rng.choice(ROLES)
            company, hq = rng.choice(COMPANIES)
            remote = rng.random() < role.remote_share
            location = "Remote" if remote else hq
            # Skill mix drifts: a couple of skills are dropped per
            # posting so trends and skill-gap shares aren't uniform.
            skills = [s for s in role.skills if rng.random() > 0.25] or role.skills[:3]
            mid = rng.randint(*role.salary_band) * 1000
            lo, hi = int(mid * 0.9), int(mid * 1.1)
            first_fetch = week_start + timedelta(days=rng.randint(0, 6), hours=rng.randint(8, 18))
            if first_fetch > now:
                first_fetch = now

            description = _DESCRIPTION.format(
                company=company,
                title=role.title,
                team=rng.choice(_TEAMS),
                mission=rng.choice(_MISSIONS),
                skill_bullets="\n".join(f"- {s}" for s in skills),
                lo=lo,
                hi=hi,
            )
            external_id = f"seed-{week}-{i}"
            url = f"https://boards.example.com/{company.lower().replace(' ', '-')}/{external_id}"
            posting = RawPosting(
                source="seed_greenhouse",
                external_id=external_id,
                url=url,
                title=role.title,
                company=company,
                location=location,
                description=description,
                salary_min=lo,
                salary_max=hi,
                salary_currency="USD",
                remote=remote,
                posted_at=first_fetch - timedelta(days=rng.randint(0, 3)),
                fetched_at=first_fetch,
                raw={"seed": True, "week": week},
            )
            await upsert_posting(session, posting, stats)
            stats.fetched += 1

            # ~20% get cross-posted on an aggregator a day later — the
            # dedupe tiers get real work (same URL, different source).
            if rng.random() < 0.2:
                cross = posting.model_copy(
                    update={
                        "source": "seed_aggregator",
                        "external_id": f"agg-{external_id}",
                        "url": url + "?utm_source=aggregator",
                        "fetched_at": min(first_fetch + timedelta(days=1), now),
                    }
                )
                await upsert_posting(session, cross, stats)
                stats.fetched += 1

            # ~75% are still open: refresh them "today" so last_seen is
            # current. The remaining quarter go stale — exactly what the
            # staleness filter and ops freshness metrics need to show.
            if rng.random() < 0.75:
                refresh = posting.model_copy(update={"fetched_at": now})
                await upsert_posting(session, refresh, stats)

    await session.commit()
    return stats


async def wipe_seed_data(session: AsyncSession) -> int:
    """Delete seeded jobs (any job whose postings all come from seed_*)."""
    seeded_job_ids = select(Posting.job_id).where(Posting.source.startswith("seed_"))
    result = await session.execute(delete(Job).where(Job.id.in_(seeded_job_ids)))
    await session.commit()  # postings cascade via FK
    # CursorResult (which DELETE returns) has rowcount; the base Result
    # type mypy sees doesn't, hence the narrow getattr.
    return int(getattr(result, "rowcount", 0) or 0)
