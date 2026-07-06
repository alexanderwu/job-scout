"""Lever adapter tests: parsing + skip/limit pagination against fixtures
mirroring the documented postings API (github.com/lever/postings-api)."""

import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from jobscout.sources.lever import LeverSource
from jobscout.sources.throttle import RateLimiter

FIXTURES = Path(__file__).parent / "fixtures"
PAGE1 = json.loads((FIXTURES / "lever_page1.json").read_text())
PAGE2 = json.loads((FIXTURES / "lever_page2.json").read_text())


def make_client(pages: dict[int, list[object]]) -> tuple[httpx.AsyncClient, list[dict[str, str]]]:
    """Serve `pages` keyed by the `skip` param; record each query."""
    queries: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = {k: v[0] for k, v in parse_qs(request.url.query.decode()).items()}
        queries.append(params)
        return httpx.Response(200, json=pages.get(int(params["skip"]), []))

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), queries


async def test_paginates_with_skip_until_short_page() -> None:
    client, queries = make_client({0: PAGE1, 2: PAGE2})
    source = LeverSource(client, "globex", page_size=2, limiter=RateLimiter(0))

    postings = [p async for p in source.fetch()]

    # 2 full + 1 short page's postings; short page ends the loop with
    # no extra request.
    assert len(postings) == 3
    assert [q["skip"] for q in queries] == ["0", "2"]
    assert queries[0]["mode"] == "json"


async def test_parses_fields_and_remote_flag() -> None:
    client, _ = make_client({0: PAGE1, 2: PAGE2})
    source = LeverSource(client, "globex", page_size=2, limiter=RateLimiter(0))

    ml, sre, em = [p async for p in source.fetch()]

    assert ml.source == "lever"
    assert ml.external_id == "a8bc6a04-5f6a-4e0e-8b90-1f9f3f1c2d3e"
    assert ml.title == "Machine Learning Engineer"
    assert ml.company == "Globex"
    assert ml.location == "New York, NY"
    assert ml.posted_at is not None
    assert ml.posted_at.year == 2026
    assert ml.remote is False  # hybrid is not remote, but it *was* stated
    assert sre.remote is True
    assert em.remote is False


async def test_description_includes_list_sections() -> None:
    """The Requirements bullets live in `lists`, not `descriptionPlain` —
    matching needs them, so the adapter must stitch them in."""
    client, _ = make_client({0: PAGE1, 2: PAGE2})
    source = LeverSource(client, "globex", page_size=2, limiter=RateLimiter(0))

    postings = [p async for p in source.fetch()]
    ml = postings[0]

    assert ml.description is not None
    assert "Join our ML team." in ml.description
    assert "Requirements" in ml.description
    assert "PyTorch or JAX" in ml.description
    assert "We offer equity." in ml.description
