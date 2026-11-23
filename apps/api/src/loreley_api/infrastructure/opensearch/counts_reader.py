"""件数の読み取り(R-9 の EP-02・11。`msearch`。C 3.3)。

サブ要求ごとに成否が分かれる(1 つの失敗が他の件数を使えなくしない)。`msearch` 全体の失敗は、
すべてのサブ要求の失敗になる。
"""

from collections.abc import Sequence

from loreley_api.common.results import FailureTarget, Ok, Result
from loreley_api.infrastructure.opensearch import queries
from loreley_api.infrastructure.opensearch.failure import SubRequestError, failed_from_exception
from loreley_api.infrastructure.opensearch.ports import CountTarget
from loreley_api.infrastructure.opensearch.readonly_client import ReadOnlyOpenSearch
from loreley_api.infrastructure.opensearch.responses import (
    is_sub_request_error,
    parse_counted_search,
    parse_msearch,
)

# 件数の対象 → 読む先。`skipped`・`oversize` は `loreley-jobs`、残りは検索インデックス。
_STORE_TARGETS: frozenset[CountTarget] = frozenset({"skipped", "oversize"})


def _failure_target_of(target: CountTarget) -> FailureTarget:
    return "store" if target in _STORE_TARGETS else "search_index"


class OpenSearchCountsReader:
    def __init__(
        self, readonly: ReadOnlyOpenSearch, *, jobs_index: str, search_index_alias: str
    ) -> None:
        self._readonly = readonly
        self._jobs_index = jobs_index
        self._search_index_alias = search_index_alias

    def count_for_source(
        self, source_id: str, targets: Sequence[CountTarget]
    ) -> dict[CountTarget, Result[int]]:
        unique_targets = tuple(dict.fromkeys(targets))
        if not unique_targets:
            return {}
        try:
            response = self._readonly.msearch(body=self._msearch_body(source_id, unique_targets))
            sub_responses = parse_msearch(response, len(unique_targets))
        except Exception as error:
            return {
                target: failed_from_exception(
                    error, _failure_target_of(target), operation="counts.count_for_source"
                )
                for target in unique_targets
            }
        return {
            target: _count_of(sub_response, target)
            for target, sub_response in zip(unique_targets, sub_responses, strict=True)
        }

    def _msearch_body(
        self, source_id: str, targets: Sequence[CountTarget]
    ) -> list[dict[str, object]]:
        body: list[dict[str, object]] = []
        for target in targets:
            index = self._jobs_index if target in _STORE_TARGETS else self._search_index_alias
            body.append({"index": index})
            body.append(queries.count_body(target, source_id))
        return body


def _count_of(sub_response: object, target: CountTarget) -> Result[int]:
    operation = "counts.count_for_source"
    failure_target = _failure_target_of(target)
    try:
        if is_sub_request_error(sub_response):
            # `error.type`・理由文は読まない(C 5.8)。
            raise SubRequestError("sub request error")
        return Ok(parse_counted_search(sub_response).total)
    except Exception as error:
        return failed_from_exception(error, failure_target, operation=operation)
