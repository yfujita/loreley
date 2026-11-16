"""全件走査(PIT + `search_after`。module 4.8。CM-P-24。architecture 3.1)。

流れ: 対象の索引を refresh -> PIT を開く -> `search_after` でページ単位に読む -> PIT を閉じる。
PIT は、最後まで読み終えたとき・途中で失敗したとき・呼び出し側が途中でやめたときのいずれも
閉じる(`with` を抜けるとき、または最後のページを読み終えたとき。閉じる処理は何度呼んでもよい)。
PIT を閉じられなくても(接続の異常など)、走査の結果は変えない。PIT は保持時間(仮値)で
期限切れになる。

- **PIT の保持時間と処理時間**: PIT は、ページを 1 つ検索するたびに保持時間ぶん延長される。
  呼び出し側が 1 ページの処理に保持時間を超える時間をかけると、次のページの検索で PIT が
  期限切れになり、`StoreUnavailableError("pit_expired")` になる(走査をやり直す)。
- **欠けた結果を成功にしない**: PIT の作成・検索とも、一部のシャードの失敗は許さず
  (`allow_partial_pit_creation=false`・`allow_partial_search_results=false`)、応答の
  `timed_out`・`_shards.failed` も確かめて、`StoreUnavailableError("search_incomplete")` にする。
  欠けた一覧から削除対象を判断すると、取りこぼし・誤削除につながるため。
- **並べ替えの一意性**: 呼び出し側が一意な組(第一候補は `document_id`)を渡す。PIT の暗黙の
  タイブレーク `_shard_doc` は使わない(OpenSearch 3.9.0 の実機では、応答の `sort` に
  追加されなかった)。安全装置として、1 ページの中で隣り合う記録の並べ替えの値が等しければ、
  `StoreUnexpectedResponseError("non_unique_sort")` にする(`search_after` が同じ値の記録を
  取りこぼすため)。ページの境目をまたぐ同値(最後の記録と、次のページに来るはずの記録)は、
  応答からは見えないので検出できない。したがって一意性の担保は呼び出し側の責任で、`sort` の
  最後を、記録ごとに一意な `document_id` にすること(P4 の `jobs/records`、P6 の `crawl`)。
"""

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from itertools import pairwise
from typing import Any

from opensearchpy import OpenSearch
from opensearchpy.exceptions import OpenSearchException

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.infrastructure.opensearch.client_calls import (
    STRICT_SEARCH_PARAMS,
    ensure_search_complete,
    has_failed_shards,
    refresh_index,
    run_query,
    to_record,
)
from loreley_crawler.infrastructure.opensearch.queries import RecordFilter, SortKey
from loreley_crawler.infrastructure.opensearch.query_builder import (
    build_record_query,
    build_sort,
)
from loreley_crawler.infrastructure.opensearch.repository import RecordPages
from loreley_crawler.infrastructure.opensearch.settings import RepositorySettings

logger = logging.getLogger(__name__)


class _PitSession:
    """開いた PIT。応答で ID が変わりうるので最後の ID を持ち、閉じる処理は 1 回だけ行う。"""

    def __init__(self, client: OpenSearch, pit_id: str) -> None:
        self._client = client
        self.pit_id = pit_id
        self._is_closed = False

    def close(self) -> None:
        if self._is_closed:
            return
        self._is_closed = True
        try:
            self._client.delete_pit(body={"pit_id": [self.pit_id]})
        except OpenSearchException as error:
            # 閉じられなくても、保持時間で期限切れになる。走査の結果は変えず、元の例外
            # (走査の失敗など)も覆わない。メッセージには応答の本文が入りうるので、
            # クラス名だけを残す。
            logger.warning("failed to close the point in time: error=%s", type(error).__name__)


@contextmanager
def scan_records(
    client: OpenSearch,
    index_name: str,
    record_filter: RecordFilter,
    sort: Sequence[SortKey],
    settings: RepositorySettings,
) -> Iterator[RecordPages]:
    refresh_index(client, index_name)
    session = _open_pit(client, index_name, settings)
    try:
        yield _read_pages(client, session, record_filter, sort, settings)
    finally:
        session.close()


def _open_pit(client: OpenSearch, index_name: str, settings: RepositorySettings) -> _PitSession:
    response = run_query(
        lambda: client.create_pit(
            index=index_name,
            params={
                "keep_alive": f"{settings.scan_pit_keep_alive_seconds}s",
                "allow_partial_pit_creation": "false",
                "request_timeout": settings.scan_request_timeout_seconds,
            },
        )
    )
    session = _PitSession(client, response["pit_id"])
    if has_failed_shards(response):
        session.close()
        raise StoreUnavailableError("search_incomplete")
    return session


def _read_pages(
    client: OpenSearch,
    session: _PitSession,
    record_filter: RecordFilter,
    sort: Sequence[SortKey],
    settings: RepositorySettings,
) -> RecordPages:
    base_body: dict[str, Any] = {
        "query": build_record_query(record_filter),
        "sort": build_sort(sort),
        "size": settings.scan_page_size,
        "seq_no_primary_term": True,
    }
    search_params = {
        **STRICT_SEARCH_PARAMS,
        "request_timeout": settings.scan_request_timeout_seconds,
    }
    sort_width = len(sort)
    search_after: list[Any] | None = None
    try:
        while True:
            body = {
                **base_body,
                "pit": {
                    "id": session.pit_id,
                    "keep_alive": f"{settings.scan_pit_keep_alive_seconds}s",
                },
            }
            if search_after is not None:
                body["search_after"] = search_after
            response = run_query(
                lambda body=body: client.search(body=body, params=dict(search_params))
            )
            ensure_search_complete(response)
            session.pit_id = response.get("pit_id", session.pit_id)
            hits = response["hits"]["hits"]
            if not hits:
                return
            _ensure_sort_values_are_unique(hits, sort_width)
            search_after = hits[-1]["sort"]
            yield [to_record(hit["_id"], hit) for hit in hits]
    finally:
        session.close()


def _ensure_sort_values_are_unique(hits: Sequence[dict[str, Any]], sort_width: int) -> None:
    """ページ内で隣り合う記録の並べ替えの値が等しければ、失敗にする(`non_unique_sort`)。

    前のページの最後の記録との比較はしない。`search_after` は排他(その値より後ろだけを返す)なので、
    次のページの最初の記録が前のページの最後と等しくなることはなく、比べても発火しない。
    """
    keys = [list(hit["sort"][:sort_width]) for hit in hits]
    if any(left == right for left, right in pairwise(keys)):
        raise StoreUnexpectedResponseError("non_unique_sort")
