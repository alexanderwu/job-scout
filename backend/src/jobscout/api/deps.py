"""FastAPI dependencies reading the per-app resources ``app.py``'s
lifespan builds once at startup (DB session factory, embedding
provider, LLM provider) rather than reconstructing them per request."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.embeddings.base import EmbeddingProvider
from jobscout.llm.base import LLMProvider


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


def get_embedding_provider(request: Request) -> EmbeddingProvider:
    provider: EmbeddingProvider = request.app.state.embedding_provider
    return provider


def get_llm_provider(request: Request) -> LLMProvider:
    provider: LLMProvider = request.app.state.llm_provider
    return provider
