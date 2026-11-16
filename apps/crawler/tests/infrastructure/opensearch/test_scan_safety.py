"""全件走査・一覧が、欠けた結果・不確かな結果を成功にしないこと(削除に関わるため、安全側)。

- 検索のタイムアウト・一部のシャードの失敗(`search_incomplete`)
- PIT の期限切れ(`pit_expired`)
- 並べ替えの値が同じ記録が隣り合って返った(`non_unique_sort`)
- HTTP の応答ではない opensearch-py の例外(`SerializationError` など)

実際の `OpenSearch` クライアントを、メモリ上のエミュレータ(または通信層のモック)につないで動かす。
いずれの失敗でも、PIT は閉じられる。
"""

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from opensearchpy import OpenSearch
from opensearchpy.exceptions import (
    ConnectionTimeout,
    NotFoundError,
    SerializationError,
    TransportError,
)

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.infrastructure.opensearch import (
    OpenSearchRepository,
    RecordFilter,
    RepositorySettings,
    SortKey,
)
from loreley_crawler.infrastructure.opensearch.classification import classify_failure
from tests.fakes import fake_opensearch
from tests.fakes.fake_opensearch import FakeOpenSearchTransport

INDEX = "loreley-jobs-test"
BY_DOCUMENT_ID = [SortKey("document_id")]
PARTIAL_SHARDS = {"_shards": {"total": 2, "successful": 1, "skipped": 0, "failed": 1}}


@pytest.fixture
def emulator() -> FakeOpenSearchTransport:
    return FakeOpenSearchTransport()


@pytest.fixture
def repository(emulator: FakeOpenSearchTransport) -> OpenSearchRepository:
    client = OpenSearch(hosts=["http://opensearch.invalid:9200"])
    client.transport = emulator
    repository = OpenSearchRepository(client, INDEX, RepositorySettings(scan_page_size=3))
    for n in range(1, 8):
        repository.create(f"skip-{n}", {"document_id": f"d{n}"})
    return repository


def read_all(repository: OpenSearchRepository) -> list[int]:
    with repository.scan(RecordFilter(), sort=BY_DOCUMENT_ID) as pages:
        return [len(page) for page in pages]


# --- 検索の不完全な応答(A1) ---


@pytest.mark.parametrize(
    "updates", [{"timed_out": True}, PARTIAL_SHARDS], ids=["timed_out", "failed-shards"]
)
@pytest.mark.parametrize("skip", [0, 1], ids=["first-page", "second-page"])
def test_a_scan_page_that_timed_out_or_lost_shards_fails_instead_of_returning_a_gap(
    repository: OpenSearchRepository,
    emulator: FakeOpenSearchTransport,
    updates: dict,
    skip: int,
) -> None:
    emulator.patch_response(fake_opensearch.SEARCH, updates, skip=skip)

    with pytest.raises(StoreUnavailableError) as excinfo:
        read_all(repository)

    assert excinfo.value.reason == "search_incomplete"
    assert emulator.open_pit_ids == []


@pytest.mark.parametrize(
    "updates", [{"timed_out": True}, PARTIAL_SHARDS], ids=["timed_out", "failed-shards"]
)
def test_a_list_that_timed_out_or_lost_shards_fails_instead_of_returning_a_gap(
    repository: OpenSearchRepository, emulator: FakeOpenSearchTransport, updates: dict
) -> None:
    emulator.patch_response(fake_opensearch.SEARCH, updates)

    with pytest.raises(StoreUnavailableError) as excinfo:
        repository.list_records(RecordFilter(), [SortKey("document_id")], limit=10)

    assert excinfo.value.reason == "search_incomplete"


def test_a_pit_created_on_only_some_shards_is_closed_and_the_scan_does_not_start(
    repository: OpenSearchRepository, emulator: FakeOpenSearchTransport
) -> None:
    emulator.patch_response(fake_opensearch.CREATE_PIT, PARTIAL_SHARDS)

    with (
        pytest.raises(StoreUnavailableError) as excinfo,
        repository.scan(RecordFilter(), sort=BY_DOCUMENT_ID),
    ):
        pytest.fail("the scan must not start")

    assert excinfo.value.reason == "search_incomplete"
    assert emulator.open_pit_ids == []


