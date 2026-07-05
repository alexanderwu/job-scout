"""FastAPI dependencies reading the per-app resources ``app.py``'s
lifespan builds once at startup (DB session factory, embedding
provider, LLM provider) rather than reconstructing them per request.

Also the shared "load or 404" dependencies (``get_profile_or_404``,
``get_job_or_404``) used by every Phase 4 route that requires an
existing profile or job — a single place for that check instead of
each route re-raising the same ``HTTPException`` inline.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from jobscout.embeddings.base import EmbeddingProvider
from jobscout.llm.base import LLMProvider
from jobscout.models import Job, Profile
from jobscout.queries import get_profile


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


async def get_profile_or_404(session: AsyncSession = Depends(get_session)) -> Profile:
    profile = await get_profile(session)
    if profile is None:
        raise HTTPException(status_code=404, detail="No profile uploaded yet")
    return profile


async def get_job_or_404(job_id: int, session: AsyncSession = Depends(get_session)) -> Job:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
