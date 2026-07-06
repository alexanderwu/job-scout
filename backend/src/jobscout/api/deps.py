"""FastAPI dependencies: DB sessions and the embedding provider.

Why dependencies instead of module-level globals: every route
declaring ``session: SessionDep`` gets a per-request session that's
committed/closed for it, and — the part that pays off immediately —
tests override one function (``get_session``) to point the whole app
at the test database. Same for the provider: tests inject
HashingProvider without patching.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.db import session_scope
from jobscout.llm import LLMProvider
from jobscout.matching.embeddings import EmbeddingProvider


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session


def get_provider(request: Request) -> EmbeddingProvider:
    """The provider chosen at app startup (create_app), one per process.

    Providers can hold a loaded model — constructing per request would
    reload weights constantly.
    """
    provider: EmbeddingProvider = request.app.state.embedding_provider
    return provider


def get_llm(request: Request) -> LLMProvider | None:
    """None when LLM_PROVIDER=none — copilot features fall back to
    their deterministic/template paths (llm.py)."""
    llm: LLMProvider | None = request.app.state.llm
    return llm


SessionDep = Annotated[AsyncSession, Depends(get_session)]
ProviderDep = Annotated[EmbeddingProvider, Depends(get_provider)]
LLMDep = Annotated[LLMProvider | None, Depends(get_llm)]
