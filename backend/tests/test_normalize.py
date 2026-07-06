"""Unit tests for the pure normalization functions.

These are the highest-leverage tests in Phase 1: every dedupe decision
flows through these functions, so each test case doubles as executable
documentation of what does — and deliberately does NOT — count as "the
same" title/company/URL.
"""

import pytest

from jobscout.normalize import (
    canonicalize_url,
    extract_salary,
    html_to_text,
    normalize_company,
    normalize_location,
    normalize_title,
)

# --- titles -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Senior Software Engineer", "senior   software engineer"),
        ("Sr. Software Engineer — Backend", "Sr Software Engineer Backend"),
        ("Engineer (Data Platform)", "engineer data platform"),
    ],
)
def test_titles_that_should_match(a: str, b: str) -> None:
    assert normalize_title(a) == normalize_title(b)


def test_titles_that_should_not_match() -> None:
    # No synonym expansion by design: a wrong merge is worse than a dup.
    assert normalize_title("Senior Engineer") != normalize_title("Sr Engineer")
    assert normalize_title("Engineer II") != normalize_title("Engineer III")


# --- companies ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Acme", "Acme, Inc."),
        ("Acme Inc", "ACME"),
        ("Globex Corporation", "globex"),
        ("Initech Ltd.", "Initech"),
    ],
)
def test_company_legal_suffixes_ignored(a: str, b: str) -> None:
    assert normalize_company(a) == normalize_company(b)


def test_company_that_is_only_a_suffix_is_kept() -> None:
    # "Co" is someone's actual whole name often enough.
    assert normalize_company("Co") == "co"


def test_company_none_passthrough() -> None:
    assert normalize_company(None) is None
    assert normalize_location(None) is None


# --- URLs --------------------------------------------------------------------


def test_url_tracking_params_and_fragment_dropped() -> None:
    assert canonicalize_url(
        "https://Boards.Greenhouse.io/acme/jobs/123/?gh_src=x&utm_source=tw#apply"
    ) == canonicalize_url("https://boards.greenhouse.io/acme/jobs/123")


def test_url_meaningful_params_kept() -> None:
    a = canonicalize_url("https://jobs.example.com/view?jid=42")
    b = canonicalize_url("https://jobs.example.com/view?jid=43")
    assert a != b


# --- salary ------------------------------------------------------------------


def test_salary_range_with_symbol() -> None:
    assert extract_salary("Compensation: $120,000 - $150,000 per year") == (
        120_000,
        150_000,
        "USD",
    )


def test_salary_k_suffix_and_dash_variants() -> None:
    # the en dash is the point of this test: sources use fancy dashes
    assert extract_salary("pays $120k–$150K depending on level") == (  # noqa: RUF001
        120_000,
        150_000,
        "USD",
    )


def test_salary_single_value_with_code() -> None:
    assert extract_salary("Base salary 95,000 USD") == (95_000, None, "USD")


def test_salary_ignores_unmarked_and_tiny_numbers() -> None:
    assert extract_salary("Join our team of 25 in a 50000 sq ft office") == (None, None, None)
    assert extract_salary("$25/hour") == (None, None, None)  # hourly: out of scope for now


# --- HTML --------------------------------------------------------------------


def test_html_to_text_blocks_bullets_entities() -> None:
    text = html_to_text(
        "<div><p>We&#39;re hiring &amp; growing.</p>"
        "<ul><li>Python</li><li>SQL</li></ul>"
        "<script>tracker()</script></div>"
    )
    assert "We're hiring & growing." in text
    assert "- Python" in text
    assert "- SQL" in text
    assert "tracker" not in text
