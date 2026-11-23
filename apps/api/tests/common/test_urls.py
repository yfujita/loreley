import pytest

from loreley_api.common.urls import InvalidUrlError, check_url

BOTH = {"http", "https"}


@pytest.mark.parametrize(
    "value",
    [
        "http://host",
        "https://host:9200",
        "http://host/",
        "http://host/path/to?x=1&y=2",
        "http://[::1]:8001/healthz",
        "http://192.0.2.1:80",
    ],
)
def test_a_valid_url_is_split(value: str) -> None:
    parts = check_url(value, allowed_schemes=BOTH)

    assert parts.hostname


@pytest.mark.parametrize(
    ("value", "allowed_schemes", "reason"),
    [
        ("ftp://host", BOTH, "scheme"),
        ("https://host", {"http"}, "scheme"),
        ("HTTPS://host", {"http"}, "scheme"),
        ("//host/path", BOTH, "scheme"),
        ("host:8080", BOTH, "scheme"),
        ("http:///path", BOTH, "host"),
        ("http://:8080", BOTH, "host"),
        ("http://user@host", BOTH, "userinfo"),
        ("http://user:SENTINEL@host", BOTH, "userinfo"),
        ("http://:SENTINEL@host", BOTH, "userinfo"),
        ("http://host/path#frag", BOTH, "fragment"),
        ("http://host#", BOTH, "fragment"),
        ("http://host:SENTINEL", BOTH, "malformed"),
        ("http://host:99999", BOTH, "malformed"),
        ("http://[::1", BOTH, "malformed"),
        ("", BOTH, "malformed"),
        (" http://host", BOTH, "malformed"),
        ("http://host\n", BOTH, "malformed"),
        ("http://ho\tst", BOTH, "malformed"),
        ("http://host/\x00", BOTH, "malformed"),
    ],
)
def test_an_invalid_url_is_rejected_with_a_fixed_reason(
    value: str, allowed_schemes: set[str], reason: str
) -> None:
    with pytest.raises(InvalidUrlError) as error_info:
        check_url(value, allowed_schemes=allowed_schemes)

    assert error_info.value.reason == reason
    assert "SENTINEL" not in str(error_info.value)
    assert value not in str(error_info.value) or value == ""
