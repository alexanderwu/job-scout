from jobscout.normalize import normalize_company, normalize_title, normalize_url


def test_normalize_title_collapses_whitespace_and_case() -> None:
    assert normalize_title("  Senior   Data Engineer ") == "senior data engineer"


def test_normalize_company_none_stays_none() -> None:
    assert normalize_company(None) is None


def test_normalize_company_blank_becomes_none() -> None:
    assert normalize_company("   ") is None


def test_normalize_company_trims_and_casefolds() -> None:
    assert normalize_company(" Acme  Corp ") == "acme corp"


def test_normalize_url_lowercases_and_drops_trailing_slash() -> None:
    assert normalize_url("HTTPS://Example.com/Jobs/123/") == "https://example.com/Jobs/123"


def test_normalize_url_strips_tracking_params() -> None:
    url = "https://example.com/jobs/123?utm_source=hiringcafe&ref=xyz&gh_jid=456"
    assert normalize_url(url) == "https://example.com/jobs/123?gh_jid=456"


def test_normalize_url_sorts_remaining_params() -> None:
    a = normalize_url("https://example.com/jobs?b=2&a=1")
    b = normalize_url("https://example.com/jobs?a=1&b=2")
    assert a == b
