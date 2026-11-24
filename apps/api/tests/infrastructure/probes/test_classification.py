"""HTTP の確認結果の分類(C 6.2 の 1 つ目の表。C 11章 10)。狭いほうから順に判定する。"""

import pytest
from urllib3.exceptions import (
    ConnectTimeoutError,
    HTTPError,
    LocationParseError,
    NameResolutionError,
    NewConnectionError,
    ProtocolError,
    ReadTimeoutError,
    SSLError,
)

from loreley_api.common.probe_outcome import ProbeOutcome
from loreley_api.infrastructure.probes.classification import classify_exception, classify_status


@pytest.mark.parametrize("status", [200, 201, 202, 204, 206, 299])
def test_a_2xx_status_is_normal(status: int) -> None:
    assert classify_status(status) == ProbeOutcome("normal", None)


@pytest.mark.parametrize("status", [100, 199, 300, 301, 302, 307, 308, 400, 401, 404, 500, 503])
def test_any_status_outside_2xx_is_abnormal_unexpected_status(status: int) -> None:
    """3xx(リダイレクトは追わない)・Indexer の起動前の 503 を含む。"""
    assert classify_status(status) == ProbeOutcome("abnormal", "unexpected_status")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        # 狭い順: NameResolutionError ⊂ NewConnectionError ⊂ ConnectTimeoutError。
        (
            NameResolutionError("host", None, OSError("x")),
            ProbeOutcome("abnormal", "name_not_resolved"),
        ),
        (NewConnectionError(None, "refused"), ProbeOutcome("abnormal", "connection_refused")),
        (ConnectTimeoutError(None, "connect timed out"), ProbeOutcome("undetermined", "timeout")),
        (ReadTimeoutError(None, "u", "read timed out"), ProbeOutcome("undetermined", "timeout")),
        (ProtocolError("reset"), ProbeOutcome("undetermined", "connection_error")),
        (SSLError("bad certificate"), ProbeOutcome("undetermined", "connection_error")),
        (HTTPError("other"), ProbeOutcome("undetermined", "connection_error")),
        (LocationParseError("bad url"), ProbeOutcome("undetermined", "connection_error")),
        (RuntimeError("unexpected"), ProbeOutcome("undetermined", "connection_error")),
        (OSError("unexpected"), ProbeOutcome("undetermined", "connection_error")),
    ],
    ids=[
        "name not resolved",
        "connection refused",
        "connect timeout",
        "read timeout",
        "protocol error",
        "ssl error",
        "other http error",
        "location parse error",
        "unexpected runtime error",
        "unexpected os error",
    ],
)
def test_an_exception_is_classified_from_the_narrowest_type(
    error: Exception, expected: ProbeOutcome
) -> None:
    assert classify_exception(error) == expected
