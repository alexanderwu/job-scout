"""hiring.cafe adapter — the primary ingestion source (PLAN.md decision #2).

.. warning::
    hiring.cafe's API is **internal and undocumented**. The endpoint,
    request payload, and response field paths below are a best-effort
    reconstruction and are exercised only against recorded fixtures in
    tests — they must be confirmed against the live API (along with rate
    limits and ToS) before Phase 1 turns on scheduled ingestion. That
    verification is the remaining human step of Phase 0. Everything
    likely to be wrong is isolated in ``SEARCH_URL``, ``_payload()`` and
    ``_to_posting()`` so corrections stay local.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx

from jobscout.sources.base import JobSource, RawPosting
from jobscout.sources.throttle import RateLimiter

SEARCH_URL = "https://hiring.cafe/api/search-jobs"

# Self-imposed politeness floor between page requests; see throttle.py
# for why we throttle an API that never published a limit.
DEFAULT_MIN_INTERVAL = 2.0

DEFAULT_PAGE_SIZE = 40


class HiringCafeSource(JobSource):
    """Pages through hiring.cafe's internal search endpoint.

    The ``httpx.AsyncClient`` is injected rather than created here so
    the caller controls its lifecycle (one client per ingestion run,
    connection pooling shared across sources) and tests can pass a
    client wired to a mock transport — no monkeypatching.
    """

    name = "hiring_cafe"

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        search_state: dict[str, Any] | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._http = http
        self._search_state = search_state or {}
        self._page_size = page_size
        self._max_pages = max_pages
        self._limiter = limiter if limiter is not None else RateLimiter(DEFAULT_MIN_INTERVAL)

    async def fetch(self) -> AsyncIterator[RawPosting]:
        page = 0
        while self._max_pages is None or page < self._max_pages:
            await self._limiter.wait()
            response = await self._http.post(SEARCH_URL, json=self._payload(page))
            response.raise_for_status()
            results = response.json().get("results", [])
            if not results:
                break
            fetched_at = datetime.now(tz=UTC)
            for item in results:
                yield self._to_posting(item, fetched_at)
            page += 1

    def _payload(self, page: int) -> dict[str, Any]:
        return {
            "size": self._page_size,
            "page": page,
            "searchState": self._search_state,
        }

    def _to_posting(self, item: dict[str, Any], fetched_at: datetime) -> RawPosting:
        # Tolerant field extraction: missing optional fields become None
        # instead of a crash, but a posting with no usable id or title is
        # a schema surprise worth failing loudly on (pydantic raises).
        info = item.get("job_information") or {}
        processed = item.get("v5_processed_job_data") or {}
        salary_min, salary_max, salary_currency = _extract_salary(processed)
        return RawPosting(
            source=self.name,
            external_id=str(item.get("id", "")),
            url=item.get("apply_url") or item.get("url") or "",
            title=info.get("title") or "",
            company=processed.get("company_name"),
            location=processed.get("formatted_workplace_location"),
            description=info.get("description"),
            posted_at=_parse_datetime(processed.get("estimated_publish_date")),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=salary_currency,
            fetched_at=fetched_at,
            raw=item,
        )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _extract_salary(processed: dict[str, Any]) -> tuple[int | None, int | None, str | None]:
    # Best-effort, like every other field pulled out of ``processed`` in
    # this adapter (see the module warning): the exact key names below
    # are an educated guess at hiring.cafe's annualized-compensation
    # fields, unconfirmed against the live API. A wrong guess just means
    # Phase 5 salary insights stay empty, not a crash.
    return (
        _to_int(processed.get("yearly_min_compensation")),
        _to_int(processed.get("yearly_max_compensation")),
        processed.get("salary_currency"),
    )


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
