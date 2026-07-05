"""Embedding providers.

Embeddings and text generation run on free local models by default (PLAN.md
guiding decision #3), behind :class:`~jobscout.embeddings.base.EmbeddingProvider`
so a paid API can be swapped in per-feature without touching callers.

``LocalEmbeddingProvider`` (in ``jobscout.embeddings.local``) is deliberately
*not* re-exported here: importing it pulls in ``sentence-transformers`` and
``torch``, which is slow and unnecessary for code (like ``jobscout.models``)
that only needs ``EMBEDDING_DIM``. Import it directly where it's used.
"""

from jobscout.embeddings.base import EMBEDDING_DIM, EmbeddingProvider

__all__ = ["EMBEDDING_DIM", "EmbeddingProvider"]
