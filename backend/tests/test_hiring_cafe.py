"""hiring.cafe adapter tests against recorded-style fixtures.

The fixture mirrors our *assumed* response shape (see the warning in
``jobscout.sources.hiring_cafe``). ``httpx.MockTransport`` lets the real
client code build and send real requests without any network — so these
tests exercise request construction, pagination, and parsing, while the
live API shape still needs one manual confirmation pass.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from jobscout.sources.hiring_cafe import SEARCH_URL, HiringCafeSource
from jobscout.sources.throttle import RateLimiter

FIXTURES = Path(__file__).parent / "fixtures"
PAGE1 = json.loads((FIXTURES / "hiring_cafe_page1.json").read_text())
EMPTY_PAGE: dict[str, Any] = {"results": [], "total": 2}


def make_client(pages: dict[int, dict[str, Any]]) -> tuple[httpx.AsyncClient, list[dict[str, Any]]]:
    """Client whose transport serves `pages` by page number, recording payloads."""
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        assert str(request.url) == SEARCH_URL
        return httpx.Response(200, json=pages.get(payload["page"], EMPTY_PAGE))

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), requests


def instant_limiter() -> RateLimiter:
    return RateLimiter(0)


async def test_parses_postings_from_fixture() -> None:
    client, _ = make_client({0: PAGE1})
    source = HiringCafeSource(client, limiter=instant_limiter())

    postings = [p async for p in source.fetch()]

    assert len(postings) == 2
    first = postings[0]
    assert first.source == "hiring_cafe"
    assert first.external_id == "job-abc123"
    assert first.title == "Senior Data Engineer"
    assert first.company == "Acme Corp"
    assert first.location == "San Francisco, CA"
    assert first.posted_at is not None
    assert first.posted_at.year == 2026
    # The full payload survives untouched for Phase 1 re-normalization.
    assert first.raw == PAGE1["results"][0]

    second = postings[1]
    assert second.location is None
    assert second.posted_at is None


async def test_paginates_until_empty_page() -> None:
    client, requests = make_client({0: PAGE1, 1: PAGE1})
    source = HiringCafeSource(client, limiter=instant_limiter())

    postings = [p async for p in source.fetch()]

    assert len(postings) == 4
    assert [r["page"] for r in requests] == [0, 1, 2]


async def test_max_pages_caps_requests() -> None:
    client, requests = make_client({0: PAGE1, 1: PAGE1})
    source = HiringCafeSource(client, max_pages=1, limiter=instant_limiter())

    postings = [p async for p in source.fetch()]

    assert len(postings) == 2
    assert [r["page"] for r in requests] == [0]


async def test_http_error_raises_instead_of_yielding_nothing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    source = HiringCafeSource(client, limiter=instant_limiter())

    with pytest.raises(httpx.HTTPStatusError):
        _ = [p async for p in source.fetch()]


async def test_missing_salary_fields_become_none() -> None:
    client, _ = make_client({0: PAGE1})
    source = HiringCafeSource(client, limiter=instant_limiter())

    postings = [p async for p in source.fetch()]

    assert postings[0].salary_min is None
    assert postings[0].salary_max is None
    assert postings[0].salary_currency is None


async def test_salary_fields_extracted_when_present() -> None:
    item = json.loads(json.dumps(PAGE1["results"][0]))
    item["v5_processed_job_data"]["yearly_min_compensation"] = 120000
    item["v5_processed_job_data"]["yearly_max_compensation"] = 160000
    item["v5_processed_job_data"]["salary_currency"] = "USD"
    client, _ = make_client({0: {"results": [item]}})
    source = HiringCafeSource(client, limiter=instant_limiter())

    [posting] = [p async for p in source.fetch()]

    assert posting.salary_min == 120000
    assert posting.salary_max == 160000
    assert posting.salary_currency == "USD"


async def test_search_state_is_sent_in_payload() -> None:
    client, requests = make_client({})
    state = {"searchQuery": "data engineer"}
    source = HiringCafeSource(client, search_state=state, limiter=instant_limiter())

    _ = [p async for p in source.fetch()]

    assert requests[0]["searchState"] == state
    assert requests[0]["size"] == 40
