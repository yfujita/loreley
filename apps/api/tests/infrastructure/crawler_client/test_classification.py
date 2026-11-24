"""urllib3 の例外の分類(C 4.3。C 11章 2。`SSLError` は通信で再現しにくいので例外を直接与える)。"""

import pytest
from urllib3.exceptions import (
    ConnectTimeoutError,
    DecodeError,
    HTTPError,
    IncompleteRead,
    LocationParseError,
    MaxRetryError,
    NameResolutionError,
    NewConnectionError,
    ProtocolError,
    ProxyError,
    ReadTimeoutError,
    ResponseError,
    SSLError,
)
from urllib3.exceptions import TimeoutError as Urllib3TimeoutError

from loreley_api.infrastructure.crawler_client import CrawlerTransportFailed
from loreley_api.infrastructure.crawler_client.classification import classify_transport_failure

BEFORE_SEND = "before_send"
AFTER_SEND = "after_send"


@pytest.mark.parametrize(
    ("error", "phase", "reason"),
    [
        # 狭いほうから判定する(NameResolutionError ⊂ NewConnectionError ⊂ ConnectTimeoutError)。
        (
            NameResolutionError("crawler.invalid", None, OSError("x")),
            BEFORE_SEND,
            "name_resolution",
        ),
        (NewConnectionError(None, "refused"), BEFORE_SEND, "connection_failed"),
        (ConnectTimeoutError(None, "connect timed out"), BEFORE_SEND, "connect_timeout"),
        (SSLError("handshake failed"), BEFORE_SEND, "tls_failure"),
        (ReadTimeoutError(None, "/x", "read timed out"), AFTER_SEND, "response_timeout"),
        (ProtocolError("Connection aborted."), AFTER_SEND, "connection_lost"),
        (IncompleteRead(10, 5), AFTER_SEND, "http_error"),  # 本物は ProtocolError に包まれて届く
        # その他の urllib3 の例外は、送った可能性があるので結果不明にする。
        (DecodeError("bad gzip"), AFTER_SEND, "http_error"),
        (HTTPError("other"), AFTER_SEND, "http_error"),
        (Urllib3TimeoutError("timeout of an unknown kind"), AFTER_SEND, "http_error"),
        (ProxyError("proxy", OSError("x")), AFTER_SEND, "http_error"),
        (ResponseError("too many redirects"), AFTER_SEND, "http_error"),
        (LocationParseError("bad url"), AFTER_SEND, "http_error"),
    ],
)
def test_each_urllib3_exception_is_classified(error: HTTPError, phase: str, reason: str) -> None:
    assert classify_transport_failure(error) == CrawlerTransportFailed(phase, reason)  # type: ignore[arg-type]


def test_a_max_retry_error_is_classified_as_unknown_outcome() -> None:
    """`retries=False` では出ないはずの例外。出たら、結果不明(安全側)にする。"""
    error = MaxRetryError(None, "/x", ReadTimeoutError(None, "/x", "t"))  # type: ignore[arg-type]

    assert classify_transport_failure(error) == CrawlerTransportFailed(AFTER_SEND, "http_error")


def test_the_result_carries_no_text_of_the_exception() -> None:
    result = classify_transport_failure(NewConnectionError(None, "SENTINEL-HOST-12345"))

    assert "SENTINEL" not in repr(result)