def test_the_search_requests_forbid_partial_results(
    repository: OpenSearchRepository, emulator: FakeOpenSearchTransport
) -> None:
    # エミュレータは、`allow_partial_*=false` がないリクエストを AssertionError にする。
    read_all(repository)
    repository.list_records(RecordFilter(), [], limit=1)

    searches = emulator.requests_of(fake_opensearch.SEARCH)
    assert searches
    assert all(r.params["allow_partial_search_results"] == "false" for r in searches)
    [create_pit] = emulator.requests_of(fake_opensearch.CREATE_PIT)
    assert create_pit.params["allow_partial_pit_creation"] == "false"


# --- PIT の期限切れ(A3) ---


def test_a_pit_that_expired_during_the_scan_is_reported_as_pit_expired(
    repository: OpenSearchRepository, emulator: FakeOpenSearchTransport
) -> None:
    read_pages = 0
    with (
        pytest.raises(StoreUnavailableError) as excinfo,
        repository.scan(RecordFilter(), sort=BY_DOCUMENT_ID) as pages,
    ):
        for _page in pages:
            read_pages += 1
            emulator.expire_pits()  # 消費側の処理が保持時間を超えた

    assert read_pages == 1
    assert excinfo.value.reason == "pit_expired"
    assert emulator.open_pit_ids == []


# --- 並べ替えの値の一意性(A2) ---


def hit(record_id: str, *sort_values: str) -> dict:
    return {
        "_id": record_id,
        "_source": {},
        "_seq_no": 1,
        "_primary_term": 1,
        "sort": list(sort_values),
    }


@pytest.fixture
def mocked_repository(real_client: OpenSearch) -> OpenSearchRepository:
    return OpenSearchRepository(real_client, INDEX, RepositorySettings(scan_page_size=3))


def scan_with_responses(
    repository: OpenSearchRepository, transport: MagicMock, *pages: list[dict]
) -> list[list[str]]:
    transport.perform_request.side_effect = [
        {"_shards": {"failed": 0}},
        {"pit_id": "PIT"},
        *({"pit_id": "PIT", "hits": {"hits": page}} for page in pages),
        {"pit_id": "PIT", "hits": {"hits": []}},
        {"pits": []},
    ]
    with repository.scan(RecordFilter(), sort=BY_DOCUMENT_ID) as result_pages:
        return [[record.id for record in page] for page in result_pages]


def test_distinct_sort_values_are_read_normally(
    mocked_repository: OpenSearchRepository, transport: MagicMock
) -> None:
    pages = scan_with_responses(
        mocked_repository,
        transport,
        [hit("a", "d1"), hit("b", "d2")],
        [hit("c", "d3")],
    )

    assert pages == [["a", "b"], ["c"]]


def test_equal_sort_values_within_a_page_fail_because_search_after_would_skip_records(
    mocked_repository: OpenSearchRepository, transport: MagicMock
) -> None:
    with pytest.raises(StoreUnexpectedResponseError) as excinfo:
        scan_with_responses(
            mocked_repository, transport, [hit("a", "d1"), hit("b", "d1"), hit("c", "d2")]
        )

    assert excinfo.value.error_type == "non_unique_sort"
    assert transport.perform_request.call_args_list[-1].args[:2] == (
        "DELETE",
        "/_search/point_in_time",
    )


def test_equal_sort_values_within_a_later_page_fail_too(
    mocked_repository: OpenSearchRepository, transport: MagicMock
) -> None:
    # 1 ページ目が正常でも、2 ページ目の中で並べ替えの値が等しければ失敗にする。
    # (ページの境目をまたぐ同値は、応答から見えず検出できない。scan.py の docstring)
    with pytest.raises(StoreUnexpectedResponseError) as excinfo:
        scan_with_responses(
            mocked_repository,
            transport,
            [hit("a", "d1"), hit("b", "d2")],
            [hit("c", "d3"), hit("d", "d3")],
        )

    assert excinfo.value.error_type == "non_unique_sort"


def test_extra_trailing_sort_values_are_ignored_by_the_uniqueness_check(
    mocked_repository: OpenSearchRepository, transport: MagicMock
) -> None:
    # 並べ替えに足された値(実機に出ない `_shard_doc` など)は、一意性の判定に使わない。
    pages = scan_with_responses(
        mocked_repository, transport, [hit("a", "d1", "0"), hit("b", "d2", "0")]
    )

    assert pages == [["a", "b"]]


