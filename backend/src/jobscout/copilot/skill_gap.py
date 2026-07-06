"""Skill-gap analysis: your profile vs. a target role's aggregate demands.

The question this answers is different from a single match explanation:
not "what does *this* job want that I lack" but "across all Data
Engineer postings in my corpus, which skills appear most, and which of
those am I missing?" — i.e. what to learn next for the role you want,
grounded in the actual market you ingested rather than a listicle.

Implementation is deliberately plain aggregation: select jobs whose
title matches the target role, run the same curated skill extractor
used for match explanations over each description, count frequencies,
and split into have/missing by the profile's skills. Title-substring
selection (not embedding search) because the sample must be *auditable*
— "these 43 postings titled data engineer" is a defensible denominator;
"43 nearest vectors" invites silently polluted samples.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.matching.explain import extract_skills
from jobscout.models import Job
from jobscout.normalize import normalize_title

MAX_SAMPLE = 200


@dataclass
class SkillDemand:
    skill: str
    count: int
    share: float  # fraction of sampled postings mentioning it


@dataclass
class SkillGapReport:
    role: str
    sampled_jobs: int
    have: list[SkillDemand] = field(default_factory=list)
    missing: list[SkillDemand] = field(default_factory=list)


async def skill_gap(
    session: AsyncSession,
    role: str,
    profile_skills: set[str],
    *,
    min_share: float = 0.1,
) -> SkillGapReport:
    """Aggregate skill demand for `role`, split by the profile.

    ``min_share`` drops one-off mentions: a skill named in a single
    posting out of fifty is noise, not market demand.
    """
    role_norm = normalize_title(role)
    jobs = await session.scalars(
        select(Job.description)
        .where(Job.title_norm.contains(role_norm), Job.description.is_not(None))
        .limit(MAX_SAMPLE)
    )
    descriptions = list(jobs)

    counts: Counter[str] = Counter()
    for description in descriptions:
        # set() per posting: a skill counts once per posting no matter
        # how often the description repeats it — we're measuring "how
        # many employers want X", not word frequency.
        counts.update(extract_skills(description or ""))

    total = len(descriptions)
    report = SkillGapReport(role=role, sampled_jobs=total)
    if total == 0:
        return report
    for skill, count in counts.most_common():
        share = count / total
        if share < min_share:
            continue
        demand = SkillDemand(skill=skill, count=count, share=round(share, 3))
        (report.have if skill in profile_skills else report.missing).append(demand)
    return report
