"""Shared fixtures.

Pipeline/query tests run against in-memory sqlite (via aiosqlite) rather
than Postgres: they exercise dedupe and query logic, not
Postgres-specific behavior, so this keeps the suite fast and Docker-free
(the pattern the existing hiring.cafe tests already use, substituting a
real embedded DB for a mocked HTTP transport).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from jobscout.db import make_session_factory
from jobscout.models import Base


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield make_session_factory(engine)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s