def test_the_uniqueness_check_compares_only_the_requested_sort_values_not_the_whole_array(
    mocked_repository: OpenSearchRepository, transport: MagicMock
) -> None:
    # 足された値が違っても、要請した並べ替えの値(先頭 1 個)が同じなら、重複として失敗にする。
    # (全体の配列を比べると、足された値の違いで重複を見逃す。)
    with pytest.raises(StoreUnexpectedResponseError) as excinfo:
        scan_with_responses(
            mocked_repository, transport, [hit("a", "d1", "0"), hit("b", "d1", "1")]
        )

    assert excinfo.value.error_type == "non_unique_sort"


# --- HTTP の応答ではない例外(A4) ---

SERIALIZATION_ERROR = SerializationError("cannot decode SENTINEL-BODY")


@pytest.mark.parametrize(
    "operation",
    [
        lambda r: r.fetch("a"),
        lambda r: r.create("a", {}),
        lambda r: r.replace_if_unchanged("a", {}, seq_no=0, primary_term=1),
        lambda r: r.delete_if_unchanged("a", seq_no=0, primary_term=1),
        lambda r: r.list_records(RecordFilter(), [], limit=1),
        lambda r: r.delete_ids(["a"]),
    ],
    ids=["fetch", "create", "replace", "delete", "list", "delete_ids"],
)
def test_a_serialization_error_is_an_unexpected_response_not_an_uncaught_exception(
    mocked_repository: OpenSearchRepository,
    transport: MagicMock,
    operation: Callable[[OpenSearchRepository], object],
) -> None:
    transport.perform_request.side_effect = SERIALIZATION_ERROR

    with pytest.raises(StoreUnexpectedResponseError) as excinfo:
        operation(mocked_repository)

    assert excinfo.value.error_type == "serialization_error"
    assert "SENTINEL-BODY" not in str(excinfo.value)


def test_a_serialization_error_while_scanning_is_an_unexpected_response_and_closes_the_pit(
    mocked_repository: OpenSearchRepository, transport: MagicMock
) -> None:
    transport.perform_request.side_effect = [
        {"_shards": {"failed": 0}},
        {"pit_id": "PIT"},
        SERIALIZATION_ERROR,
        {"pits": []},
    ]

    with (
        pytest.raises(StoreUnexpectedResponseError) as excinfo,
        mocked_repository.scan(RecordFilter(), sort=BY_DOCUMENT_ID) as pages,
    ):
        list(pages)

    assert excinfo.value.error_type == "serialization_error"
    assert transport.perform_request.call_args_list[-1].args[:2] == (
        "DELETE",
        "/_search/point_in_time",
    )


@pytest.mark.parametrize(
    "close_error",
    [SerializationError("x"), ConnectionTimeout("TIMEOUT", "x", Exception("x"))],
    ids=["serialization", "timeout"],
)
def test_a_failure_to_close_the_pit_does_not_hide_the_failure_of_the_scan(
    mocked_repository: OpenSearchRepository, transport: MagicMock, close_error: Exception
) -> None:
    transport.perform_request.side_effect = [
        {"_shards": {"failed": 0}},
        {"pit_id": "PIT"},
        ConnectionTimeout("TIMEOUT", "x", Exception("x")),
        close_error,
    ]

    with (
        pytest.raises(StoreUnavailableError) as excinfo,
        mocked_repository.scan(RecordFilter(), sort=BY_DOCUMENT_ID) as pages,
    ):
        list(pages)

    assert excinfo.value.reason == "connection_timeout"


# --- PIT の期限切れの分類(A3) ---


@pytest.mark.parametrize(
    "info",
    [
        # 実機(3.9.0)の応答の形: 404 の `search_phase_execution_exception` の `root_cause`
        {
            "error": {
                "root_cause": [{"type": "search_context_missing_exception", "reason": "r"}],
                "type": "search_phase_execution_exception",
            }
        },
        {"error": {"type": "search_context_missing_exception", "reason": "r"}},
    ],
    ids=["root_cause", "top_level"],
)
def test_a_missing_search_context_is_classified_as_pit_expired(info: dict) -> None:
    with pytest.raises(StoreUnavailableError) as excinfo:
        classify_failure(NotFoundError(404, "search_phase_execution_exception", info))

    assert excinfo.value.reason == "pit_expired"


def test_other_search_phase_failures_are_not_pit_expired() -> None:
    info = {
        "error": {
            "root_cause": [{"type": "query_shard_exception", "reason": "r"}],
            "type": "search_phase_execution_exception",
        }
    }

    with pytest.raises(StoreUnexpectedResponseError):
        classify_failure(TransportError(400, "search_phase_execution_exception", info))
