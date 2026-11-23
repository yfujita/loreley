"""Reader が共有する読み取りの手順。

呼び出し(`readonly_client`)・応答の検証(`responses`)・失敗の分類(`failure`)を 1 つにつなぐ。
Reader は、どの索引に何を問い合わせるか(`queries`)だけを決める。
"""

from collections.abc import Mapping, Sequence

from loreley_api.common.results import FailureTarget, Result
from loreley_api.infrastructure.opensearch.failure import failed_from_exception, guarded_read
from loreley_api.infrastructure.opensearch.ports import Page, RecordResults
from loreley_api.infrastructure.opensearch.readonly_client import ReadOnlyOpenSearch
from loreley_api.infrastructure.opensearch.responses import parse_counted_search, parse_mget


def fetch_documents(
    readonly: ReadOnlyOpenSearch,
    *,
    index: str,
    ids: Sequence[str],
    target: FailureTarget,
    operation: str,
    source_includes: Sequence[str] | None = None,
    include_source: bool = True,
    expected_record_type: str | None = None,
) -> RecordResults:
    """`mget` で取得し、要求した ID ごとの結果にする(重複した ID は 1 つにまとめる)。

    `mget` 全体の失敗(例外・件数の異常)は、すべての ID が同じ `Failed` になる。
    """
    unique_ids = tuple(dict.fromkeys(ids))
    if not unique_ids:
        return {}
    try:
        response = readonly.mget(
            index=index,
            ids=unique_ids,
            source_includes=source_includes,
            include_source=include_source,
        )
        return parse_mget(
            response,
            unique_ids,
            target=target,
            operation=operation,
            expected_record_type=expected_record_type,
        )
    except Exception as error:
        failed = failed_from_exception(error, target, operation=operation)
        return dict.fromkeys(unique_ids, failed)


def search_page(
    readonly: ReadOnlyOpenSearch,
    *,
    index: str,
    body: Mapping[str, object],
    target: FailureTarget,
    operation: str,
) -> Result[Page]:
    """一覧の検索を実行して、1 ページ分の結果にする(`track_total_hits: true` の本文用)。"""

    def read() -> Page:
        parsed = parse_counted_search(readonly.search(index=index, body=body))
        return Page(total=parsed.total, items=parsed.hits)

    return guarded_read(operation, target, read)
