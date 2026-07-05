"""Contract tests for the JobSource interface and RawPosting model."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from jobscout.sources import JobSource, RawPosting


def make_posting(**overrides: object) -> RawPosting:
    defaults: dict[str, object] = {
        "source": "fake",
        "external_id": "1",
        "url": "https://example.com/jobs/1",
        "title": "Data Engineer",
        "fetched_at": datetime.now(tz=UTC),
        "raw": {"id": "1"},
    }
    return RawPosting(**{**defaults, **overrides})  # type: ignore[arg-type]


class FakeSource(JobSource):
    """Minimal in-memory adapter proving the interface is implementable."""

    name = "fake"

    def __init__(self, postings: list[RawPosting]) -> None:
        self._postings = postings

    async def fetch(self) -> AsyncIterator[RawPosting]:
        for posting in self._postings:
            yield posting


async def test_fake_source_yields_postings() -> None:
    postings = [make_posting(external_id=str(i)) for i in range(3)]
    fetched = [p async for p in FakeSource(postings).fetch()]
    assert fetched == postings


def test_raw_posting_is_immutable() -> None:
    posting = make_posting()
    with pytest.raises(ValidationError):
        posting.title = "Edited"


@pytest.mark.parametrize("field", ["source", "external_id", "url", "title"])
def test_identity_fields_reject_empty_strings(field: str) -> None:
    with pytest.raises(ValidationError):
        make_posting(**{field: ""})
