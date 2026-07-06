"""ORM -> schema conversion helpers shared by routes."""

from __future__ import annotations

from jobscout.api.schemas import ExplanationOut, JobSummary, MatchOut, MatchResponse
from jobscout.matching.engine import MatchResult
from jobscout.models import Job


def best_apply_url(job: Job) -> str | None:
    """The URL a user should apply through.

    Postings from official ATS boards (greenhouse/lever) beat
    aggregator links: applying at the primary source avoids dead
    aggregator redirects. Ties break to the most recently seen posting.
    """
    if not job.postings:
        return None
    official = [p for p in job.postings if p.source in ("greenhouse", "lever")]
    pool = official or list(job.postings)
    return max(pool, key=lambda p: p.last_seen).url


def to_match_response(result: MatchResult) -> MatchResponse:
    return MatchResponse(
        resume_skills=sorted(result.resume_skills),
        matches=[
            MatchOut(
                job=JobSummary.model_validate(m.job),
                score=round(m.score, 4),
                apply_url=best_apply_url(m.job),
                explanation=ExplanationOut(
                    overlapping=m.explanation.overlapping,
                    missing=m.explanation.missing,
                    summary=m.explanation.summary(),
                ),
            )
            for m in result.matches
        ],
    )
