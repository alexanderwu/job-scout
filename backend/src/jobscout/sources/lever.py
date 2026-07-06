"""Lever job-board adapter — second official source.

Lever's documented, no-auth postings API per company ("site"):

    GET https://api.lever.co/v0/postings/{site}?mode=json&skip=N&limit=N

Docs: https://github.com/lever/postings-api

Unlike Greenhouse's all-in-one response, Lever supports ``skip``/
``limit`` paging, so ``fetch()`` loops pages — which exercises the
paginating side of the JobSource contract against an *official* API
(previously only the fixture-verified hiring.cafe adapter did paging).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx

from jobscout.normalize import html_to_text
from jobscout.sources.base import JobSource, RawPosting
from jobscout.sources.throttle import RateLimiter

POSTINGS_URL = "https://api.lever.co/v0/postings/{site}"

DEFAULT_PAGE_SIZE = 100
# Politeness between page requests; Lever documents no rate limit, so
# same self-imposed floor rationale as throttle.py.
DEFAULT_MIN_INTERVAL = 1.0


class LeverSource(JobSource):
    name = "lever"

    def __init__(
        self,
        http: httpx.AsyncClient,
        site: str,
        *,
        company: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._http = http
        self._site = site
        self._company = company or site.replace("-", " ").title()
        self._page_size = page_size
        self._limiter = limiter if limiter is not None else RateLimiter(DEFAULT_MIN_INTERVAL)

    async def fetch(self) -> AsyncIterator[RawPosting]:
        skip = 0
        while True:
            await self._limiter.wait()
            response = await self._http.get(
                POSTINGS_URL.format(site=self._site),
                params={"mode": "json", "skip": skip, "limit": self._page_size},
            )
            response.raise_for_status()
            items: list[dict[str, Any]] = response.json()
            fetched_at = datetime.now(tz=UTC)
            for item in items:
                yield self._to_posting(item, fetched_at)
            if len(items) < self._page_size:
                break  # short page = last page
            skip += self._page_size

    def _to_posting(self, item: dict[str, Any], fetched_at: datetime) -> RawPosting:
        categories = item.get("categories") or {}
        workplace = item.get("workplaceType")
        return RawPosting(
            source=self.name,
            external_id=str(item.get("id", "")),
            url=item.get("hostedUrl") or "",
            title=item.get("text") or "",
            company=self._company,
            location=categories.get("location"),
            posted_at=_from_epoch_ms(item.get("createdAt")),
            fetched_at=fetched_at,
            description=_description(item),
            # Lever's enum is on-site/hybrid/remote; only map what it
            # actually said — absence stays None (unknown), not False.
            remote=workplace == "remote" if workplace else None,
            raw=item,
        )


def _description(item: dict[str, Any]) -> str | None:
    """Assemble full text: intro + each list section (Requirements, ...).

    Lever splits a posting into ``description`` and ``lists``;
    ``descriptionPlain`` alone drops the requirement bullets, which are
    exactly what matching needs most.
    """
    parts: list[str] = []
    if plain := item.get("descriptionPlain"):
        parts.append(str(plain).strip())
    for section in item.get("lists") or []:
        if heading := section.get("text"):
            parts.append(str(heading))
        if content := section.get("content"):
            parts.append(html_to_text(str(content)))
    if additional := item.get("additionalPlain"):
        parts.append(str(additional).strip())
    return "\n".join(p for p in parts if p) or None


def _from_epoch_ms(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)
