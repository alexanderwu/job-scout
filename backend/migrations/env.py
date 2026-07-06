"""Alembic environment: wires migrations to the app's models & settings.

Two deliberate choices:

- **URL comes from Settings**, not alembic.ini — one source of
  connection truth. Alembic runs *sync* (its design); psycopg 3's
  dialect covers sync and async alike, so we reuse the same URL
  rewrite as the app (db.sqlalchemy_url).
- **target_metadata = Base.metadata** enables ``alembic revision
  --autogenerate``: Alembic diffs the models against the live schema
  and drafts the migration. Drafts are reviewed and edited by hand —
  autogenerate misses things (server defaults, some index changes) and
  every migration here is committed as reviewed code, not trusted
  output.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from jobscout.config import get_settings
from jobscout.db import sqlalchemy_url
from jobscout.models import Base

config = context.config
target_metadata = Base.metadata

# Respect a URL that was already set programmatically (the test suite
# migrates a throwaway database this way); otherwise use Settings.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", sqlalchemy_url(get_settings().database_url))


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of a DB (``alembic upgrade --sql``).

    Useful for reviewing exactly what will run, or applying by hand in
    an environment where Alembic can't connect.
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
