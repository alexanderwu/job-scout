"""The LLM-provider contract (PLAN.md Phase 4, guiding decision #3).

Mirrors ``embeddings.base.EmbeddingProvider``: callers (cover-letter
generation) build the prompt and never talk to a specific backend
directly, so swapping the local Ollama model for a paid API later means
writing one more implementation of this, not touching any caller.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Interface every text-generation backend implements.

    ``generate`` is async — unlike ``EmbeddingProvider.embed``, every
    concrete implementation talks to a model over the network (Ollama's
    HTTP API today, a paid API's HTTP API if one is added later), and
    the rest of this codebase's network-calling code (``HiringCafeSource``)
    is async for the same reason.
    """

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Generate text from a single prompt string."""
