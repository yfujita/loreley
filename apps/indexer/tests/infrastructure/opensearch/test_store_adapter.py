from unittest.mock import MagicMock

import pytest
from opensearchpy import OpenSearch
from opensearchpy.exceptions import ConflictError, NotFoundError, RequestError

from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    Deleted,
    NotFound,
    OpenSearchStore,
    OpenSearchUnavailableError,
    OpenSearchUnexpectedResponseError,
    RecordFilter,
    SortKey,
    StoredDocument,
    Written,
)
from loreley_indexer.infrastructure.opensearch.store import LIST_MAX_SIZE
from loreley_indexer.infrastructure.opensearch.store_adapter import build_record_query

INDEX = "loreley-deletions"


@pytest.fixture
def client() -> MagicMock:
    mock = MagicMock(spec=OpenSearch)
    mock.indices = MagicMock()
    mock.indices.refresh.return_value = {}
    return mock


@pytest.fixture
def store(client: MagicMock) -> OpenSearchStore:
    return OpenSearchStore(client, INDEX)


def test_fetch_returns_the_record_with_its_version(
    store: OpenSearchStore, client: MagicMock
) -> None:
    client.get.return_value = {
        "found": True,
        "_source": {"status": "running"},
        "_seq_no": 3,
        "_primary_term": 1,
    }

    record = store.fetch("deletion_result-c1")

    client.get.assert_called_once_with(index=INDEX, id="deletion_result-c1")
    assert record == StoredDocument(
        id="deletion_result-c1", source={"status": "running"}, seq_no=3, primary_term=1
    )


def test_fetch_returns_none_for_a_missing_record(store: OpenSearchStore, client: MagicMock) -> None:
    client.get.side_effect = NotFoundError(404, "x", {"found": False})
    assert store.fetch("x") is None


def test_save_is_unconditional(store: OpenSearchStore, client: MagicMock) -> None:
    client.index.return_value = {"result": "created", "_seq_no": 0, "_primary_term": 1}

    outcome = store.save("deletion-s1", {"crawl_id": "c1"})

    client.index.assert_called_once_with(index=INDEX, id="deletion-s1", body={"crawl_id": "c1"})
    assert outcome == Written(seq_no=0, primary_term=1, created=True)


def test_replace_if_unchanged_sends_the_version(store: OpenSearchStore, client: MagicMock) -> None:
    client.index.return_value = {"result": "updated", "_seq_no": 5, "_primary_term": 1}

    store.replace_if_unchanged("r", {"status": "failed"}, seq_no=4, primary_term=1)

    client.index.assert_called_once_with(
        index=INDEX, id="r", body={"status": "failed"}, if_seq_no=4, if_primary_term=1
    )


def test_replace_if_unchanged_conflict(store: OpenSearchStore, client: MagicMock) -> None:
    client.index.side_effect = ConflictError(
        409, "x", {"error": {"type": "version_conflict_engine_exception"}}
    )
    assert store.replace_if_unchanged("r", {}, seq_no=1, primary_term=1) == Conflict()
    client.index.assert_called_once()  # 409 の読み直しは呼び出し側が行う(R8)


def test_delete_is_unconditional(store: OpenSearchStore, client: MagicMock) -> None:
    client.delete.return_value = {"result": "deleted"}
    assert store.delete("r") == Deleted()
    client.delete.assert_called_once_with(index=INDEX, id="r")


def test_delete_missing_record_is_not_found(store: OpenSearchStore, client: MagicMock) -> None:
    client.delete.side_effect = NotFoundError(404, "x", {"_id": "r", "result": "not_found"})
    assert store.delete("r") == NotFound()


def test_list_records_refreshes_first_then_searches_with_versions(
    store: OpenSearchStore, client: MagicMock
) -> None:
    calls: list[str] = []
    client.indices.refresh.side_effect = lambda **_: calls.append("refresh") or {}
    client.search.side_effect = lambda **_: (
        calls.append("search")
        or {
            "hits": {"hits": [{"_id": "r1", "_source": {"a": 1}, "_seq_no": 2, "_primary_term": 1}]}
        }
    )

    records = store.list_records(
        RecordFilter(equals={"source_id": "s1"}),
        [SortKey("finish_received_at"), SortKey("crawl_id", descending=True)],
        limit=50,
    )

    assert calls == ["refresh", "search"]
    client.indices.refresh.assert_called_once_with(index=INDEX)
    client.search.assert_called_once_with(
        index=INDEX,
        body={
            "query": {"bool": {"filter": [{"term": {"source_id": "s1"}}], "must_not": []}},
            "sort": [{"finish_received_at": "asc"}, {"crawl_id": "desc"}],
            "size": 50,
            "seq_no_primary_term": True,
        },
    )
    assert records == [StoredDocument(id="r1", source={"a": 1}, seq_no=2, primary_term=1)]


def test_list_records_does_not_search_when_the_refresh_is_incomplete(
    store: OpenSearchStore, client: MagicMock
) -> None:
    """一部のシャードで失敗した refresh のあとの一覧は、直前の書き込みを見落としうる。"""
    client.indices.refresh.return_value = {"_shards": {"total": 2, "successful": 1, "failed": 1}}

    with pytest.raises(OpenSearchUnavailableError) as raised:
        store.list_records(RecordFilter(), [], limit=1)

    assert raised.value.reason == "refresh_incomplete"
    client.search.assert_not_called()


@pytest.mark.parametrize("limit", [0, -1, LIST_MAX_SIZE + 1])
def test_list_records_rejects_an_unbounded_or_invalid_limit(
    store: OpenSearchStore, client: MagicMock, limit: int
) -> None:
    with pytest.raises(ValueError, match="limit"):
        store.list_records(RecordFilter(), [], limit=limit)
    client.search.assert_not_called()


def test_list_records_with_a_rejected_query_is_an_unexpected_response(
    store: OpenSearchStore, client: MagicMock
) -> None:
    client.search.side_effect = RequestError(400, "x", {"error": {"type": "parsing_exception"}})
    with pytest.raises(OpenSearchUnexpectedResponseError):
        store.list_records(RecordFilter(), [], limit=1)


def test_build_record_query_without_conditions_matches_all() -> None:
    assert build_record_query(RecordFilter()) == {"match_all": {}}


def test_build_record_query_combines_all_condition_kinds() -> None:
    query = build_record_query(
        RecordFilter(
            equals={"source_id": "s1"},
            one_of={"status": ["running", "failed"]},
            exists=("finish_received_at",),
            missing=("deletion_started_at",),
        )
    )
    assert query == {
        "bool": {
            "filter": [
                {"term": {"source_id": "s1"}},
                {"terms": {"status": ["running", "failed"]}},
                {"exists": {"field": "finish_received_at"}},
            ],
            "must_not": [{"exists": {"field": "deletion_started_at"}}],
        }
    }
