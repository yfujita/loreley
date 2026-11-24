"""`OpenSearchHealthProbe`: `cluster.health` の応答の有無(C 6.2 の 2 つ目の表。C 11章 10)。

例外は `ConnectionError.info` の `urllib3.exceptions` の型で分類する。`status_code` が整数なら HTTP
エラーの応答(異常)、`"N/A"` なら接続の失敗。
"""

import logging

import pytest
from opensearchpy.exceptions import (
    AuthenticationException,
    AuthorizationException,
    ConnectionTimeout,
    SerializationError,
    SSLError,
    TransportError,
)
from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError
from urllib3.exceptions import (
    ConnectTimeoutError,
    NameResolutionError,
    NewConnectionError,
    ProtocolError,
    ReadTimeoutError,
)

from loreley_api.common.probe_outcome import ProbeOutcome
from loreley_api.infrastructure.opensearch import OpenSearchHealthProbe, ReadOnlyOpenSearch
from tests.fakes.fake_opensearch_client import FakeOpenSearchClient
from tests.secret_assertions import assert_secret_absent

SENTINEL = "SENTINEL-OPENSEARCH-HOST"


def connection_error(info: BaseException) -> OpenSearchConnectionError:
    return OpenSearchConnectionError("N/A", str(info), info)


def check_with(outcome: object) -> tuple[ProbeOutcome, FakeOpenSearchClient]:
    fake = FakeOpenSearchClient()
    fake.script("cluster.health", outcome)
    return OpenSearchHealthProbe(ReadOnlyOpenSearch(fake)).check(), fake


@pytest.mark.parametrize(
    "response",
    [
        {"cluster_name": "loreley", "status": "green"},
        {"cluster_name": "loreley", "status": "yellow"},
        # `red` でも応答できれば正常(詳細は O1。EP-12)。
        {"cluster_name": "loreley", "status": "red"},
        {},
        "not even a mapping",
    ],
    ids=["green", "yellow", "red", "empty", "unexpected shape"],
)
def test_any_response_is_normal_regardless_of_its_shape(response: object) -> None:
    outcome, _ = check_with(response)

    assert outcome == ProbeOutcome("normal", None)


def test_only_cluster_health_is_called_once() -> None:
    _, fake = check_with({"status": "green"})

    assert [request.operation for request in fake.requests] == ["cluster.health"]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        # HTTP エラーの応答(接続はできた): 異常。
        (TransportError(503, "unavailable", {}), ProbeOutcome("abnormal", "unexpected_status")),
        (TransportError(500, "boom", {}), ProbeOutcome("abnormal", "unexpected_status")),
        (AuthenticationException(401, "x", {}), ProbeOutcome("abnormal", "unexpected_status")),
        (AuthorizationException(403, "x", {}), ProbeOutcome("abnormal", "unexpected_status")),
        # 接続の失敗は `info`(urllib3 の元の例外)の型で分ける。
        (
            connection_error(NameResolutionError("h", None, OSError("x"))),
            ProbeOutcome("abnormal", "name_not_resolved"),
        ),
        (
            connection_error(NewConnectionError(None, "refused")),
            ProbeOutcome("abnormal", "connection_refused"),
        ),
        (
            connection_error(ConnectTimeoutError(None, "connect timed out")),
            ProbeOutcome("undetermined", "timeout"),
        ),
        (
            ConnectionTimeout("TIMEOUT", "read timed out", ReadTimeoutError(None, "u", "")),
            ProbeOutcome("undetermined", "timeout"),
        ),
        (
            connection_error(ProtocolError("reset")),
            ProbeOutcome("undetermined", "connection_error"),
        ),
        # `SSLError` は `ConnectionError` の子なので、`info` の型より先に判定する。
        (
            SSLError("N/A", "bad cert", NewConnectionError(None, "x")),
            ProbeOutcome("undetermined", "connection_error"),
        ),
        (
            OpenSearchConnectionError("N/A", "x", RuntimeError("x")),
            ProbeOutcome("undetermined", "connection_error"),
        ),
        (SerializationError("x"), ProbeOutcome("undetermined", "connection_error")),
        (RuntimeError("unexpected"), ProbeOutcome("undetermined", "connection_error")),
    ],
    ids=[
        "503",
        "500",
        "401",
        "403",
        "name not resolved",
        "connection refused",
        "connect timeout",
        "read timeout",
        "protocol error",
        "ssl error",
        "other connection error",
        "serialization",
        "unexpected",
    ],
)
def test_an_exception_is_classified_into_state_and_reason(
    error: Exception, expected: ProbeOutcome
) -> None:
    outcome, _ = check_with(error)

    assert outcome == expected


def test_the_exception_message_is_not_written_to_the_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)

    check_with(connection_error(NewConnectionError(None, f"refused {SENTINEL}")))
    check_with(RuntimeError(SENTINEL))

    assert any(record.name.startswith("loreley_api") for record in caplog.records)
    assert_secret_absent(SENTINEL, records=caplog.records)
