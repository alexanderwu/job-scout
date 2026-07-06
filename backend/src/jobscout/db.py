"""Database engine and session factories.

One engine per process, created lazily. The app uses SQLAlchemy's
*async* engine (psycopg 3 driver) because everything around it —
source adapters, the ingestion pipeline, FastAPI later — is async;
mixing a blocking DB into an async pipeline would stall the event loop
exactly where we wait the most. Alembic migrations and the RQ worker
entrypoint are the two sync corners, and they get there via
``async``-to-sync bridges (Alembic has its own sync engine in
``migrations/env.py``; the worker wraps the pipeline in
``asyncio.run``) rather than a parallel sync codepath to maintain.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from jobscout.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def sqlalchemy_url(database_url: str) -> str:
    """Rewrite a plain ``postgresql://`` URL to name the psycopg 3 driver.

    ``.env`` keeps the driver-agnostic form (it's also what ``psql``
    understands); the ``+psycopg`` suffix is a SQLAlchemy detail that
    belongs here, not in user-facing config. Without it SQLAlchemy
    assumes the legacy psycopg2 package, which isn't installed. The
    psycopg 3 dialect serves both sync (Alembic) and async (the app)
    engines — one driver dependency for both worlds.
    """
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(sqlalchemy_url(get_settings().database_url))
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        # expire_on_commit=False: we read attributes of ORM objects after
        # commit (e.g. to print ingest stats); the default would force a
        # surprising re-SELECT for each access.
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """A session that commits on success and rolls back on error."""
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
