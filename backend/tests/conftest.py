"""Shared fixtures — most importantly, a real Postgres for pipeline tests.

Philosophy: dedupe behavior lives in SQL queries against real indexes
and constraints, so the pipeline tests run against an actual Postgres
(the same pgvector image Compose runs), not SQLite or mocks. SQLite
would silently diverge (no JSONB, different type coercion, and no
pgvector at all come Phase 2); mocking the session would test nothing
but the mock. The cost — needing a database — is paid once in
docker-compose/CI and bought back as tests that catch real bugs.

Mechanics:
- ``TEST_DATABASE_URL`` names the throwaway DB; default derives from
  the dev URL by appending ``_test`` (never the dev DB itself — tests
  TRUNCATE tables).
- If it's unreachable, DB tests *skip* with instructions instead of
  erroring: unit tests stay runnable without infra. CI always has the
  service, so nothing silently skips where it matters.
- The schema comes from ``alembic upgrade head``, not
  ``create_all()`` — every test run also proves the migration chain
  builds the schema the models expect.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import psycopg
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from jobscout.config import Settings
from jobscout.db import sqlalchemy_url

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _test_database_url() -> str:
    if explicit := os.environ.get("TEST_DATABASE_URL"):
        return explicit
    dev_url = make_url(Settings().database_url)
    return dev_url.set(database=f"{dev_url.database}_test").render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def database_url() -> str:
    """Reachable, migrated test database URL — or a skip."""
    url = _test_database_url()
    try:
        with psycopg.connect(url, connect_timeout=3):
            pass
    except psycopg.OperationalError as exc:
        pytest.skip(
            f"no test database at {url!r} ({exc}); "
            "run `docker compose up -d` and create the *_test database, "
            "or set TEST_DATABASE_URL"
        )
    cfg = AlembicConfig(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "migrations"))
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url(url))
    command.upgrade(cfg, "head")
    return url


@pytest.fixture
async def db_session(database_url: str) -> AsyncIterator[AsyncSession]:
    """A session on a *clean* schema: tables truncated per test.

    Truncation over per-test transactions-with-rollback: the pipeline
    commits internally (batching is part of its contract), so the
    rollback trick would fight the code under test.
    """
    engine = create_async_engine(sqlalchemy_url(database_url))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text("TRUNCATE jobs, postings RESTART IDENTITY CASCADE"))
        await session.commit()
        yield session
    await engine.dispose()
