"""LocalEmbeddingProvider tests, against an injected fake encoder rather
than downloading real model weights (same pattern as HiringCafeSource's
injected httpx client)."""

from __future__ import annotations

from jobscout.embeddings.local import LocalEmbeddingProvider


class FakeEncoder:
    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 0.0, 1.0] for text in texts]


def test_embed_returns_one_vector_per_text() -> None:
    provider = LocalEmbeddingProvider(FakeEncoder())
    vectors = provider.embed(["hi", "hello there"])
    assert vectors == [[2.0, 0.0, 1.0], [11.0, 0.0, 1.0]]


def test_embed_empty_list_returns_empty_list() -> None:
    provider = LocalEmbeddingProvider(FakeEncoder())
    assert provider.embed([]) == []
