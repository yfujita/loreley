from loreley_crawler.common.errors import (
    CrawlerError,
    StoreUnavailableError,
    StoreUnexpectedResponseError,
    is_store_unavailable,
)


def test_unavailable_error_is_a_crawler_error_carrying_only_a_reason() -> None:
    error = StoreUnavailableError("timeout")
    assert isinstance(error, CrawlerError)
    assert error.reason == "timeout"
    assert str(error) == "timeout"


def test_unexpected_response_error_is_a_crawler_error_carrying_only_the_error_type() -> None:
    error = StoreUnexpectedResponseError("parsing_exception")
    assert isinstance(error, CrawlerError)
    assert error.error_type == "parsing_exception"
    assert str(error) == "parsing_exception"


def test_store_errors_are_distinguishable() -> None:
    assert not issubclass(StoreUnavailableError, StoreUnexpectedResponseError)
    assert not issubclass(StoreUnexpectedResponseError, StoreUnavailableError)


def test_only_store_unavailable_errors_are_retryable() -> None:
    assert is_store_unavailable(StoreUnavailableError("timeout"))
    assert not is_store_unavailable(StoreUnexpectedResponseError("http_400"))
    assert not is_store_unavailable(RuntimeError("x"))
