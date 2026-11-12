"""検索インデックスと Store 層のアダプタが共有する、opensearch-py の呼び出しと結果の変換。"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from opensearchpy import OpenSearch
from opensearchpy.exceptions import TransportError

from loreley_indexer.infrastructure.opensearch.classification import classify_failure
from loreley_indexer.infrastructure.opensearch.errors import (
    OpenSearchUnavailableError,
    OpenSearchUnexpectedResponseError,
)
from loreley_indexer.infrastructure.opensearch.results import (
    Conflict,
    Deleted,
    DeleteOutcome,
    NotFound,
    Rejected,
    StoredDocument,
    WriteOutcome,
    Written,
)


def fetch_stored_document(
    client: OpenSearch,
    index_name: str,
    document_id: str,
    *,
    source_includes: Sequence[str] | None = None,
) -> StoredDocument | None:
    """ID で取得する。`source_includes` を指定すると、その項目だけを `source` に含める。"""
    parameters: dict[str, Any] = {}
    if source_includes is not None:
        parameters["_source_includes"] = list(source_includes)
    try:
        response = client.get(index=index_name, id=document_id, **parameters)
    except TransportError as error:
        outcome = classify_failure(error)
        if isinstance(outcome, NotFound):
            return None
        raise unexpected_response_error(outcome) from None
    return StoredDocument(
        id=document_id,
        source=response["_source"],
        seq_no=response["_seq_no"],
        primary_term=response["_primary_term"],
    )


def index_document(
    client: OpenSearch,
    index_name: str,
    document_id: str,
    source: Mapping[str, Any],
    **conditions: Any,
) -> WriteOutcome:
    """`conditions` は `op_type`、または `if_seq_no`・`if_primary_term`。"""
    try:
        response = client.index(index=index_name, id=document_id, body=dict(source), **conditions)
    except TransportError as error:
        return classify_failure(error)
    return Written(
        seq_no=response["_seq_no"],
        primary_term=response["_primary_term"],
        created=response["result"] == "created",
    )


def delete_document(
    client: OpenSearch, index_name: str, document_id: str, **conditions: Any
) -> DeleteOutcome:
    try:
        client.delete(index=index_name, id=document_id, **conditions)
    except TransportError as error:
        return classify_failure(error)
    return Deleted()


def run_query(call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """検索・件数・refresh など。全体異常以外の失敗は、クエリの誤りなどの想定外として扱う。"""
    try:
        return call()
    except TransportError as error:
        raise unexpected_response_error(classify_failure(error)) from None


def refresh_index(client: OpenSearch, index_name: str) -> None:
    """`refresh` する。一部のシャードで失敗していたら、反映が不完全なので全体異常にする。

    反映されない refresh を成功とみなすと、古い件数・一覧から削除を判断してしまうため。
    応答に `_shards` がなければ、従来どおり成功として扱う。
    """
    response = run_query(lambda: client.indices.refresh(index=index_name))
    if response.get("_shards", {}).get("failed", 0) > 0:
        raise OpenSearchUnavailableError("refresh_incomplete")


def unexpected_response_error(
    outcome: Conflict | NotFound | Rejected,
) -> OpenSearchUnexpectedResponseError:
    if isinstance(outcome, Rejected):
        return OpenSearchUnexpectedResponseError(outcome.error_type)
    return OpenSearchUnexpectedResponseError(type(outcome).__name__.lower())
