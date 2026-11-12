"""アダプタのリクエスト形と応答の変換(MagicMock。OpenSearch 実体には接続しない)。

実機での挙動(`_seq_no` の楽観ロック、painless の max 比較、`delete_by_query` の競合など)は
U-31 として持ち越しで、ここでは確認できない。
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from opensearchpy import OpenSearch
from opensearchpy.exceptions import ConflictError, NotFoundError, RequestError, TransportError

from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    DeleteByQueryResult,
    Deleted,
    DocumentFilter,
    NotFound,
    OpenSearchSearchIndexRepository,
    OpenSearchUnavailableError,
    OpenSearchUnexpectedResponseError,
    Rejected,
    StoredDocument,
    Unchanged,
    Updated,
    Written,
)
from loreley_indexer.infrastructure.opensearch.search_index_adapter import (
    LAST_SEEN_AT_MAX_SCRIPT,
    build_document_query,
)

INDEX = "loreley-documents"
INSTANT = datetime(2026, 11, 9, 1, 0, 0, tzinfo=UTC)
INSTANT_TEXT = "2026-11-09T01:00:00.000Z"


@pytest.fixture
def client() -> MagicMock:
    mock = MagicMock(spec=OpenSearch)
    mock.indices = MagicMock()
    return mock


DELETE_BY_QUERY_TIMEOUT_SECONDS = 600.0


@pytest.fixture
def delete_by_query_client() -> MagicMock:
    return MagicMock(spec=OpenSearch)


@pytest.fixture
def repository(
    client: MagicMock, delete_by_query_client: MagicMock
) -> OpenSearchSearchIndexRepository:
    return OpenSearchSearchIndexRepository(
        client,
        INDEX,
        update_retry_on_conflict=3,
        delete_by_query_client=delete_by_query_client,
        delete_by_query_timeout_seconds=DELETE_BY_QUERY_TIMEOUT_SECONDS,
    )


def error_body(error_type: str) -> dict:
    return {"error": {"type": error_type, "reason": "r"}, "status": 0}


# --- fetch ---


def test_fetch_requests_by_id_and_returns_the_version(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.get.return_value = {
        "found": True,
        "_source": {"title": "t"},
        "_seq_no": 7,
        "_primary_term": 2,
    }

    document = repository.fetch("doc-1")

    client.get.assert_called_once_with(index=INDEX, id="doc-1")
    assert document == StoredDocument(id="doc-1", source={"title": "t"}, seq_no=7, primary_term=2)


def test_fetch_returns_none_when_the_document_is_missing(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.get.side_effect = NotFoundError(404, "x", {"_id": "doc-1", "found": False})
    assert repository.fetch("doc-1") is None


def test_fetch_raises_unavailable_when_the_index_is_missing(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.get.side_effect = NotFoundError(404, "x", error_body("index_not_found_exception"))
    with pytest.raises(OpenSearchUnavailableError):
        repository.fetch("doc-1")


def test_fetch_treats_an_unrecognizable_404_body_as_an_unexpected_response(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    # プロキシなどの JSON でない 404。ライブラリは本文の文字列をそのまま `info` に入れる。
    client.get.side_effect = NotFoundError(404, "x", "<html>SENTINEL-BODY</html>")
    with pytest.raises(OpenSearchUnexpectedResponseError) as excinfo:
        repository.fetch("doc-1")
    assert excinfo.value.error_type == "http_404"
    assert "SENTINEL-BODY" not in str(excinfo.value)


# --- fetch_for_deletion ---


def test_fetch_for_deletion_asks_only_for_the_fields_the_recheck_needs(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.get.return_value = {
        "found": True,
        "_source": {"source_id": "s1", "last_seen_at": INSTANT_TEXT},
        "_seq_no": 7,
        "_primary_term": 2,
    }

    document = repository.fetch_for_deletion("doc-1")

    client.get.assert_called_once_with(
        index=INDEX, id="doc-1", _source_includes=["source_id", "last_seen_at"]
    )
    assert document == StoredDocument(
        id="doc-1",
        source={"source_id": "s1", "last_seen_at": INSTANT_TEXT},
        seq_no=7,
        primary_term=2,
    )


def test_fetch_for_deletion_returns_none_when_the_document_is_missing(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.get.side_effect = NotFoundError(404, "x", {"_id": "doc-1", "found": False})
    assert repository.fetch_for_deletion("doc-1") is None


# --- create / replace ---


def test_create_uses_op_type_create_without_version_conditions(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.index.return_value = {"result": "created", "_seq_no": 0, "_primary_term": 1}

    outcome = repository.create("doc-1", {"title": "t"})

    client.index.assert_called_once_with(
        index=INDEX, id="doc-1", body={"title": "t"}, op_type="create"
    )
    assert outcome == Written(seq_no=0, primary_term=1, created=True)


def test_create_conflict_is_reported_as_conflict(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.index.side_effect = ConflictError(
        409, "x", error_body("version_conflict_engine_exception")
    )
    assert repository.create("doc-1", {}) == Conflict()
    client.index.assert_called_once()  # 409 の読み直しは呼び出し側が行う(R8)


def test_replace_if_unchanged_sends_the_version_read_earlier(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.index.return_value = {"result": "updated", "_seq_no": 8, "_primary_term": 2}

    outcome = repository.replace_if_unchanged("doc-1", {"title": "t2"}, seq_no=7, primary_term=2)

    client.index.assert_called_once_with(
        index=INDEX, id="doc-1", body={"title": "t2"}, if_seq_no=7, if_primary_term=2
    )
    assert outcome == Written(seq_no=8, primary_term=2, created=False)


def test_replace_if_unchanged_conflict_and_missing_document(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.index.side_effect = ConflictError(
        409, "x", error_body("version_conflict_engine_exception")
    )
    assert repository.replace_if_unchanged("d", {}, seq_no=1, primary_term=1) == Conflict()
    client.index.assert_called_once()  # 409 の読み直しは呼び出し側が行う(R8)

    client.index.side_effect = NotFoundError(404, "x", error_body("document_missing_exception"))
    assert repository.replace_if_unchanged("d", {}, seq_no=1, primary_term=1) == NotFound()


def test_document_specific_rejection_does_not_carry_the_reason(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.index.side_effect = RequestError(
        400,
        "mapper_parsing_exception",
        {"error": {"type": "mapper_parsing_exception", "reason": "SENTINEL-BODY"}},
    )
    outcome = repository.create("doc-1", {})
    assert outcome == Rejected(error_type="mapper_parsing_exception")


def test_write_during_cluster_block_raises_unavailable(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.index.side_effect = TransportError(503, "x", error_body("cluster_block_exception"))
    with pytest.raises(OpenSearchUnavailableError):
        repository.create("doc-1", {})


# --- raise_last_seen_at ---


def test_raise_last_seen_at_sends_fixed_script_with_params_and_no_upsert(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.update.return_value = {"result": "updated"}

    outcome = repository.raise_last_seen_at("doc-1", INSTANT)

    client.update.assert_called_once_with(
        index=INDEX,
        id="doc-1",
        body={
            "script": {
                "lang": "painless",
                "source": LAST_SEEN_AT_MAX_SCRIPT,
                "params": {"last_seen_at": INSTANT_TEXT},
            }
        },
        retry_on_conflict=3,
    )
    assert outcome == Updated()


def test_script_parses_instants_instead_of_comparing_strings() -> None:
    # スクリプトの文面の確認にとどまる。painless として正しく動くか(max 比較の意味)は、
    # 実機での確認(U-31(7))に委ねる。
    assert LAST_SEEN_AT_MAX_SCRIPT.count("Instant.parse") == 2
    assert "ctx.op = 'none'" in LAST_SEEN_AT_MAX_SCRIPT
    # 値はスクリプトに埋め込まず params で渡す(スクリプトのコンパイルを固定するため)。
    assert "2026" not in LAST_SEEN_AT_MAX_SCRIPT


def test_raise_last_seen_at_noop_is_unchanged(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.update.return_value = {"result": "noop"}
    assert repository.raise_last_seen_at("doc-1", INSTANT) == Unchanged()


def test_raise_last_seen_at_unknown_result_is_unexpected(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.update.return_value = {"result": "created"}
    with pytest.raises(OpenSearchUnexpectedResponseError):
        repository.raise_last_seen_at("doc-1", INSTANT)


def test_raise_last_seen_at_missing_document_is_not_found(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.update.side_effect = NotFoundError(404, "x", error_body("document_missing_exception"))
    assert repository.raise_last_seen_at("doc-1", INSTANT) == NotFound()


def test_raise_last_seen_at_missing_index_is_unavailable_not_not_found(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.update.side_effect = NotFoundError(404, "x", error_body("index_not_found_exception"))
    with pytest.raises(OpenSearchUnavailableError):
        repository.raise_last_seen_at("doc-1", INSTANT)


def test_raise_last_seen_at_conflict_after_retries_is_conflict(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.update.side_effect = ConflictError(
        409, "x", error_body("version_conflict_engine_exception")
    )
    assert repository.raise_last_seen_at("doc-1", INSTANT) == Conflict()
    client.update.assert_called_once()  # 再試行は retry_on_conflict(サーバー側)に任せ、繰り返さない


# --- delete_if_unchanged ---


def test_delete_if_unchanged_sends_the_version(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.delete.return_value = {"result": "deleted"}

    outcome = repository.delete_if_unchanged("doc-1", seq_no=7, primary_term=2)

    client.delete.assert_called_once_with(index=INDEX, id="doc-1", if_seq_no=7, if_primary_term=2)
    assert outcome == Deleted()


def test_delete_if_unchanged_conflict_and_not_found(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.delete.side_effect = ConflictError(
        409, "x", error_body("version_conflict_engine_exception")
    )
    assert repository.delete_if_unchanged("d", seq_no=1, primary_term=1) == Conflict()
    client.delete.assert_called_once()  # 409 の読み直しは呼び出し側が行う(R8)

    client.delete.side_effect = NotFoundError(404, "x", {"_id": "d", "result": "not_found"})
    assert repository.delete_if_unchanged("d", seq_no=1, primary_term=1) == NotFound()


# --- search / count / refresh ---


def test_search_document_ids_uses_search_after_with_a_document_id_sort(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.search.return_value = {"hits": {"hits": [{"_id": "a"}, {"_id": "b"}]}}

    ids = repository.search_document_ids(
        DocumentFilter(source_id="s1", last_seen_at_lt=INSTANT), page_size=2, after="9"
    )

    client.search.assert_called_once_with(
        index=INDEX,
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"source_id": "s1"}},
                        {"range": {"last_seen_at": {"lt": INSTANT_TEXT}}},
                    ]
                }
            },
            "sort": [{"document_id": "asc"}],
            "size": 2,
            "_source": False,
            "track_total_hits": False,
            "search_after": ["9"],
        },
    )
    assert ids == ["a", "b"]


def test_search_document_ids_first_page_has_no_search_after(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.search.return_value = {"hits": {"hits": []}}
    repository.search_document_ids(DocumentFilter(source_id="s1"), page_size=10, after=None)
    assert "search_after" not in client.search.call_args.kwargs["body"]


def test_search_with_a_rejected_query_is_an_unexpected_response(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.search.side_effect = RequestError(
        400, "search_phase_execution_exception", error_body("search_phase_execution_exception")
    )
    with pytest.raises(OpenSearchUnexpectedResponseError):
        repository.search_document_ids(DocumentFilter(), page_size=1, after=None)


def test_count_sends_the_query_and_returns_the_count(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.count.return_value = {"count": 42}

    count = repository.count(DocumentFilter(source_id="s1", last_seen_at_gte=INSTANT))

    client.count.assert_called_once_with(
        index=INDEX,
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"source_id": "s1"}},
                        {"range": {"last_seen_at": {"gte": INSTANT_TEXT}}},
                    ]
                }
            }
        },
    )
    assert count == 42


def test_count_existing_ids_chunks_requests_and_sums(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.count.side_effect = [{"count": 1000}, {"count": 1000}, {"count": 3}]
    ids = [f"id-{n}" for n in range(2_500)]

    assert repository.count_existing_ids(ids) == 2_003

    sent_sizes = [
        len(call.kwargs["body"]["query"]["ids"]["values"]) for call in client.count.call_args_list
    ]
    assert sent_sizes == [1000, 1000, 500]


@pytest.mark.parametrize(
    ("num_ids", "expected_chunk_sizes"),
    [(1, [1]), (999, [999]), (1000, [1000]), (1001, [1000, 1]), (2000, [1000, 1000])],
)
def test_count_existing_ids_splits_at_the_chunk_boundary(
    repository: OpenSearchSearchIndexRepository,
    client: MagicMock,
    num_ids: int,
    expected_chunk_sizes: list[int],
) -> None:
    client.count.side_effect = [{"count": size} for size in expected_chunk_sizes]

    total = repository.count_existing_ids([f"id-{n}" for n in range(num_ids)])

    sent_sizes = [
        len(call.kwargs["body"]["query"]["ids"]["values"]) for call in client.count.call_args_list
    ]
    assert sent_sizes == expected_chunk_sizes
    assert total == num_ids


def test_count_existing_ids_without_ids_does_not_call_opensearch(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    assert repository.count_existing_ids([]) == 0
    client.count.assert_not_called()


def test_refresh_refreshes_the_index(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.indices.refresh.return_value = {"_shards": {"total": 2, "successful": 2, "failed": 0}}

    repository.refresh()

    client.indices.refresh.assert_called_once_with(index=INDEX)


def test_refresh_without_the_shards_section_is_treated_as_a_success(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    client.indices.refresh.return_value = {}

    repository.refresh()


def test_refresh_with_a_failed_shard_is_reported_as_unavailable(
    repository: OpenSearchSearchIndexRepository, client: MagicMock
) -> None:
    """一部のシャードで失敗した refresh は反映が不完全。成功とみなすと古い件数で削除を判断する。"""
    client.indices.refresh.return_value = {"_shards": {"total": 2, "successful": 1, "failed": 1}}

    with pytest.raises(OpenSearchUnavailableError) as raised:
        repository.refresh()

    assert raised.value.reason == "refresh_incomplete"


# --- delete_by_query ---


def test_delete_by_query_proceeds_on_conflicts_and_reports_counts(
    repository: OpenSearchSearchIndexRepository, delete_by_query_client: MagicMock
) -> None:
    delete_by_query_client.delete_by_query.return_value = {
        "deleted": 5,
        "version_conflicts": 2,
        "failures": [{"x": 1}],
    }

    result = repository.delete_by_query(DocumentFilter(source_id="s1"))

    delete_by_query_client.delete_by_query.assert_called_once_with(
        index=INDEX,
        body={"query": {"bool": {"filter": [{"term": {"source_id": "s1"}}]}}},
        conflicts="proceed",
        request_timeout=DELETE_BY_QUERY_TIMEOUT_SECONDS,
    )
    assert result == DeleteByQueryResult(deleted=5, version_conflicts=2, failure_count=1)


def test_delete_by_query_uses_its_own_client_and_never_the_general_one(
    repository: OpenSearchSearchIndexRepository,
    client: MagicMock,
    delete_by_query_client: MagicMock,
) -> None:
    """再送しない専用クライアントを通すこと(通常のクライアントは timeout で再送する。P4)。"""
    delete_by_query_client.delete_by_query.return_value = {"deleted": 0}

    repository.delete_by_query(DocumentFilter(source_id="s1"))

    client.delete_by_query.assert_not_called()


def test_other_calls_do_not_use_the_delete_by_query_client(
    repository: OpenSearchSearchIndexRepository,
    client: MagicMock,
    delete_by_query_client: MagicMock,
) -> None:
    client.count.return_value = {"count": 1}
    client.get.return_value = {"found": True, "_source": {}, "_seq_no": 0, "_primary_term": 1}
    client.indices.refresh.return_value = {}

    repository.count(DocumentFilter(source_id="s1"))
    repository.fetch("d1")
    repository.refresh()

    assert delete_by_query_client.method_calls == []


def test_delete_by_query_requires_a_source_to_avoid_deleting_everything(
    repository: OpenSearchSearchIndexRepository, delete_by_query_client: MagicMock
) -> None:
    with pytest.raises(ValueError, match="source_id"):
        repository.delete_by_query(DocumentFilter(summary_status="pending"))
    delete_by_query_client.delete_by_query.assert_not_called()


# --- query building ---


def test_build_document_query_without_conditions_matches_all() -> None:
    assert build_document_query(DocumentFilter()) == {"match_all": {}}


def test_build_document_query_combines_all_conditions() -> None:
    query = build_document_query(
        DocumentFilter(
            source_id="s1",
            last_seen_at_gte=INSTANT,
            last_seen_at_lt=datetime(2026, 11, 10, tzinfo=UTC),
            summary_status="pending",
        )
    )
    assert query == {
        "bool": {
            "filter": [
                {"term": {"source_id": "s1"}},
                {"term": {"summary_status": "pending"}},
                {
                    "range": {
                        "last_seen_at": {"gte": INSTANT_TEXT, "lt": "2026-11-10T00:00:00.000Z"}
                    }
                },
            ]
        }
    }
