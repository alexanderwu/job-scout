"""The source-adapter contract every ingestion source implements.

Design notes
------------
``RawPosting`` is deliberately *thin*: it carries only the fields the
Phase 1 pipeline needs for cheap deduplication (``external_id``/``url``
for tier 1, ``title`` + ``company`` for tier 2) plus the source's full
untouched payload in ``raw``. Normalization into a rich schema happens
downstream, in one place — so when the normalized schema evolves, old
payloads can be re-normalized from ``raw`` without re-fetching anything.

``fetch()`` is an async *iterator* rather than the ``fetch() -> list``
sketched in PLAN.md. The iterator form subsumes the "pagination hooks"
the plan asked for: each adapter pages through its source internally and
yields postings as they arrive, so the pipeline can process a source of
any size with bounded memory, and a crash mid-fetch still keeps
everything yielded so far. Adapters that want to be polite between page
requests use :class:`~jobscout.sources.throttle.RateLimiter`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field


class RawPosting(BaseModel):
    """One job posting exactly as a source reported it.

    Frozen (immutable) on purpose: a raw posting is a fact about what a
    source said at ``fetched_at``; nothing downstream should edit it.

    The ``min_length=1`` constraints make "source returned a posting we
    can't identify or dedupe" a loud ValidationError at the adapter
    boundary instead of a silent empty string that corrupts dedupe later.
    """

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1)
    """Adapter name that produced this posting (``JobSource.name``)."""

    external_id: str = Field(min_length=1)
    """The source's own identifier for the posting — dedupe tier 1."""

    url: str = Field(min_length=1)
    """Canonical posting URL. Kept as a plain string: URL normalization
    (tracking params, trailing slashes, ...) is a dedupe concern handled
    explicitly in Phase 1, not silently by a URL type."""

    title: str = Field(min_length=1)
    company: str | None = None
    location: str | None = None
    posted_at: datetime | None = None
    """When the source says the job was published, if it says at all."""

    # Phase 1 widened the contract with the fields below. RawPosting
    # stays "thin" in spirit — these are *extracted*, not normalized —
    # but extraction is inherently per-source (only the adapter knows
    # where its payload keeps a description or comp figures), so it
    # belongs here rather than in a central normalizer that would need
    # an if-ladder per source.

    description: str | None = None
    """Plain-text job description (adapters strip source HTML)."""

    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    """Structured annual comp, only when the source reports it as data.
    Free-text salary parsing is the pipeline's job (normalize.py)."""

    remote: bool | None = None
    """Explicit remote flag from the source; None means it didn't say."""

    fetched_at: datetime
    """When *we* retrieved it — drives first_seen/last_seen in Phase 1."""

    raw: dict[str, Any]
    """The source's complete, untouched payload for this posting."""


class JobSource(ABC):
    """Interface all ingestion adapters implement.

    Adding a job board means writing one subclass of this — the pipeline
    itself never changes (PLAN.md guiding decision #2).
    """

    name: ClassVar[str]
    """Stable identifier for this source, stored on every RawPosting."""

    @abstractmethod
    def fetch(self) -> AsyncIterator[RawPosting]:
        """Yield postings from this source, paginating internally.

        Implementations are async generators: ``async def fetch(self)``
        with ``yield``. They should raise on hard failures (auth, schema
        surprises) rather than silently yielding nothing, so the
        pipeline can tell "source is empty" from "source is broken".
        """
