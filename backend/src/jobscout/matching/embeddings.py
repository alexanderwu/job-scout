"""Embedding providers — the swappable heart of matching.

The contract (:class:`EmbeddingProvider`) is tiny on purpose: turn
texts into fixed-size vectors, synchronously. Sync because the default
implementation is CPU-bound local inference where async buys nothing;
async callers (the API) wrap calls in ``asyncio.to_thread`` instead of
every provider carrying event-loop plumbing.

The one rule that makes or breaks matching: **query and corpus vectors
must come from the same model** (PLAN.md rejects the hybrid
local-corpus/API-resume option for exactly this reason — two models =
two vector spaces = meaningless distances). That's why:

- each provider exposes a ``signature`` (provider + model name),
- every stored job embedding records the signature it was made with,
- search filters on the *current* signature, so a half-re-embedded
  corpus degrades to fewer results, never to nonsense rankings.

Providers:

- :class:`SentenceTransformerProvider` — the default (PLAN.md
  "local-first ML"): free, offline, no API key. Heavy deps (torch), so
  it lives in the optional ``ml`` dependency group and is imported
  lazily.
- :class:`HashingProvider` — feature-hashed bag-of-words. Zero
  dependencies, deterministic, instant. This is a *real* (if
  old-school) IR baseline — pure lexical overlap — not a mock: useful
  for tests, CI, low-RAM machines, and as an honest quality floor to
  compare the neural model against. It shares dimensionality with
  MiniLM (384) so both fit the same pgvector column.

Changing to a model with a different dimension means a schema change
(the pgvector column is fixed-width) — that's a deliberate speed bump:
re-embedding the whole corpus should be a decision, not a side effect.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

from jobscout.config import Settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2's width; HashingProvider matches it.


class EmbeddingProvider(ABC):
    name: ClassVar[str]
    dimension: int = EMBEDDING_DIM

    @property
    @abstractmethod
    def signature(self) -> str:
        """Identifies the vector space, e.g. ``st:all-MiniLM-L6-v2``.

        Stored with every embedding; two vectors are only comparable
        when their signatures match.
        """

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """One unit-length vector per input text."""


_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.]*")


class HashingProvider(EmbeddingProvider):
    """Feature hashing ("the hashing trick"): token -> stable bucket.

    Each token is hashed to one of ``dimension`` buckets with a ±1 sign
    (the sign trick keeps colliding tokens from only ever adding up, so
    collisions partially cancel instead of biasing counts); the vector
    is L2-normalized so cosine distance behaves. Same scheme as
    scikit-learn's HashingVectorizer, minus the dependency.

    blake2b instead of Python's ``hash()``: builtin string hashing is
    salted per process (PYTHONHASHSEED), which would give every process
    its own incompatible vector space — the exact bug the signature
    mechanism exists to prevent.
    """

    name = "hashing"

    @property
    def signature(self) -> str:
        return f"hashing:v1:{self.dimension}"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        for token in _TOKEN_RE.findall(text.casefold()):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]


class SentenceTransformerProvider(EmbeddingProvider):
    """Local neural embeddings via sentence-transformers (the default).

    The model (~90 MB) downloads from Hugging Face on first use and is
    cached; after that everything runs offline — resume text never
    leaves the machine.
    """

    name = "sentence-transformers"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model: SentenceTransformer | None = None

    @property
    def signature(self) -> str:
        return f"st:{self._model_name}"

    def _load(self) -> SentenceTransformer:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - exercised via message test
                raise MissingMLDependenciesError() from exc
            self._model = SentenceTransformer(self._model_name)
            self.dimension = self._model.get_sentence_embedding_dimension() or EMBEDDING_DIM
        return self._model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._load().encode(
            list(texts),
            normalize_embeddings=True,  # unit length -> cosine == dot product
            show_progress_bar=False,
        )
        return [list(map(float, v)) for v in vectors]


class MissingMLDependenciesError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "sentence-transformers is not installed. Either install the ml "
            "dependency group (`just install`, or `uv sync --group ml` in "
            "backend/) or set EMBEDDING_PROVIDER=hashing in .env to use the "
            "dependency-free lexical provider."
        )


def provider_from_settings(settings: Settings) -> EmbeddingProvider:
    """The one place config strings become provider instances."""
    if settings.embedding_provider == "hashing":
        return HashingProvider()
    if settings.embedding_provider == "sentence-transformers":
        return SentenceTransformerProvider(settings.embedding_model)
    raise ValueError(
        f"unknown EMBEDDING_PROVIDER {settings.embedding_provider!r}; "
        "expected 'sentence-transformers' or 'hashing'"
    )
