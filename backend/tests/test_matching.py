"""Ranking and explainability tests (PLAN.md Phase 2)."""

from __future__ import annotations

from jobscout.matching import cosine_similarity, extract_keywords, rank_jobs
from jobscout.models import Job


def make_job(**overrides: object) -> Job:
    defaults: dict[str, object] = {
        "normalized_title": "data engineer",
        "canonical_url": "https://example.com/1",
        "title": "Data Engineer",
        "first_seen": None,
        "last_seen": None,
    }
    return Job(**{**defaults, **overrides})


def test_cosine_similarity_identical_vectors_is_one() -> None:
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0


def test_cosine_similarity_orthogonal_vectors_is_zero() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_zero_vector_is_zero_not_nan() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0


def test_extract_keywords_drops_stopwords_and_short_words() -> None:
    keywords = extract_keywords("We are looking for a Python engineer to build data pipelines.")
    assert "python" in keywords
    assert "pipelines" in keywords
    assert "we" not in keywords
    assert "for" not in keywords
    assert "a" not in keywords


def test_rank_jobs_orders_by_similarity_and_reports_matched_keywords() -> None:
    close = make_job(
        title="Senior Python Engineer",
        description="Build data pipelines with Python and SQL.",
        embedding=[1.0, 0.0, 0.0],
    )
    far = make_job(
        title="Marketing Manager",
        description="Run social media campaigns.",
        embedding=[0.0, 1.0, 0.0],
    )
    unembedded = make_job(title="No Embedding Yet", embedding=None)

    resume_embedding = [1.0, 0.0, 0.0]
    resume_keywords = extract_keywords("Experienced Python engineer, data pipelines, SQL.")

    results = rank_jobs([far, close, unembedded], resume_embedding, resume_keywords, limit=5)

    assert [r.job.title for r in results] == ["Senior Python Engineer", "Marketing Manager"]
    assert results[0].score > results[1].score
    assert set(results[0].matched_keywords) == {"python", "engineer", "data", "pipelines", "sql"}


def test_rank_jobs_respects_limit() -> None:
    jobs = [make_job(title=f"Job {i}", embedding=[float(i), 0.0]) for i in range(5)]
    results = rank_jobs(jobs, [1.0, 0.0], set(), limit=2)
    assert len(results) == 2
