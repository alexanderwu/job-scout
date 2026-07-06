"""Application settings, loaded from the environment (and ``.env``).

Why pydantic-settings instead of ``os.environ`` reads scattered around:
every knob is declared once, typed, defaulted, and validated at startup —
a typo'd env var fails loudly here instead of surfacing as a weird
``KeyError`` deep in a worker. The alternatives:

- plain ``os.environ.get()`` calls: zero deps, but no single place to see
  every setting, no types, and silent fallbacks hide misconfiguration.
- dynaconf/environs: more features (layered config files, secrets
  backends) than a single-developer tool needs.

Settings are read once into a module-level singleton via
:func:`get_settings`; tests construct their own ``Settings`` instances
directly instead of monkeypatching the environment.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every runtime knob Job Scout reads, in one place.

    Defaults match ``docker-compose.yml`` / ``.env.example`` so a fresh
    clone works with zero configuration beyond ``docker compose up``.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://jobscout:jobscout@localhost:5432/jobscout"
    redis_url: str = "redis://localhost:6379/0"

    # --- ingestion sources -------------------------------------------------
    # Which Greenhouse boards / Lever sites to pull, as comma-separated
    # slugs (e.g. GREENHOUSE_BOARDS="anthropic,stripe"). Comma-separated
    # strings instead of JSON lists because that's what people naturally
    # type into a .env file.
    greenhouse_boards: list[str] = []
    lever_sites: list[str] = []

    # hiring.cafe is off by default: its API is internal/undocumented and
    # the adapter is only fixture-verified (see sources/hiring_cafe.py).
    # Flip on once you've confirmed the live API shape manually.
    hiring_cafe_enabled: bool = False

    # How often the scheduled worker re-runs ingestion (see schedules.py).
    ingest_interval_minutes: int = 30

    # --- matching (Phase 2) ------------------------------------------------
    # 'sentence-transformers' (default; local neural model, needs the ml
    # dependency group) or 'hashing' (dependency-free lexical baseline).
    # See matching/embeddings.py for the trade-off and the one hard rule:
    # resume and job vectors must come from the same provider+model.
    embedding_provider: str = "sentence-transformers"
    embedding_model: str = "all-MiniLM-L6-v2"

    @field_validator("greenhouse_boards", "lever_sites", mode="before")
    @classmethod
    def _split_commas(cls, value: object) -> object:
        """Allow ``FOO=a,b,c`` in .env for list fields."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide settings instance (cached after first read)."""
    return Settings()
