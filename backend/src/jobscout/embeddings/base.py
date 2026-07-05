"""The embedding-provider contract (PLAN.md Phase 2, guiding decision #3).

Job description and resume/profile text must be embedded by the *same*
model — PLAN.md's embedding-model trade-off table rejects mixing providers
for exactly this reason ("query and corpus embeddings must share a
model"). Routing both through one ``EmbeddingProvider`` interface makes
that invariant structural rather than a convention callers have to
remember.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

EMBEDDING_DIM = 384
"""Output dimension of the default local model (``all-MiniLM-L6-v2``).

Fixed at the module level (rather than read off a provider instance)
because it's also needed by ``jobscout.models`` to size the ``pgvector``
column, before any provider is constructed. Swapping in a provider with a
different dimension requires a migration to resize the column to match.
"""


class EmbeddingProvider(ABC):
    """Interface every embedding backend implements.

    Swapping local sentence-transformers for a paid API (Claude, OpenAI,
    Voyage) means writing one implementation of this — callers (the embed
    batch job, resume matching) never change.
    """

    dimension: ClassVar[int] = EMBEDDING_DIM

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, returning one vector per input text,
        in the same order."""
