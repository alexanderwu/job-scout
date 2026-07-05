"""LLM (text-generation) providers.

Text generation runs on a free local model by default (PLAN.md guiding
decision #3), behind :class:`~jobscout.llm.base.LLMProvider` so a paid
API can be swapped in per-feature without touching callers.

``LocalOllamaProvider`` (in ``jobscout.llm.ollama``) is deliberately not
re-exported here, mirroring ``jobscout.embeddings``'s treatment of
``LocalEmbeddingProvider`` — keep the two provider packages' import
shape consistent even though Ollama itself has no heavy import cost.
Import it directly where it's used.
"""

from jobscout.llm.base import LLMProvider

__all__ = ["LLMProvider"]
