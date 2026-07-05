"""The FastAPI app factory (PLAN.md Phase 3).

``create_app`` takes the session factory and embedding provider as
optional overrides — the same constructor-injection pattern
``LocalEmbeddingProvider`` and ``HiringCafeSource`` already use for
tests — so ``tests/test_api.py`` can wire in the sqlite fixture and a
fake provider directly, instead of a real Postgres DB and a downloaded
model.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jobscout.api.routes import feed, jobs, matches, profile, saved
from jobscout.db import make_engine, make_session_factory
from jobscout.embeddings.base import EmbeddingProvider
from jobscout.embeddings.local import LocalEmbeddingProvider


def create_app(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> FastAPI:
    owns_engine = session_factory is None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine() if owns_engine else None
        app.state.session_factory = make_session_factory(engine) if engine else session_factory
        app.state.embedding_provider = embedding_provider or LocalEmbeddingProvider()
        try:
            yield
        finally:
            if engine is not None:
                await engine.dispose()

    app = FastAPI(title="Job Scout API", lifespan=lifespan)

    allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(jobs.router, prefix="/api")
    app.include_router(profile.router, prefix="/api")
    app.include_router(matches.router, prefix="/api")
    app.include_router(feed.router, prefix="/api")
    app.include_router(saved.router, prefix="/api")
    return app


app = create_app()
