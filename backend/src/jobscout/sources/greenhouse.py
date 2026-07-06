"""Greenhouse job-board adapter — the first *official* source.

Greenhouse publishes a documented, ToS-safe, no-auth Job Board API per
company ("board token"):

    GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true

Docs: https://developers.greenhouse.io/job-board.html

Contrast with hiring_cafe.py: that adapter reverse-engineers an internal
endpoint and carries a warning banner; this one implements a published
contract. Having both proves the JobSource interface fits either kind of
source (PLAN.md guiding decision #2).

The endpoint returns *all* open jobs for a board in one response (no
pagination), so ``fetch()`` is a single GET. One adapter instance = one
company's board; ingestion runs one instance per configured board.
"""

from __future__ import annotations

import html as html_module
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx

from jobscout.normalize import html_to_text
from jobscout.sources.base import JobSource, RawPosting

BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"


class GreenhouseSource(JobSource):
    name = "greenhouse"

    def __init__(
        self,
        http: httpx.AsyncClient,
        board: str,
        *,
        company: str | None = None,
    ) -> None:
        """``board`` is the Greenhouse board token, e.g. ``"anthropic"``.

        ``company`` overrides the display name; by default the board
        token is title-cased ("anthropic" -> "Anthropic"), which is
        right often enough and always overridable in config.
        """
        self._http = http
        self._board = board
        self._company = company or board.replace("-", " ").title()

    async def fetch(self) -> AsyncIterator[RawPosting]:
        # content=true inlines the job description; without it we'd need
        # one extra request per job.
        response = await self._http.get(
            BOARD_URL.format(board=self._board), params={"content": "true"}
        )
        response.raise_for_status()
        fetched_at = datetime.now(tz=UTC)
        for item in response.json().get("jobs", []):
            yield self._to_posting(item, fetched_at)

    def _to_posting(self, item: dict[str, Any], fetched_at: datetime) -> RawPosting:
        location = (item.get("location") or {}).get("name")
        # Greenhouse double-escapes `content` (HTML entities encoding
        # HTML): html_to_text with convert_charrefs handles the outer
        # layer, so unescape-then-strip gives clean text.
        content = item.get("content") or ""
        description = html_to_text(html_module.unescape(content)) or None
        return RawPosting(
            source=self.name,
            external_id=str(item.get("id", "")),
            url=item.get("absolute_url") or "",
            title=item.get("title") or "",
            company=self._company,
            location=location,
            posted_at=_parse_datetime(item.get("first_published") or item.get("updated_at")),
            fetched_at=fetched_at,
            description=description,
            raw=item,
        )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
