"""SourcesReader(R-1・R-2)。"""

import pytest
from opensearchpy.exceptions import ConnectionTimeout, TransportError

from loreley_api.common.results import Failed, Ok
from loreley_api.infrastructure.opensearch import (
    OpenSearchSourcesReader,
    ReadOnlyOpenSearch,
    StoredRecord,
    queries,
)
from tests.fakes.fake_opensearch_client import FakeOpenSearchClient
from tests.infrastructure.opensearch.conftest import INDEX_NAMES
from tests.infrastructure.opensearch.sample_responses import (
    hit,
    mget_doc,
    mget_response,
    search_response,
)


@pytest.fixture
def reader(readonly: ReadOnlyOpenSearch) -> OpenSearchSourcesReader:
    return OpenSearchSourcesReader(readonly, sources_index=INDEX_NAMES.sources)


def test_list_all_reads_every_source_without_connector_config(
    reader: OpenSearchSourcesReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script(
        "search", search_response([hit("a", {"status": "active"}), hit("b", {})], total=2)
    )

    result = reader.list_all()

    assert result == Ok((StoredRecord("a", {"status": "active"}), StoredRecord("b", {})))
    [request] = fake_client.requests
    assert request.index == INDEX_NAMES.sources
    assert request.body == queries.sources_all_body()


def test_list_all_accepts_exactly_the_upper_limit(
    reader: OpenSearchSourcesReader, fake_client: FakeOpenSearchClient
) -> None:
    hits = [hit(f"s{i}", {}) for i in range(10_000)]
    fake_client.script("search", search_response(hits, total=10_000))

    result = reader.list_all()

    assert isinstance(result, Ok)
    assert len(result.value) == 10_000


def test_list_all_fails_instead_of_returning_a_truncated_list(
    reader: OpenSearchSourcesReader, fake_client: FakeOpenSearchClient
) -> None:
    hits = [hit(f"s{i}", {}) for i in range(10_000)]
    fake_client.script("search", search_response(hits, total=10_001))

    assert reader.list_all() == Failed("unavailable", "store", "ResultLimitExceededError")


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (ConnectionTimeout("TIMEOUT", "x", None), Failed("timeout", "store", "ConnectionTimeout")),
        (TransportError(503, "x", {}), Failed("unavailable", "store", "TransportError")),
        (RuntimeError("x"), Failed("unavailable", "store", "RuntimeError")),
        (
            search_response([hit("a", {})], total=1, timed_out=True),
            Failed("timeout", "store", "PartialResponseError"),
        ),
        (
            search_response([hit("a", {})], total=1, failed_shards=1),
            Failed("unavailable", "store", "PartialResponseError"),
        ),
        ({"unexpected": True}, Failed("unavailable", "store", "ResponseShapeError")),
    ],
)
def test_list_all_never_leaks_an_exception(
    reader: OpenSearchSourcesReader,
    fake_client: FakeOpenSearchClient,
    outcome: object,
    expected: Failed,
) -> None:
    fake_client.script("search", outcome)

    assert reader.list_all() == expected


def test_get_reads_all_fields_when_none_are_specified(
    reader: OpenSearchSourcesReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("mget", mget_response(mget_doc("a", {"connector_config": {}})))

    result = reader.get("a", None)

    assert result == Ok(StoredRecord("a", {"connector_config": {}}))
    [request] = fake_client.requests
    assert (request.index, request.body, request.query_params) == (
        INDEX_NAMES.sources,
        {"ids": ["a"]},
        {},
    )


def test_get_reads_only_the_requested_fields(
    reader: OpenSearchSourcesReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("mget", mget_response(mget_doc("a", {"status": "active"})))

    assert reader.get("a", ("status",)) == Ok(StoredRecord("a", {"status": "active"}))
    assert fake_client.requests[0].query_params == {"_source_includes": ["status"]}


def test_get_with_no_fields_is_an_existence_check_without_the_source(
    reader: OpenSearchSourcesReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("mget", mget_response(mget_doc("a")))

    assert reader.get("a", ()) == Ok(StoredRecord("a", {}))
    assert fake_client.requests[0].query_params == {"_source": False}


def test_get_returns_none_for_a_missing_source(
    reader: OpenSearchSourcesReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("mget", mget_response(mget_doc("a", found=False)))

    assert reader.get("a", None) == Ok(None)


def test_get_does_not_read_a_failed_document_as_missing(
    reader: OpenSearchSourcesReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("mget", mget_response({"_id": "a", "error": {"type": "x"}}))

    assert reader.get("a", None) == Failed("unavailable", "store", "DocumentError")


def test_get_never_leaks_an_exception(
    reader: OpenSearchSourcesReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("mget", ConnectionTimeout("TIMEOUT", "x", None))

    assert reader.get("a", None) == Failed("timeout", "store", "ConnectionTimeout")
