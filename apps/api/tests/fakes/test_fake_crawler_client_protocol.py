"""`FakeCrawlerClient`・`HttpCrawlerClient` が、`CrawlerClient`(Protocol)と同じ形であること。

`test_in_memory_readers_protocols.py` と同じ流儀(Protocol を自動で列挙し、メソッド・引数・
同期/非同期・操作名の一覧の過不足を確かめる)。本物(`HttpCrawlerClient`)も同じ形であることを確かめる。
"""

import pytest

from loreley_api.infrastructure.crawler_client import HttpCrawlerClient, client
from tests.api_config import make_api_config
from tests.fakes.fake_crawler_client import OPERATIONS, FakeCrawlerClient
from tests.fakes.protocol_conformance import (
    assert_same_methods_as_protocol,
    protocols_defined_in,
    public_methods,
)


def test_the_client_module_defines_exactly_one_protocol() -> None:
    """Protocol を足したのに、偽物の検査に足し忘れる、を防ぐ。"""
    assert set(protocols_defined_in(client)) == {"CrawlerClient"}


def test_the_fake_has_every_protocol_method_with_the_same_parameters() -> None:
    assert_same_methods_as_protocol(FakeCrawlerClient(), client.CrawlerClient, label="fake")


def test_the_http_client_has_every_protocol_method_with_the_same_parameters() -> None:
    http_client = HttpCrawlerClient(make_api_config().crawler_client)
    try:
        assert_same_methods_as_protocol(http_client, client.CrawlerClient, label="http")
    finally:
        http_client.close()


def test_the_operation_names_of_the_fake_are_exactly_the_protocol_methods() -> None:
    assert set(public_methods(client.CrawlerClient)) == OPERATIONS


@pytest.mark.parametrize("operation", ["start_crawls", "crawl", "cancel", "release"])
def test_an_unknown_operation_name_is_rejected_instead_of_silently_accepted(
    operation: str,
) -> None:
    behavior = FakeCrawlerClient().behavior

    with pytest.raises(ValueError, match="unknown operation"):
        behavior.inject(operation, None)
    with pytest.raises(ValueError, match="unknown operation"):
        behavior.before(operation, lambda: None)
    with pytest.raises(ValueError, match="unknown operation"):
        behavior.calls_of(operation)
