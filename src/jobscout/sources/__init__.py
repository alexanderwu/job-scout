"""Ingestion source adapters.

Every job source (hiring.cafe, Greenhouse, Lever, ...) implements the
:class:`~jobscout.sources.base.JobSource` interface, so the ingestion
pipeline never depends on any single board's API. See PLAN.md guiding
decision #2 ("source-agnostic ingestion").
"""

from jobscout.sources.base import JobSource, RawPosting
from jobscout.sources.hiring_cafe import HiringCafeSource

__all__ = ["HiringCafeSource", "JobSource", "RawPosting"]
