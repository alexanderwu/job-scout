"""Ranking and explainability tests (PLAN.md Phase 2), plus skill-gap
and tailoring-suggestions tests (PLAN.md Phase 4)."""

from __future__ import annotations

from jobscout.matching import (
    aggregate_keyword_frequencies,
    cosine_similarity,
    extract_keywords,
    rank_jobs,
    skill_gap,
    tailoring_suggestions,
)
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


def test_aggregate_keyword_frequencies_counts_documents_not_mentions() -> None:
    repeats_python = make_job(
        title="Python Engineer", description="Python, Python, Python everywhere."
    )
    mentions_python_once = make_job(title="Backend Engineer", description="Uses Python and Go.")
    jobs = [repeats_python, mentions_python_once]

    counts = aggregate_keyword_frequencies(jobs)

    assert counts["python"] == 2  # one increment per job, not per mention
    assert counts["engineer"] == 2


def test_skill_gap_partitions_missing_and_matched_sorted_by_frequency() -> None:
    jobs = [
        make_job(title="Job A", description="Python and Kubernetes experience required."),
        make_job(title="Job B", description="Python and Docker experience required."),
        make_job(title="Job C", description="Python required."),
    ]
    resume_keywords = extract_keywords("Experienced Python engineer.")

    result = skill_gap(resume_keywords, jobs, top_n=10)

    assert result.postings_considered == 3
    assert result.matched_keywords[0] == ("python", 3)
    missing_keywords = [keyword for keyword, _ in result.missing_keywords]
    assert "kubernetes" in missing_keywords
    assert "docker" in missing_keywords
    assert "python" not in missing_keywords


def test_tailoring_suggestions_is_the_complement_of_matched_keywords() -> None:
    job = make_job(
        title="Senior Python Engineer",
        description="Build data pipelines with Python and SQL.",
        embedding=[1.0, 0.0, 0.0],
    )
    resume_keywords = extract_keywords("Experienced Python engineer, data pipelines, SQL.")

    ranked = rank_jobs([job], [1.0, 0.0, 0.0], resume_keywords, limit=1)
    suggestions = tailoring_suggestions(resume_keywords, job)

    assert suggestions.matched_keywords == ranked[0].matched_keywords
    assert "build" in suggestions.missing_keywords
    assert "python" not in suggestions.missing_keywords
