"""クライアントの生成(C 3.7)。接続はしない。"""

from dataclasses import replace

import pytest

from loreley_api.infrastructure.opensearch import (
    OpenSearchConnectionConfig,
    ReadOnlyOpenSearch,
    connection,
    create_probe_connection,
    create_read_connection,
)
from loreley_api.infrastructure.opensearch.connection import ReadOnlyConnection

SECRET_PASSWORD = "p@ssw0rd-secret"


def make_config(**overrides: object) -> OpenSearchConnectionConfig:
    return replace(
        OpenSearchConnectionConfig(
            url="http://opensearch.invalid:9200",
            username=None,
            password=None,
            verify_certs=True,
            ca_certs_path=None,
            request_timeout_seconds=10.0,
            max_retries=2,
            probe_timeout_seconds=3.0,
        ),
        **overrides,
    )


class RecordingOpenSearch:
    """`OpenSearch(...)` の引数を記録する(生成時に接続しないことも兼ねて確かめる)。"""

    instances: list["RecordingOpenSearch"]

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.closed = False
        type(self).instances.append(self)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[RecordingOpenSearch]:
    RecordingOpenSearch.instances = []
    monkeypatch.setattr(connection, "OpenSearch", RecordingOpenSearch)
    return RecordingOpenSearch.instances


def test_the_read_client_uses_the_configured_timeout_and_retries(
    recorded: list[RecordingOpenSearch],
) -> None:
    create_read_connection(make_config())

    [raw] = recorded
    assert raw.kwargs == {
        "hosts": ["http://opensearch.invalid:9200"],
        "http_auth": None,
        "verify_certs": True,
        "ca_certs": None,
        "timeout": 10.0,
        "max_retries": 2,
        "retry_on_timeout": False,
        "retry_on_status": (429, 500, 502, 503, 504),
        "pool_maxsize": 16,
    }


def test_the_probe_client_has_a_short_timeout_and_never_retries(
    recorded: list[RecordingOpenSearch],
) -> None:
    create_probe_connection(make_config())

    [raw] = recorded
    assert raw.kwargs["timeout"] == 3.0
    assert raw.kwargs["max_retries"] == 0
    assert raw.kwargs["retry_on_timeout"] is False
    assert raw.kwargs["retry_on_status"] == ()
    assert raw.kwargs["pool_maxsize"] == 8


def test_credentials_and_tls_settings_are_passed_to_the_client(
    recorded: list[RecordingOpenSearch],
) -> None:
    config = make_config(
        username="reader",
        password=SECRET_PASSWORD,
        verify_certs=False,
        ca_certs_path="/certs/ca.pem",
    )

    create_read_connection(config)

    [raw] = recorded
    assert raw.kwargs["http_auth"] == ("reader", SECRET_PASSWORD)
    assert raw.kwargs["verify_certs"] is False
    assert raw.kwargs["ca_certs"] == "/certs/ca.pem"
    assert SECRET_PASSWORD not in repr(config)


def test_the_connection_gives_the_readonly_wrapper_and_closes_the_raw_client(
    recorded: list[RecordingOpenSearch],
) -> None:
    result = create_read_connection(make_config())

    assert isinstance(result, ReadOnlyConnection)
    assert isinstance(result.client, ReadOnlyOpenSearch)
    assert not recorded[0].closed
    result.close()
    assert recorded[0].closed


def test_creating_a_client_does_not_connect() -> None:
    """名前解決できない `.invalid` のホストでも、生成は失敗しない(起動時に接続しない。C 8.4)。"""
    result = create_read_connection(make_config())

    assert isinstance(result.client, ReadOnlyOpenSearch)
    result.close()
