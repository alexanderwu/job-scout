"""HashingProvider tests — the properties any EmbeddingProvider must hold.

The neural provider can't run in CI (model download, torch); these
tests pin down the *contract* on the dependency-free implementation:
determinism, unit length, and "similar text is closer than dissimilar
text" — which for the hashing provider means lexical overlap.
"""

import math

import pytest

from jobscout.config import Settings
from jobscout.matching.embeddings import (
    EMBEDDING_DIM,
    HashingProvider,
    SentenceTransformerProvider,
    provider_from_settings,
)


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_deterministic_across_instances() -> None:
    # Two separate instances (as in: two separate processes) must agree,
    # or stored vectors would be garbage next run. This is why blake2b,
    # not the salted builtin hash().
    v1 = HashingProvider().embed(["senior python engineer"])[0]
    v2 = HashingProvider().embed(["senior python engineer"])[0]
    assert v1 == v2


def test_unit_length_and_dimension() -> None:
    (vec,) = HashingProvider().embed(["data engineering with airflow and dbt"])
    assert len(vec) == EMBEDDING_DIM
    assert math.isclose(sum(v * v for v in vec), 1.0, rel_tol=1e-9)


def test_empty_text_is_zero_vector_not_crash() -> None:
    (vec,) = HashingProvider().embed([""])
    assert all(v == 0.0 for v in vec)


def test_lexical_similarity_orders_sensibly() -> None:
    provider = HashingProvider()
    resume, data_job, design_job = provider.embed(
        [
            "Python data engineer: SQL, Airflow, Spark pipelines",
            "Hiring a data engineer to build SQL and Airflow pipelines in Python",
            "Visual designer crafting brand identities in Figma",
        ]
    )
    assert cosine(resume, data_job) > cosine(resume, design_job)


def test_signatures_distinguish_vector_spaces() -> None:
    assert HashingProvider().signature != SentenceTransformerProvider().signature
    # and the ST signature carries the model name, so switching models
    # also switches spaces:
    assert SentenceTransformerProvider("all-MiniLM-L6-v2").signature != (
        SentenceTransformerProvider("all-mpnet-base-v2").signature
    )


def test_provider_from_settings_selects_and_rejects() -> None:
    assert isinstance(
        provider_from_settings(Settings(embedding_provider="hashing")), HashingProvider
    )
    assert isinstance(
        provider_from_settings(Settings(embedding_provider="sentence-transformers")),
        SentenceTransformerProvider,
    )
    with pytest.raises(ValueError, match="EMBEDDING_PROVIDER"):
        provider_from_settings(Settings(embedding_provider="nope"))
