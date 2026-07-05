"""Normalization used by dedupe (PLAN.md Phase 1, tiers 1-2).

Kept as small pure functions, independent of the pipeline and the DB, so
dedupe behavior is unit-testable without a database and reusable if a
future re-normalization pass needs to run over stored ``raw`` payloads.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_WHITESPACE = re.compile(r"\s+")

# Query params that are noise for identity (analytics/referral tags), not
# part of what makes a URL point at a distinct job. Everything else is
# kept, since some ATSs (e.g. Greenhouse's `gh_jid`) encode the actual
# job identity in the query string.
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAMS = {"ref", "source", "fbclid", "gclid"}


def normalize_title(title: str) -> str:
    return _WHITESPACE.sub(" ", title).strip().casefold()


def normalize_company(company: str | None) -> str | None:
    if company is None:
        return None
    normalized = _WHITESPACE.sub(" ", company).strip().casefold()
    return normalized or None


def normalize_url(url: str) -> str:
    """Canonicalize a posting URL for tier-1 dedupe.

    Lowercases scheme/host, drops a trailing slash, strips known tracking
    params, and sorts the remaining query params so param-order
    differences don't defeat matching.
    """
    parts = urlsplit(url)
    kept_params = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in _TRACKING_PARAMS and not key.startswith(_TRACKING_PARAM_PREFIXES)
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(kept_params), "")
    )
