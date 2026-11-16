"""opensearch-py の呼び出しと、応答から結果への変換(Repository の実装が共有する)。

`TransportError` だけでなく、`OpenSearchException` 全体を捕捉して `classify_failure` を通す
(`SerializationError` など、HTTP の応答ではない例外が分類を素通りしないように)。
"""

from collections.abc import Callable, Mapping
from typing import Any

from opensearchpy import OpenSearch
from opensearchpy.exceptions import OpenSearchException

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.infrastructure.opensearch.classification import classify_failure
from loreley_crawler.infrastructure.opensearch.results import (
    AlreadyExists,
    Conflict,
    CreateOutcome,
    Deleted,
    DeleteOutcome,
    NotFound,
    ReplaceOutcome,
    StoredRecord,
    Written,
)

# 検索を、一部のシャードの失敗やタイムアウトで欠けた結果のまま成功にしない(OpenSearch の検索は
# 既定で部分結果を返す)。欠けた一覧から削除対象を判断すると、取りこぼし・誤削除につながる。
STRICT_SEARCH_PARAMS = {"allow_partial_search_results": "false"}


def to_record(record_id: str, response: Mapping[str, Any]) -> StoredRecord:
    """取得の応答・検索の hit(どちらも `_source`・`_seq_no`・`_primary_term` を持つ)から作る。"""
    return StoredRecord(
        id=record_id,
        source=response["_source"],
        seq_no=response["_seq_no"],
        primary_term=response["_primary_term"],
    )


def fetch_record(client: OpenSearch, index_name: str, record_id: str) -> StoredRecord | None:
    if not record_id:
        # 実クライアントは空の ID を `ValueError` にする(`OpenSearchException` ではない)。
        # 記録は存在しないので、メモリ上の実装と同じく None を返す。
        return None
    try:
        response = client.get(index=index_name, id=record_id)
    except OpenSearchException as error:
        outcome = classify_failure(error)
        if isinstance(outcome, NotFound):
            return None
        raise unexpected_response_error(outcome) from None
    return to_record(record_id, response)


def create_record(
    client: OpenSearch, index_name: str, record_id: str, body: Mapping[str, Any]
) -> CreateOutcome:
    try:
        response = client.index(index=index_name, id=record_id, body=dict(body), op_type="create")
    except OpenSearchException as error:
        outcome = classify_failure(error)
        if isinstance(outcome, Conflict):
            return AlreadyExists()
        raise unexpected_response_error(outcome) from None
    return Written(seq_no=response["_seq_no"], primary_term=response["_primary_term"])


def replace_record(
    client: OpenSearch,
    index_name: str,
    record_id: str,
    body: Mapping[str, Any],
    *,
    seq_no: int,
    primary_term: int,
) -> ReplaceOutcome:
    try:
        response = client.index(
            index=index_name,
            id=record_id,
            body=dict(body),
            if_seq_no=seq_no,
            if_primary_term=primary_term,
        )
    except OpenSearchException as error:
        return classify_failure(error)
    return Written(seq_no=response["_seq_no"], primary_term=response["_primary_term"])


def delete_record(
    client: OpenSearch, index_name: str, record_id: str, *, seq_no: int, primary_term: int
) -> DeleteOutcome:
    try:
        client.delete(
            index=index_name, id=record_id, if_seq_no=seq_no, if_primary_term=primary_term
        )
    except OpenSearchException as error:
        return classify_failure(error)
    return Deleted()


def run_query(call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """検索・refresh・バルクなど。`Conflict`・`NotFound` は、想定外の応答として扱う。"""
    try:
        return call()
    except OpenSearchException as error:
        raise unexpected_response_error(classify_failure(error)) from None


def has_failed_shards(response: Mapping[str, Any]) -> bool:
    return response.get("_shards", {}).get("failed", 0) > 0


def ensure_search_complete(response: Mapping[str, Any]) -> None:
    """検索がタイムアウトした・一部のシャードで失敗したときは、全体の異常にする(`search_incomplete`)。

    応答に `timed_out`・`_shards` がなければ、完全として扱う。
    """
    if response.get("timed_out") is True or has_failed_shards(response):
        raise StoreUnavailableError("search_incomplete")


def refresh_index(client: OpenSearch, index_name: str) -> None:
    """`refresh` する。一部のシャードで失敗していたら、反映が不完全なので全体の異常にする。

    反映されない refresh を成功とみなすと、古い一覧から削除を判断してしまうため。
    応答に `_shards` がなければ、成功として扱う。
    """
    response = run_query(lambda: client.indices.refresh(index=index_name))
    if has_failed_shards(response):
        raise StoreUnavailableError("refresh_incomplete")


def unexpected_response_error(outcome: Conflict | NotFound) -> StoreUnexpectedResponseError:
    """その操作では起こらない結果(GET の 409 など)。想定外の応答として扱う。"""
    return StoreUnexpectedResponseError(type(outcome).__name__.lower())
