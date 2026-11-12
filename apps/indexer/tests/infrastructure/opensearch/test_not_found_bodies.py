"""404 の本文の種類ごとの扱い(例外経路)。削除の安全性に直結するので、固定する。

存在しない文書の取得・削除・更新は、通常の結果(`NotFound`・`None`)として扱う。一方、索引の不在は
全体異常で、削除の判断・実行を止める(索引が消えたのを「文書がない」と読み違えて進めない)。
本文が JSON でない(プロキシ・Ingress の 404)ものは、文書の不在とも索引の不在とも言えないので、
`Rejected("http_404")`(取得は想定外の応答)にして、削除の executor の有限回の再試行に任せる。

通信層(`transport`)だけをモックにし、実際の `OpenSearch` クライアントのメソッドを通す。
本文が JSON でない場合に実際のライブラリがどうなるかは `test_log_leak.py`(ローカルの HTTP スタブ)。
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError

from loreley_indexer.infrastructure.opensearch import (
    NotFound,
    OpenSearchSearchIndexRepository,
    OpenSearchStore,
    OpenSearchUnavailableError,
    OpenSearchUnexpectedResponseError,
    Rejected,
)

DOCUMENT_ID = "doc-1"
INSTANT = datetime(2026, 11, 9, tzinfo=UTC)

BODIES: dict[str, Any] = {
    "found_false": {"_id": DOCUMENT_ID, "found": False},
    "result_not_found": {"_id": DOCUMENT_ID, "result": "not_found"},
    "document_missing": {"error": {"type": "document_missing_exception", "reason": "r"}},
    "index_not_found": {"error": {"type": "index_not_found_exception", "reason": "r"}},
    "html": "<html><body>404 Not Found</body></html>",
    "empty_object": {},
}
# 本文ごとの結果。`not_found`: 文書がない / `unavailable`: 全体異常 / `rejected`: 想定外の 404。
EXPECTED_KIND = {
    "found_false": "not_found",
    "result_not_found": "not_found",
    "document_missing": "not_found",
    "index_not_found": "unavailable",
    "html": "rejected",
    "empty_object": "rejected",
}


def make_calls(real_client: OpenSearch) -> dict[str, tuple[Callable[[], Any], bool]]:
    """操作名 → (呼び出し, 取得か)。取得は `NotFound` が `None` になり、`Rejected` が例外になる。"""
    repository = OpenSearchSearchIndexRepository(
        real_client,
        "docs",
        update_retry_on_conflict=3,
        delete_by_query_client=real_client,
        delete_by_query_timeout_seconds=1.0,
    )
    store = OpenSearchStore(real_client, "records")
    return {
        "repository.fetch": (lambda: repository.fetch(DOCUMENT_ID), True),
        "repository.fetch_for_deletion": (lambda: repository.fetch_for_deletion(DOCUMENT_ID), True),
        "store.fetch": (lambda: store.fetch(DOCUMENT_ID), True),
        "repository.delete_if_unchanged": (
            lambda: repository.delete_if_unchanged(DOCUMENT_ID, seq_no=1, primary_term=1),
            False,
        ),
        "store.delete": (lambda: store.delete(DOCUMENT_ID), False),
        "repository.raise_last_seen_at": (
            lambda: repository.raise_last_seen_at(DOCUMENT_ID, INSTANT),
            False,
        ),
    }


CALL_NAMES = list(make_calls(MagicMock()))


@pytest.mark.parametrize("body_name", BODIES)
@pytest.mark.parametrize("call_name", CALL_NAMES)
def test_a_404_is_classified_by_its_body_the_same_way_for_every_call(
    real_client: OpenSearch, transport: MagicMock, call_name: str, body_name: str
) -> None:
    transport.perform_request.side_effect = NotFoundError(404, "x", BODIES[body_name])
    call, is_fetch = make_calls(real_client)[call_name]
    kind = EXPECTED_KIND[body_name]

    if kind == "unavailable":
        with pytest.raises(OpenSearchUnavailableError) as unavailable:
            call()
        assert unavailable.value.reason == "index_not_found_exception"
    elif kind == "not_found" and is_fetch:
        assert call() is None
    elif kind == "not_found":
        assert call() == NotFound()
    elif is_fetch:
        with pytest.raises(OpenSearchUnexpectedResponseError) as unexpected:
            call()
        assert unexpected.value.error_type == "http_404"
    else:
        assert call() == Rejected("http_404")
