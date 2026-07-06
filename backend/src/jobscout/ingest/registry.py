"""Build the list of configured source adapters from Settings.

This is the *only* place that knows which concrete adapters exist —
the pipeline takes ``Sequence[JobSource]`` and the CLI/worker just call
:func:`configured_sources`. Adding a source to the product = writing
the adapter + registering it here; nothing else changes.
"""

from __future__ import annotations

import httpx

from jobscout.config import Settings
from jobscout.sources.base import JobSource
from jobscout.sources.greenhouse import GreenhouseSource
from jobscout.sources.hiring_cafe import HiringCafeSource
from jobscout.sources.lever import LeverSource


def configured_sources(settings: Settings, http: httpx.AsyncClient) -> list[JobSource]:
    """One adapter instance per configured board/site.

    The single shared ``httpx.AsyncClient`` (created by the caller, who
    owns its lifecycle) gives all sources one connection pool and one
    place to set timeouts/headers — the injection pattern established
    in hiring_cafe.py.
    """
    sources: list[JobSource] = []
    sources.extend(GreenhouseSource(http, board) for board in settings.greenhouse_boards)
    sources.extend(LeverSource(http, site) for site in settings.lever_sites)
    if settings.hiring_cafe_enabled:
        sources.append(HiringCafeSource(http))
    return sources


def default_http_client() -> httpx.AsyncClient:
    """The client ingestion runs use: generous timeout, honest UA."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        headers={"User-Agent": "jobscout/0.1 (personal job-search tool)"},
        follow_redirects=True,
    )
