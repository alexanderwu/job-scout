"""Greenhouse adapter tests.

Unlike the hiring.cafe fixtures (reverse-engineered), this fixture
mirrors Greenhouse's *documented* Job Board API response, so a mismatch
here is a bug in our code, not a guess about theirs.
"""

import json
from pathlib import Path

import httpx
import pytest

from jobscout.sources.greenhouse import GreenhouseSource

FIXTURES = Path(__file__).parent / "fixtures"
BOARD = json.loads((FIXTURES / "greenhouse_board.json").read_text())


def make_client(payload: object) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), requests


async def test_parses_board_fixture() -> None:
    client, requests = make_client(BOARD)
    source = GreenhouseSource(client, "acme")

    postings = [p async for p in source.fetch()]

    assert len(postings) == 2
    assert requests[0].url == ("https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true")

    first = postings[0]
    assert first.source == "greenhouse"
    assert first.external_id == "4021775008"
    assert first.title == "Staff Software Engineer, Data Platform"
    assert first.company == "Acme"  # board token title-cased by default
    assert first.location == "San Francisco, CA"
    assert first.posted_at is not None
    assert first.posted_at.year == 2026
    assert first.raw == BOARD["jobs"][0]


async def test_content_is_unescaped_to_plain_text() -> None:
    """Greenhouse HTML-escapes `content`; we must get readable text out."""
    client, _ = make_client(BOARD)
    source = GreenhouseSource(client, "acme")

    postings = [p async for p in source.fetch()]

    description = postings[0].description
    assert description is not None
    assert "Staff Software Engineer" in description
    assert "- 7+ years building distributed systems" in description
    assert "$190,000 - $240,000" in description
    assert "&lt;" not in description
    assert "<li>" not in description


async def test_company_override_and_null_first_published() -> None:
    client, _ = make_client(BOARD)
    source = GreenhouseSource(client, "acme", company="Acme Corp")

    postings = [p async for p in source.fetch()]

    assert postings[1].company == "Acme Corp"
    # first_published null -> falls back to updated_at
    assert postings[1].posted_at is not None
    assert postings[1].posted_at.month == 7


async def test_http_error_raises() -> None:
    client, _ = make_client(BOARD)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    source = GreenhouseSource(client, "nonexistent-board")

    with pytest.raises(httpx.HTTPStatusError):
        _ = [p async for p in source.fetch()]
