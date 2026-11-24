"""SearchIndexReader(R-9 の EP-01 の集計・R-10・R-11)。"""

from collections.abc import Callable

import pytest
from opensearchpy.exceptions import ConnectionTimeout, TransportError

from loreley_api.common.results import Failed, Ok
from loreley_api.infrastructure.opensearch import (
    OpenSearchSearchIndexReader,
    Page,
    PageRequest,
    ReadOnlyOpenSearch,
    StoredRecord,
    queries,
)
from tests.fakes.fake_opensearch_client import FakeOpenSearchClient
from tests.infrastructure.opensearch.conftest import INDEX_NAMES
from tests.infrastructure.opensearch.sample_responses import (
    hit,
    search_response,
    with_capped_total,
)

PAGE = PageRequest(page=1, items_per_page=50, descending=False)
FAILED_TARGET = "search_index"


@pytest.fixture
def reader(readonly: ReadOnlyOpenSearch) -> OpenSearchSearchIndexReader:
    return OpenSearchSearchIndexReader(readonly, search_index_alias=INDEX_NAMES.search)


def count_response(buckets: list[dict[str, object]]) -> dict[str, object]:
    return search_response(total=0, aggregations={"by_source": {"buckets": buckets}})


def test_count_by_source_returns_zero_for_a_source_without_documents(
    reader: OpenSearchSearchIndexReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script(
        "search",
        count_response([{"key": "a", "doc_count": 7}, {"key": "unrelated", "doc_count": 1}]),
    )

    assert reader.count_by_source(["a", "b"]) == Ok({"a": 7, "b": 0})
    [request] = fake_client.requests
    assert request.index == INDEX_NAMES.search  # エイリアスを読む
    assert request.body == queries.count_by_source_body(["a", "b"])


def test_count_by_source_without_sources_does_not_query(
    reader: OpenSearchSearchIndexReader, fake_client: FakeOpenSearchClient
) -> None:
    assert reader.count_by_source([]) == Ok({})
    assert fake_client.requests == []


@pytest.mark.parametrize(
    "response",
    [
        search_response(total=0),
        count_response([{"key": "a"}]),
        count_response([{"key": "a", "doc_count": "7"}]),
        count_response([{"key": 1, "doc_count": 7}]),
    ],
)
def test_count_by_source_fails_on_a_malformed_aggregation(
    reader: OpenSearchSearchIndexReader, fake_client: FakeOpenSearchClient, response: object
) -> None:
    fake_client.script("search", response)

    assert reader.count_by_source(["a"]) == Failed(
        "unavailable", FAILED_TARGET, "ResponseShapeError"
    )


@pytest.mark.parametrize(
    ("method", "build"),
    [
        ("list_extract_failed", queries.extract_failed_list_body),
        ("list_summary_pending", queries.summary_pending_list_body),
    ],
)
def test_the_search_index_tabs_are_listed_from_the_alias(
    reader: OpenSearchSearchIndexReader,
    fake_client: FakeOpenSearchClient,
    method: str,
    build: Callable[[str, PageRequest], dict[str, object]],
) -> None:
    fake_client.script("search", search_response([hit("doc-1", {"title": "t"})], total=1))

    result = getattr(reader, method)("a", PAGE)

    assert result == Ok(Page(1, (StoredRecord("doc-1", {"title": "t"}),)))
    [request] = fake_client.requests
    assert request.index == INDEX_NAMES.search
    assert request.body == build("a", PAGE)


@pytest.mark.parametrize(
    ("outcome", "expected_kind"),
    [
        (TransportError(503, "x", {}), "unavailable"),
        (ConnectionTimeout("TIMEOUT", "x", None), "timeout"),
        (search_response([hit("a", {})], total=1, failed_shards=1), "unavailable"),
        (search_response([hit("a", {})], total=1, timed_out=True), "timeout"),
    ],
)
def test_the_list_methods_report_the_search_index_as_the_failed_target(
    reader: OpenSearchSearchIndexReader,
    fake_client: FakeOpenSearchClient,
    outcome: object,
    expected_kind: str,
) -> None:
    for call in (
        lambda: reader.list_extract_failed("a", PAGE),
        lambda: reader.list_summary_pending("a", PAGE),
        lambda: reader.count_by_source(["a"]),
        lambda: reader.existing_ids(["d1"]),
    ):
        fake_client.script("search", outcome)
        failed = call()
        assert isinstance(failed, Failed)
        assert (failed.kind, failed.target) == (expected_kind, FAILED_TARGET)


def test_existing_ids_returns_the_ids_found_in_the_index(
    reader: OpenSearchSearchIndexReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("search", search_response([hit("d1"), hit("d3")]))

    assert reader.existing_ids(["d1", "d2", "d3"]) == Ok(frozenset({"d1", "d3"}))
    [request] = fake_client.requests
    assert request.index == INDEX_NAMES.search
    assert request.body == queries.existing_ids_body(["d1", "d2", "d3"])


def test_existing_ids_does_not_depend_on_the_total_of_the_response(
    reader: OpenSearchSearchIndexReader, fake_client: FakeOpenSearchClient
) -> None:
    """本文は `track_total_hits: false`(総件数を使わない)。頭打ちの `total` があっても読める。"""
    assert queries.existing_ids_body(["d1"])["track_total_hits"] is False
    fake_client.script("search", with_capped_total(search_response([hit("d1")])))

    assert reader.existing_ids(["d1"]) == Ok(frozenset({"d1"}))


def test_existing_ids_without_ids_does_not_query(
    reader: OpenSearchSearchIndexReader, fake_client: FakeOpenSearchClient
) -> None:
    assert reader.existing_ids([]) == Ok(frozenset())
    assert fake_client.requests == []


def test_existing_ids_accepts_up_to_one_hundred_ids(
    reader: OpenSearchSearchIndexReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("search", search_response([]))

    assert reader.existing_ids([f"d{i}" for i in range(100)]) == Ok(frozenset())


def test_existing_ids_rejects_more_than_one_hundred_ids(
    reader: OpenSearchSearchIndexReader,
) -> None:
    with pytest.raises(ValueError, match="too many"):
        reader.existing_ids([f"d{i}" for i in range(101)])
