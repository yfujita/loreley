"""CountsReader(R-9。`msearch` のサブ要求ごとの成否)。"""

import pytest
from opensearchpy.exceptions import ConnectionTimeout, TransportError

from loreley_api.common.results import Failed, FailureKind, Ok
from loreley_api.infrastructure.opensearch import (
    CountTarget,
    OpenSearchCountsReader,
    ReadOnlyOpenSearch,
    queries,
)
from tests.fakes.fake_opensearch_client import FakeOpenSearchClient
from tests.infrastructure.opensearch.conftest import INDEX_NAMES
from tests.infrastructure.opensearch.sample_responses import (
    SUB_REQUEST_ERROR,
    msearch_response,
    search_response,
)

ALL_TARGETS: tuple[CountTarget, ...] = (
    "document_count",
    "skipped",
    "oversize",
    "extract_failed",
    "summary_pending",
)


@pytest.fixture
def reader(readonly: ReadOnlyOpenSearch) -> OpenSearchCountsReader:
    return OpenSearchCountsReader(
        readonly, jobs_index=INDEX_NAMES.jobs, search_index_alias=INDEX_NAMES.search
    )


def counted(total: int) -> dict[str, object]:
    return search_response(total=total)


def test_count_for_source_sends_one_sub_request_per_target_to_the_right_index(
    reader: OpenSearchCountsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script(
        "msearch", msearch_response(*(counted(i) for i, _ in enumerate(ALL_TARGETS, start=1)))
    )

    results = reader.count_for_source("a", ALL_TARGETS)

    assert results == {target: Ok(i) for i, target in enumerate(ALL_TARGETS, start=1)}
    [request] = fake_client.requests
    jobs, search = INDEX_NAMES.jobs, INDEX_NAMES.search
    assert request.body == [
        {"index": search},
        queries.count_body("document_count", "a"),
        {"index": jobs},
        queries.count_body("skipped", "a"),
        {"index": jobs},
        queries.count_body("oversize", "a"),
        {"index": search},
        queries.count_body("extract_failed", "a"),
        {"index": search},
        queries.count_body("summary_pending", "a"),
    ]


def test_a_failed_sub_request_does_not_affect_the_others(
    reader: OpenSearchCountsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script(
        "msearch",
        msearch_response(
            counted(10),
            SUB_REQUEST_ERROR,
            search_response(total=3, failed_shards=1),
            search_response(total=4, timed_out=True),
            counted(5),
        ),
    )

    results = reader.count_for_source("a", ALL_TARGETS)

    assert results == {
        "document_count": Ok(10),
        "skipped": Failed("unavailable", "store", "SubRequestError"),
        "oversize": Failed("unavailable", "store", "PartialResponseError"),
        "extract_failed": Failed("timeout", "search_index", "PartialResponseError"),
        "summary_pending": Ok(5),
    }


def test_the_failed_target_follows_the_index_of_each_sub_request(
    reader: OpenSearchCountsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("msearch", msearch_response(*([SUB_REQUEST_ERROR] * 5)))

    results = reader.count_for_source("a", ALL_TARGETS)

    targets = {
        name: result.target for name, result in results.items() if isinstance(result, Failed)
    }
    assert targets == {
        "document_count": "search_index",
        "skipped": "store",
        "oversize": "store",
        "extract_failed": "search_index",
        "summary_pending": "search_index",
    }


@pytest.mark.parametrize(
    ("outcome", "kind", "error_class_name"),
    [
        (ConnectionTimeout("TIMEOUT", "x", None), "timeout", "ConnectionTimeout"),
        (TransportError(503, "x", {}), "unavailable", "TransportError"),
        (msearch_response(counted(1)), "unavailable", "ResponseShapeError"),  # サブ応答の数が違う
        ({"unexpected": True}, "unavailable", "ResponseShapeError"),
    ],
)
def test_a_failure_of_the_whole_msearch_fails_every_sub_request(
    reader: OpenSearchCountsReader,
    fake_client: FakeOpenSearchClient,
    outcome: object,
    kind: FailureKind,
    error_class_name: str,
) -> None:
    fake_client.script("msearch", outcome)

    results = reader.count_for_source("a", ("document_count", "skipped"))

    assert results == {
        "document_count": Failed(kind, "search_index", error_class_name),
        "skipped": Failed(kind, "store", error_class_name),
    }


def test_a_sub_response_without_a_total_is_a_failure(
    reader: OpenSearchCountsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("msearch", msearch_response(search_response()))

    assert reader.count_for_source("a", ("document_count",)) == {
        "document_count": Failed("unavailable", "search_index", "ResponseShapeError")
    }


def test_a_malformed_sub_response_is_a_failure(
    reader: OpenSearchCountsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("msearch", {"responses": ["not an object"]})

    assert reader.count_for_source("a", ("skipped",)) == {
        "skipped": Failed("unavailable", "store", "ResponseShapeError")
    }


def test_count_for_source_without_targets_does_not_query(
    reader: OpenSearchCountsReader, fake_client: FakeOpenSearchClient
) -> None:
    assert reader.count_for_source("a", ()) == {}
    assert fake_client.requests == []


def test_the_exact_total_is_returned_even_above_the_window(
    reader: OpenSearchCountsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("msearch", msearch_response(counted(123_456)))

    assert reader.count_for_source("a", ("document_count",)) == {"document_count": Ok(123_456)}
