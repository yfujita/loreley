from collections.abc import Callable

import pytest
from opensearchpy import OpenSearch

from loreley_crawler.infrastructure.opensearch import (
    OpenSearchConnectionConfig,
    close_clients,
    create_heartbeat_client,
    create_store_client,
)

URL = "http://opensearch:9200"


def test_the_store_and_heartbeat_clients_have_their_own_timeouts_and_connections() -> None:
    config = OpenSearchConnectionConfig(
        URL, store_request_timeout_seconds=30.0, heartbeat_request_timeout_seconds=7.5
    )

    store_client = create_store_client(config)
    heartbeat_client = create_heartbeat_client(config)

    assert store_client is not heartbeat_client
    assert store_client.transport is not heartbeat_client.transport
    assert store_client.transport.kwargs["timeout"] == 30.0
    assert heartbeat_client.transport.kwargs["timeout"] == 7.5
    close_clients(store_client, heartbeat_client)


@pytest.mark.parametrize("create", [create_store_client, create_heartbeat_client])
def test_clients_do_not_retry_on_their_own(
    create: Callable[[OpenSearchConnectionConfig], OpenSearch],
) -> None:
    # リトライは確認点つきの `common` の機構で、呼び出し側が行う(二重にしない)。
    client = create(OpenSearchConnectionConfig(URL))

    assert client.transport.max_retries == 0
    assert client.transport.retry_on_timeout is False
    assert client.transport.retry_on_status == ()
    close_clients(client)


def test_credentials_are_passed_as_basic_auth_and_never_shown_in_the_config_repr() -> None:
    config = OpenSearchConnectionConfig(URL, username="crawler", password="SENTINEL-PASSWORD")

    assert "SENTINEL-PASSWORD" not in repr(config)
    client = create_store_client(config)
    assert client.transport.kwargs["http_auth"] == ("crawler", "SENTINEL-PASSWORD")
    close_clients(client)


def test_credentials_embedded_in_the_url_are_rejected_without_echoing_them() -> None:
    with pytest.raises(ValueError, match="credentials must not be embedded") as excinfo:
        OpenSearchConnectionConfig("http://user:SENTINEL-PASSWORD@opensearch:9200")

    assert "SENTINEL-PASSWORD" not in str(excinfo.value)


@pytest.mark.parametrize(
    "credentials", [{"username": "crawler"}, {"password": "SENTINEL-PASSWORD"}]
)
def test_a_username_without_a_password_or_the_reverse_is_rejected(
    credentials: dict[str, str],
) -> None:
    with pytest.raises(ValueError, match="together") as excinfo:
        OpenSearchConnectionConfig(URL, **credentials)

    assert "SENTINEL-PASSWORD" not in str(excinfo.value)


def test_an_invalid_url_is_rejected_with_a_fixed_message() -> None:
    with pytest.raises(ValueError, match="the OpenSearch URL is invalid") as excinfo:
        OpenSearchConnectionConfig("http://SENTINEL-HOST:notaport")

    assert "SENTINEL-HOST" not in str(excinfo.value)
    assert excinfo.value.__context__ is None


@pytest.mark.parametrize(
    "overrides",
    [{"store_request_timeout_seconds": 0.0}, {"heartbeat_request_timeout_seconds": -1.0}],
)
def test_non_positive_timeouts_are_rejected(overrides: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        OpenSearchConnectionConfig(URL, **overrides)


def test_close_clients_closes_the_rest_even_if_one_close_fails() -> None:
    closed: list[str] = []

    class FailingClient:
        def close(self) -> None:
            closed.append("failing")
            raise RuntimeError("boom")

    class ClosableClient:
        def close(self) -> None:
            closed.append("ok")

    with pytest.raises(RuntimeError, match="boom"):
        close_clients(FailingClient(), ClosableClient())

    assert sorted(closed) == ["failing", "ok"]
