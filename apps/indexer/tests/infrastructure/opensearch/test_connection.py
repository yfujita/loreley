import traceback
from unittest.mock import MagicMock

import pytest

from loreley_indexer.infrastructure.opensearch import (
    OpenSearchConnectionConfig,
    close_clients,
    create_delete_by_query_client,
    create_opensearch_client,
)


def test_client_uses_the_configured_timeout_retries_and_credentials() -> None:
    client = create_opensearch_client(
        OpenSearchConnectionConfig(
            url="https://opensearch:9200",
            username="indexer",
            password="s3cret",
            request_timeout_seconds=12,
            transport_max_retries=4,
        )
    )
    transport = client.transport
    assert transport.max_retries == 4
    assert transport.retry_on_timeout is True
    assert transport.kwargs["timeout"] == 12
    assert transport.kwargs["http_auth"] == ("indexer", "s3cret")
    assert transport.kwargs["verify_certs"] is True
    assert transport.connection_pool.connections[0].use_ssl is True


def test_client_without_credentials_sends_no_auth() -> None:
    client = create_opensearch_client(OpenSearchConnectionConfig(url="http://opensearch:9200"))
    assert client.transport.kwargs["http_auth"] is None


def test_client_with_a_username_but_no_password_sends_no_auth() -> None:
    client = create_opensearch_client(
        OpenSearchConnectionConfig(url="http://opensearch:9200", username="indexer")
    )
    assert client.transport.kwargs["http_auth"] is None


@pytest.mark.filterwarnings("ignore:Connecting to .* verify_certs=False is insecure")
def test_client_can_disable_certificate_verification() -> None:
    client = create_opensearch_client(
        OpenSearchConnectionConfig(url="https://opensearch:9200", verify_certs=False)
    )
    assert client.transport.kwargs["verify_certs"] is False


def test_client_uses_the_configured_ca_certificate_path() -> None:
    client = create_opensearch_client(
        OpenSearchConnectionConfig(url="https://opensearch:9200", ca_certs_path="/certs/ca.pem")
    )
    assert client.transport.kwargs["ca_certs"] == "/certs/ca.pem"


def test_password_is_not_shown_in_repr() -> None:
    config = OpenSearchConnectionConfig(url="http://os:9200", username="u", password="s3cret")
    assert "s3cret" not in repr(config)


def test_close_clients_closes_every_client_even_if_one_fails() -> None:
    first, second, third = MagicMock(), MagicMock(), MagicMock()
    second.close.side_effect = RuntimeError("cannot close")

    with pytest.raises(RuntimeError, match="cannot close"):
        close_clients(first, second, third)

    for client in (first, second, third):
        client.close.assert_called_once_with()


def test_close_clients_closes_real_clients_without_connecting() -> None:
    config = OpenSearchConnectionConfig(url="http://opensearch.invalid:9200")
    close_clients(create_opensearch_client(config), create_delete_by_query_client(config))


def test_credentials_embedded_in_the_url_are_rejected() -> None:
    with pytest.raises(ValueError, match="credentials"):
        OpenSearchConnectionConfig(url="http://user:pass@os:9200")


@pytest.mark.parametrize(
    "url",
    [
        # NFKC で正規化できない文字を含む netloc(標準ライブラリは netloc をメッセージに入れる)。
        "http://user:SENTINEL-PW@host\u2100:9200",
        "http://host:SENTINEL-PORT",
        "http://host:99999999",
        "http://[SENTINEL-HOST",
    ],
)
def test_an_unparsable_url_is_rejected_without_showing_the_url(url: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        OpenSearchConnectionConfig(url=url)

    error = excinfo.value
    assert str(error) == "the OpenSearch URL is invalid"
    assert error.__context__ is None  # 値を持つ元の例外を連鎖させない
    assert error.__cause__ is None
    assert "SENTINEL" not in "".join(traceback.format_exception(error))


@pytest.mark.filterwarnings("ignore:Connecting to .* verify_certs=False is insecure")
def test_delete_by_query_client_does_not_retry_on_timeout_but_is_otherwise_the_same() -> None:
    """timeout で自動再送しない(P4。0005 の持ち越し)。ほかの接続設定は通常のクライアントと同じ。"""
    config = OpenSearchConnectionConfig(
        url="https://opensearch:9200",
        username="indexer",
        password="s3cret",
        verify_certs=False,
        ca_certs_path="/certs/ca.pem",
        request_timeout_seconds=12,
        transport_max_retries=4,
    )
    general = create_opensearch_client(config).transport
    dedicated = create_delete_by_query_client(config).transport

    assert general.retry_on_timeout is True
    assert dedicated.retry_on_timeout is False
    assert tuple(general.retry_on_status) == (502, 503, 504)
    assert tuple(dedicated.retry_on_status) == ()  # 502/503/504 でも再送しない
    assert dedicated.max_retries == general.max_retries == 4
    assert dedicated.kwargs == general.kwargs
    assert dedicated.connection_pool.connections[0].use_ssl is True


def test_delete_by_query_timeout_default_is_defined_in_one_place() -> None:
    from loreley_indexer.infrastructure.opensearch.connection import (
        DEFAULT_DELETE_BY_QUERY_TIMEOUT_SECONDS,
    )
    from tests.test_config import make_settings

    default = OpenSearchConnectionConfig(url="http://opensearch:9200")
    assert default.delete_by_query_timeout_seconds == DEFAULT_DELETE_BY_QUERY_TIMEOUT_SECONDS
    settings = make_settings()
    assert settings.os_delete_by_query_timeout_seconds == DEFAULT_DELETE_BY_QUERY_TIMEOUT_SECONDS


def test_delete_by_query_timeout_defaults_to_a_value_longer_than_the_request_timeout() -> None:
    config = OpenSearchConnectionConfig(url="http://opensearch:9200")
    assert config.delete_by_query_timeout_seconds > config.request_timeout_seconds
