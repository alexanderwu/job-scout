"""Async SQLAlchemy engine/session setup.

``DATABASE_URL`` is read from the environment at call time rather than
threaded through every call site; tests and Alembic pass an explicit URL
instead (sqlite for tests, so pipeline/query logic runs without Docker).
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def database_url() -> str:
    return os.environ["DATABASE_URL"]


def make_engine(url: str | None = None) -> AsyncEngine:
    return create_async_engine(url or database_url())


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
