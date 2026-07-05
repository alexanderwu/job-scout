"""Resume-to-job matching and explainability (PLAN.md Phase 2, the real MVP).

Ranking runs in Python over candidate rows already filtered in SQL
(location, non-null embedding), rather than pushing cosine distance into
the query with pgvector's ``<=>`` operator. At the corpus sizes this
personal-use tool actually reaches (thousands, not millions, of postings)
brute-force cosine in Python is fast enough, and it keeps ranking logic
testable against the project's existing sqlite test fixtures instead of
requiring a real Postgres+pgvector instance in the test suite. The
``<=>``-operator, index-backed version is the documented scale-up path if
the corpus ever outgrows this.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from jobscout.models import Job

_WORD = re.compile(r"[a-z][a-z0-9+#]*")

_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "if",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "as",
    "at",
    "by",
    "from",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "this",
    "that",
    "these",
    "those",
    "you",
    "your",
    "we",
    "our",
    "will",
    "have",
    "has",
    "had",
    "it",
    "its",
    "into",
    "about",
    "than",
    "then",
    "so",
    "such",
    "not",
    "no",
    "can",
    "may",
    "must",
    "should",
    "would",
    "who",
    "what",
    "which",
    "their",
    "they",
    "them",
    "us",
    "job",
    "role",
    "work",
}
"""Generic English/job-posting filler that would otherwise dominate every
overlap and make "matched keywords" meaningless."""


def extract_keywords(text: str) -> set[str]:
    """Lowercase content words, filtered to those worth surfacing as an
    overlap signal (stopwords and single letters excluded)."""
    return {
        word for word in _WORD.findall(text.lower()) if len(word) > 2 and word not in _STOPWORDS
    }


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass(frozen=True)
class MatchResult:
    """One ranked job, with the explainability PLAN.md's Phase 2 asks for."""

    job: Job
    score: float
    matched_keywords: list[str]


def rank_jobs(
    jobs: list[Job],
    resume_embedding: list[float],
    resume_keywords: set[str],
    *,
    limit: int = 20,
) -> list[MatchResult]:
    """Rank ``jobs`` (must all have a non-null ``embedding``) against a
    resume's embedding, highest cosine similarity first."""
    results = []
    for job in jobs:
        if job.embedding is None:
            continue
        score = cosine_similarity(list(job.embedding), resume_embedding)
        job_text = f"{job.title} {job.description or ''}"
        matched = sorted(resume_keywords & extract_keywords(job_text))
        results.append(MatchResult(job=job, score=score, matched_keywords=matched))
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]
