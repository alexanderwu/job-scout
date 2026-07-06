"""Source-independent normalization: dedupe keys, URLs, salary, HTML.

Everything here is a pure function over strings — no I/O, no source
knowledge. Source-*specific* extraction (where a given API keeps its
description or comp fields) lives in the adapters, because the adapter
is the one place that knows its payload shape; if it lived here, adding
a source would mean editing a central ``if source == ...`` ladder,
breaking the "new source = one new adapter" rule.

Normalization is deliberately conservative. These keys decide whether
two postings get *merged into one job*, and a wrong merge silently
corrupts data while a missed merge just shows a duplicate row. So: no
stemming, no synonym maps, no stripping of parenthesized qualifiers —
just casefolding, punctuation removal, whitespace collapsing, and (for
companies) dropping legal suffixes that vary across job boards.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")

# Legal-entity suffixes that job boards inconsistently include
# ("Acme" vs "Acme Inc." vs "Acme, Inc"). Dropped from the *normalized*
# company only — display strings keep whatever the source said.
_COMPANY_SUFFIXES = frozenset(
    {"inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "co", "gmbh", "plc"}
)

# Query parameters that identify the visitor, not the job. Everything
# else is kept: an unknown parameter might be load-bearing (some ATSs
# put the posting ID in the query string).
_TRACKING_PARAMS_RE = re.compile(r"^(utm_|gh_src$|lever-|ref$|src$|source$)")


def normalize_title(title: str) -> str:
    """Casefold, strip punctuation, collapse whitespace.

    "Sr. Software Engineer — Backend" and "sr software engineer backend"
    normalize identically; "Senior" vs "Sr" does **not** (that would
    need a synonym map, and the cost of a wrong merge outweighs the
    duplicate it avoids — revisit with evidence, not up front).
    """
    return _WS_RE.sub(" ", _PUNCT_RE.sub(" ", title.casefold())).strip()


def normalize_company(company: str | None) -> str | None:
    if company is None:
        return None
    words = _WS_RE.sub(" ", _PUNCT_RE.sub(" ", company.casefold())).strip().split(" ")
    while len(words) > 1 and words[-1] in _COMPANY_SUFFIXES:
        words.pop()
    normalized = " ".join(words)
    return normalized or None


def normalize_location(location: str | None) -> str | None:
    if location is None:
        return None
    normalized = _WS_RE.sub(" ", _PUNCT_RE.sub(" ", location.casefold())).strip()
    return normalized or None


def canonicalize_url(url: str) -> str:
    """Reduce a URL to its job-identifying core for tier-1 dedupe.

    Lowercases scheme/host, drops the fragment and tracking params,
    strips a trailing slash. Keeps everything else — over-aggressive
    canonicalization (e.g. dropping all query params) would merge
    distinct jobs on ATSs that address postings via the query string.
    """
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING_PARAMS_RE.match(k)]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            urlencode(query),
            "",  # fragment never identifies a job
        )
    )


# --- salary ----------------------------------------------------------------

_CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}

# Matches "$120,000 - $150,000", "$120k-$150K", "€90.000", "150,000 USD"...
# Amount = digits with , or . thousands separators, optional k suffix.
_MONEY = r"(?P<{name}>\d{{1,3}}(?:[,.]\d{{3}})*|\d+)\s*(?P<{name}_k>[kK])?"
_SALARY_RE = re.compile(
    r"(?P<sym>[$€£])?\s*"
    + _MONEY.format(name="lo")
    # en/em dashes below are deliberate: postings write "$120k" dash "$150k"
    # with every dash variant under the sun.
    + r"(?:\s*(?:-|–|—|to)\s*[$€£]?\s*"  # noqa: RUF001
    + _MONEY.format(name="hi")
    + r")?"
    r"(?:\s*(?P<code>USD|EUR|GBP|CAD))?",
)

# Sanity bounds for *annual* salaries; numbers outside are more likely
# hourly rates, revenue figures, or employee counts than a salary.
_MIN_ANNUAL = 20_000
_MAX_ANNUAL = 2_000_000


def _to_amount(digits: str, k_suffix: str | None) -> int:
    value = int(re.sub(r"[,.]", "", digits))
    return value * 1000 if k_suffix else value


def extract_salary(text: str) -> tuple[int | None, int | None, str | None]:
    """Best-effort ``(min, max, currency)`` from free text.

    Regex over prose is inherently lossy; this exists as a *fallback*
    for sources without structured comp fields (adapters pass structured
    values through when the source has them). The bounds filter keeps
    precision high at the cost of missing exotic formats — for a
    matching filter, a missing salary is far better than a wrong one.
    """
    for match in _SALARY_RE.finditer(text):
        sym, code = match.group("sym"), match.group("code")
        if not sym and not code:
            continue  # bare numbers are too ambiguous to trust
        lo = _to_amount(match.group("lo"), match.group("lo_k"))
        hi = match.group("hi") and _to_amount(match.group("hi"), match.group("hi_k"))
        if not (_MIN_ANNUAL <= lo <= _MAX_ANNUAL):
            continue
        if hi and not (lo <= hi <= _MAX_ANNUAL):
            hi = None
        currency = code or (_CURRENCY_SYMBOLS[sym] if sym else None)
        return lo, hi or None, currency
    return None, None, None


# --- HTML ------------------------------------------------------------------


class _TextExtractor(HTMLParser):
    """Minimal HTML → text: block tags become newlines, list items bullets.

    stdlib ``HTMLParser`` instead of BeautifulSoup: job descriptions are
    simple markup, we only need readable text, and it's one less
    dependency to keep current. Swap in bs4 if sources start sending
    pathological HTML.
    """

    _BLOCK_TAGS = frozenset({"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "tr"})
    _SKIP_TAGS = frozenset({"script", "style"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self._BLOCK_TAGS:
            self._chunks.append("\n- " if tag == "li" else "\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._chunks.append(data)

    def text(self) -> str:
        lines = (_WS_RE.sub(" ", line).strip() for line in "".join(self._chunks).split("\n"))
        return "\n".join(line for line in lines if line)


def html_to_text(html: str) -> str:
    """Readable plain text from job-description HTML."""
    extractor = _TextExtractor()
    extractor.feed(html)
    return extractor.text()
