"""Local sentence-transformers embedding provider (PLAN.md Phase 2 default).

Free, no API key, and resume text never leaves the machine. The
``sentence_transformers.SentenceTransformer`` model is injected rather than
constructed by name inside ``embed()`` so tests can pass a lightweight fake
with the same ``encode`` shape instead of downloading real model weights —
the same injection pattern ``HiringCafeSource`` uses for its HTTP client.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from jobscout.embeddings.base import EMBEDDING_DIM, EmbeddingProvider

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"


class _Encoder(Protocol):
    def encode(self, texts: list[str]) -> Iterable[Iterable[float]]: ...


class LocalEmbeddingProvider(EmbeddingProvider):
    """Embeds text with a local ``sentence-transformers`` model."""

    dimension = EMBEDDING_DIM

    def __init__(self, model: _Encoder | None = None, *, model_name: str = DEFAULT_MODEL_NAME):
        if model is None:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_name)
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(texts)
        return [[float(x) for x in vector] for vector in vectors]
