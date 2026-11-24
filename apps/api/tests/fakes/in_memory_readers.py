"""OpenSearch の Reader(Protocol)の偽物(D 7.2。C 11章 16)。

`services`・`routers` のテストで、Reader の下の OpenSearch を持ち込まずに、読み取りの結果を
作る。**検索は古いスナップショット、`mget` はリアルタイム**を再現する(`stalled` の偽陽性が
出ないことの確認用):

- `get_locks`・`get_jobs`・`get`(ソース)・`get_result` は、書き込んだ直後の状態を読む(`mget`)。
- 一覧・集計・件数(`sources.list_all`、`jobs.list_jobs`・`latest_by_source`・`latest_crawl_id`・
  `list_skipped`・`list_oversize`、検索インデックスの全メソッド、`counts`)は、`refresh_search()` を
  呼んだ時点の状態を読む(検索。最大で約 1 秒古い)。書き込みだけでは検索に現れない。

障害の注入(`behavior` は `FakeBehavior`):
- 呼び出し全体の失敗: `readers.behavior.inject("jobs.get_locks", failed, times=None)`
  (操作名は `sources.list_all`・`sources.get`・`jobs.get_locks`・`jobs.get_jobs`・
  `jobs.list_jobs`・`jobs.latest_by_source`・`jobs.latest_crawl_id`・`jobs.list_skipped`・
  `jobs.list_oversize`・`deletions.get_result`・`search_index.count_by_source`・
  `search_index.list_extract_failed`・`search_index.list_summary_pending`・
  `search_index.existing_ids`・`counts.count_for_source`・`cluster.read`)。`mget` の操作では、
  すべての ID が同じ失敗になる(本物の Reader と同じ)。`counts.count_for_source` は、すべての
  対象が同じ失敗になる(`msearch` 全体の失敗)。
- 文書単位の失敗(`mget` だけ): `readers.fail_document("jobs.get_locks", "source-b", failed)`。
  他の文書は読める。件数のサブ要求単位の失敗は、対象の名前で指定する:
  `readers.fail_document("counts.count_for_source", "summary_pending", failed)`。
- 読みと読みの間の書き込み: `readers.behavior.before("jobs.get_locks", callback)`。
- 読んだ呼び出しは `readers.behavior.calls_of(...)` に残る(`key` は ID、複数ならカンマ区切り)。
  操作名は `OPERATIONS` にあるものだけで、それ以外(打ち間違い)は `ValueError`。

並べ替えの注意: 一覧の並べ替え・絞り込み・ページの切り出しは、この偽物が自前で実装している。
`services`・`routers` のテストで確かめられるのは、その結果を取りこぼさず・並べ直さずに通すことまで。
実クエリの `sort`(同順位の決め方を含む)が意図どおりかは、この偽物では確かめられない。
`infrastructure/opensearch/test_queries.py`(クエリの組み立て)と、P7 の実機のスモークで確かめる。
"""

import copy
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from loreley_api.common.results import Failed, Ok, Result
from loreley_api.common.timestamps import parse_instant
from loreley_api.infrastructure.opensearch import (
    ClusterSnapshot,
    CountTarget,
    JobListQuery,
    Page,
    PageRequest,
    RecordResults,
    SourceJobsSummary,
    StoredRecord,
)
from loreley_api.infrastructure.opensearch.ports import (
    JOB_BRIEF_FIELDS,
    LOCK_FIELDS,
    MAX_EXISTENCE_IDS,
)
from loreley_api.infrastructure.opensearch.queries import (
    EXTRACT_FAILED_FIELDS,
    OVERSIZE_FIELDS,
    SKIPPED_FIELDS,
    SUMMARY_PENDING_FIELDS,
)
from tests.fakes.behavior import FakeBehavior

STORE_UNAVAILABLE = Failed(kind="unavailable", target="store", error_class_name="ConnectionError")
STORE_TIMEOUT = Failed(kind="timeout", target="store", error_class_name="ConnectionTimeout")
SEARCH_UNAVAILABLE = Failed(
    kind="unavailable", target="search_index", error_class_name="ConnectionError"
)
SEARCH_TIMEOUT = Failed(kind="timeout", target="search_index", error_class_name="ConnectionTimeout")

DELETION_RESULT_FIELDS = (
    "record_type",
    "status",
    "reason",
    "reason_detail",
    "forced",
    "target_count",
    "denominator",
    "deleted_count",
    "ended_at",
)

# `behavior` の操作名(`{Reader の属性名}.{メソッド名}`)。打ち間違いを `ValueError` にするための
# 一覧で、Protocol のメソッドと過不足がないことは `test_in_memory_readers_protocols.py` で確かめる。
OPERATIONS = frozenset(
    {
        "sources.list_all",
        "sources.get",
        "jobs.latest_by_source",
        "jobs.get_locks",
        "jobs.get_jobs",
        "jobs.list_jobs",
        "jobs.latest_crawl_id",
        "jobs.list_skipped",
        "jobs.list_oversize",
        "deletions.get_result",
        "search_index.count_by_source",
        "search_index.list_extract_failed",
        "search_index.list_summary_pending",
        "search_index.existing_ids",
        "counts.count_for_source",
        "cluster.read",
    }
)

type Document = dict[str, Any]


class _Documents:
    """4 つの索引の文書(`_id` → `_source`)。`sources`・`jobs`・`deletions`・`search_index` が
    索引に対応する(`search_index` の `_id` は `document_id`)。
    """

    def __init__(self) -> None:
        self.sources: dict[str, Document] = {}
        self.jobs: dict[str, Document] = {}
        self.deletions: dict[str, Document] = {}
        self.search_index: dict[str, Document] = {}

    def copy(self) -> "_Documents":
        snapshot = _Documents()
        snapshot.sources = copy.deepcopy(self.sources)
        snapshot.jobs = copy.deepcopy(self.jobs)
        snapshot.deletions = copy.deepcopy(self.deletions)
        snapshot.search_index = copy.deepcopy(self.search_index)
        return snapshot


def _project(source: Mapping[str, Any], fields: Sequence[str] | None) -> Document:
    """`_source_includes` の再現。`finish_notice.send_started_at` のような入れ子のパスも読む。"""
    if fields is None:
        return copy.deepcopy(dict(source))
    projected: Document = {}
    for path in fields:
        _copy_path(source, projected, path.split("."))
    return projected


def _copy_path(source: Mapping[str, Any], target: Document, path: list[str]) -> None:
    head, *rest = path
    if head not in source:
        return
    if not rest:
        target[head] = copy.deepcopy(source[head])
        return
    child = source[head]
    if isinstance(child, Mapping):
        _copy_path(child, target.setdefault(head, {}), rest)


class _Store:
    """Reader の偽物と `InMemoryReaders` が共有する状態。"""

    def __init__(self) -> None:
        self.behavior = FakeBehavior(OPERATIONS)
        self.cluster_snapshot: ClusterSnapshot | None = None
        # `mget` が読む(リアルタイム)。
        self.live = _Documents()
        # 検索が読む(最後の `refresh_search()` の時点の状態)。
        self.searchable = _Documents()
        self.document_failures: dict[tuple[str, str], Failed] = {}


class InMemoryReaders:
    def __init__(self) -> None:
        self._store = _Store()
        self.behavior = self._store.behavior
        self.sources = _InMemorySourcesReader(self._store)
        self.jobs = _InMemoryJobsReader(self._store)
        self.deletions = _InMemoryDeletionsReader(self._store)
        self.search_index = _InMemorySearchIndexReader(self._store)
        self.counts = _InMemoryCountsReader(self._store)
        self.cluster = _InMemoryClusterReader(self._store)

    @property
    def cluster_snapshot(self) -> ClusterSnapshot | None:
        return self._store.cluster_snapshot

    @cluster_snapshot.setter
    def cluster_snapshot(self, snapshot: ClusterSnapshot | None) -> None:
        self._store.cluster_snapshot = snapshot

    # --- 文書の書き込み(テストの準備。`mget` にはすぐ見える) ---

    def put_source(self, source_id: str, **fields: Any) -> None:
        self._store.live.sources[source_id] = {"status": "active", **fields}

    def remove_source(self, source_id: str) -> None:
        self._store.live.sources.pop(source_id, None)

    def put_skip(self, source_id: str, document_id: str, **fields: Any) -> None:
        """`record_type=skip` の記録(`skip-{source_id}-{document_id}`)。"""
        self._store.live.jobs[f"skip-{source_id}-{document_id}"] = {
            "record_type": "skip",
            "source_id": source_id,
            "document_id": document_id,
            **fields,
        }

    def put_oversize(self, source_id: str, document_id: str, **fields: Any) -> None:
        """`record_type=oversize` の記録(`oversize-{source_id}-{document_id}`)。"""
        self._store.live.jobs[f"oversize-{source_id}-{document_id}"] = {
            "record_type": "oversize",
            "source_id": source_id,
            "document_id": document_id,
            **fields,
        }

    def put_jobs_document(self, document_id: str, **source: Any) -> None:
        """`loreley-jobs` の文書を、`_source` をそのままで書く(読めない値の再現用)。"""
        self._store.live.jobs[document_id] = source

    def put_document(self, document_id: str, *, source_id: str, **fields: Any) -> None:
        """検索インデックスの文書(`_id` は `document_id`)。`index_status` など。"""
        self._store.live.search_index[document_id] = {"source_id": source_id, **fields}

    def put_job(self, job_id: str, *, source_id: str, status: str, **fields: Any) -> None:
        self._store.live.jobs[job_id] = {
            "record_type": "job",
            "source_id": source_id,
            "job_type": "crawl",
            "status": status,
            **fields,
        }

    def update_job(self, job_id: str, **fields: Any) -> None:
        self._store.live.jobs[job_id].update(fields)

    def put_lock(self, source_id: str, **fields: Any) -> None:
        self._store.live.jobs[f"lock-{source_id}"] = {
            "record_type": "lock",
            "source_id": source_id,
            **fields,
        }

    def remove_lock(self, source_id: str) -> None:
        self._store.live.jobs.pop(f"lock-{source_id}", None)

    def put_deletion_result(self, job_id: str, **fields: Any) -> None:
        self._store.live.deletions[f"deletion_result-{job_id}"] = {
            "record_type": "deletion_result",
            **fields,
        }

    def refresh_search(self) -> None:
        """今の状態を、検索から見えるようにする(`refresh`)。以後の書き込みは、次の呼び出しまで見えない。"""
        self._store.searchable = self._store.live.copy()

    # --- 障害の注入 ---

    def fail_document(self, operation: str, document_key: str, failed: Failed) -> None:
        """`mget` の `operation` で、1 件の文書だけを失敗にする。

        `document_key` は ID(ロックは `source_id`)。他の文書は読める。
        """
        self._store.document_failures[(operation, document_key)] = failed


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_ONE_MILLISECOND = timedelta(milliseconds=1)


def _page_of(
    documents: Mapping[str, Document],
    matches: Callable[[Document], bool],
    *,
    sort_field: str,
    fields: Sequence[str],
    page: PageRequest,
) -> Page:
    """絞り込み・並べ替え(`sort_field`。同順位は `_id` の昇順)・ページの切り出し。

    `total` は絞り込み後の総件数(窓を超えても正確)。日時は同じ書式(UTC ミリ秒)の文字列なので、
    文字列の比較で時刻の順になる。
    """
    matched = [(doc_id, source) for doc_id, source in documents.items() if matches(source)]
    matched.sort(key=lambda item: item[0])
    # 逆順の指定でも、同順位の相対順(`_id` の昇順)は保たれる(並べ替えは安定)。
    matched.sort(key=lambda item: str(item[1].get(sort_field, "")), reverse=page.descending)
    window = matched[page.offset : page.offset + page.items_per_page]
    items = tuple(StoredRecord(doc_id, _project(source, fields)) for doc_id, source in window)
    return Page(total=len(matched), items=items)


def _latest_job(jobs: Sequence[tuple[str, Document]], job_type: str) -> StoredRecord | None:
    """`queued_at` が最新のジョブ(同順位は `job_id` の昇順)。"""
    candidates = sorted(
        ((job_id, source) for job_id, source in jobs if source.get("job_type") == job_type),
        key=lambda item: item[0],
    )
    candidates.sort(key=lambda item: str(item[1].get("queued_at", "")), reverse=True)
    if not candidates:
        return None
    job_id, source = candidates[0]
    return StoredRecord(job_id, _project(source, JOB_BRIEF_FIELDS))


def _last_completed_epoch_millis(jobs: Sequence[tuple[str, Document]]) -> int | None:
    """成功・一部成功の `crawl` の `finished_at` の最大(エポックミリ秒)。"""
    finished = [
        parse_instant(source["finished_at"])
        for _, source in jobs
        if source.get("job_type") == "crawl"
        and source.get("status") in ("succeeded", "partially_succeeded")
        and isinstance(source.get("finished_at"), str)
    ]
    if not finished:
        return None
    return (max(finished) - _EPOCH) // _ONE_MILLISECOND


def _key_of(ids: Sequence[str]) -> str:
    return ",".join(ids)


def _document_failure(store: _Store, operation: str, document_key: str) -> Failed | None:
    return store.document_failures.get((operation, document_key))


class _InMemorySourcesReader:
    def __init__(self, store: _Store) -> None:
        self._store = store

    def list_all(self) -> Result[tuple[StoredRecord, ...]]:
        """検索(最後の `refresh_search()` の時点の状態)。`source_id` の昇順で、設定の本体は除く。"""
        intercepted = self._store.behavior.enter("sources.list_all")
        if intercepted is not None:
            return intercepted.value
        return Ok(
            tuple(
                StoredRecord(
                    source_id,
                    copy.deepcopy({k: v for k, v in source.items() if k != "connector_config"}),
                )
                for source_id, source in sorted(self._store.searchable.sources.items())
            )
        )

    def get(self, source_id: str, fields: Sequence[str] | None) -> Result[StoredRecord | None]:
        intercepted = self._store.behavior.enter("sources.get", source_id)
        if intercepted is not None:
            return intercepted.value
        failure = _document_failure(self._store, "sources.get", source_id)
        if failure is not None:
            return failure
        source = self._store.live.sources.get(source_id)
        if source is None:
            return Ok(None)
        return Ok(StoredRecord(source_id, _project(source, fields)))


class _InMemoryJobsReader:
    def __init__(self, store: _Store) -> None:
        self._store = store

    def get_locks(self, source_ids: Sequence[str]) -> RecordResults:
        """`mget`。キーは `source_id`。`record_type` が `lock` でなければ「ロックなし」。"""
        unique_ids = list(dict.fromkeys(source_ids))
        intercepted = self._store.behavior.enter("jobs.get_locks", _key_of(unique_ids))
        if intercepted is not None:
            return dict.fromkeys(unique_ids, intercepted.value)
        results: RecordResults = {}
        for source_id in unique_ids:
            results[source_id] = self._read_document(
                "jobs.get_locks", source_id, f"lock-{source_id}", "lock", LOCK_FIELDS
            )
        return results

    def get_jobs(self, job_ids: Sequence[str], fields: Sequence[str]) -> RecordResults:
        """`mget`。`record_type` が `job` でなければ「記録なし」。"""
        unique_ids = list(dict.fromkeys(job_ids))
        intercepted = self._store.behavior.enter("jobs.get_jobs", _key_of(unique_ids))
        if intercepted is not None:
            return dict.fromkeys(unique_ids, intercepted.value)
        return {
            job_id: self._read_document("jobs.get_jobs", job_id, job_id, "job", fields)
            for job_id in unique_ids
        }

    def list_jobs(self, query: JobListQuery) -> Result[Page]:
        """検索(最後の `refresh_search()` の時点の状態)。`queued_at`、同順位は `job_id` の昇順。"""
        intercepted = self._store.behavior.enter("jobs.list_jobs", query.source_id)
        if intercepted is not None:
            return intercepted.value

        def matches(source: Document) -> bool:
            return (
                source.get("record_type") == "job"
                and (query.source_id is None or source.get("source_id") == query.source_id)
                and (not query.statuses or source.get("status") in query.statuses)
            )

        return Ok(
            _page_of(
                self._store.searchable.jobs,
                matches,
                sort_field="queued_at",
                fields=JOB_BRIEF_FIELDS,
                page=query.page,
            )
        )

    def latest_by_source(self, source_ids: Sequence[str]) -> Result[dict[str, SourceJobsSummary]]:
        """検索(最後の `refresh_search()` の時点の状態)。ジョブが 1 件もないソースはキーがない。"""
        intercepted = self._store.behavior.enter("jobs.latest_by_source", _key_of(source_ids))
        if intercepted is not None:
            return intercepted.value
        jobs = [
            (job_id, source)
            for job_id, source in self._store.searchable.jobs.items()
            if source.get("record_type") == "job"
        ]
        summaries: dict[str, SourceJobsSummary] = {}
        for source_id in dict.fromkeys(source_ids):
            source_jobs = [(job_id, s) for job_id, s in jobs if s.get("source_id") == source_id]
            if not source_jobs:
                continue
            summaries[source_id] = SourceJobsSummary(
                latest_crawl=_latest_job(source_jobs, "crawl"),
                latest_source_delete=_latest_job(source_jobs, "source_delete"),
                last_completed_epoch_millis=_last_completed_epoch_millis(source_jobs),
            )
        return Ok(summaries)

    def list_skipped(self, source_id: str, page: PageRequest) -> Result[Page]:
        """検索。`last_skipped_at`、同順位は `document_id` の昇順。"""
        return self._list_records(
            "jobs.list_skipped", "skip", "last_skipped_at", SKIPPED_FIELDS, source_id, page
        )

    def list_oversize(self, source_id: str, page: PageRequest) -> Result[Page]:
        """検索。`last_detected_at`、同順位は `document_id` の昇順。"""
        return self._list_records(
            "jobs.list_oversize", "oversize", "last_detected_at", OVERSIZE_FIELDS, source_id, page
        )

    def _list_records(
        self,
        operation: str,
        record_type: str,
        sort_field: str,
        fields: Sequence[str],
        source_id: str,
        page: PageRequest,
    ) -> Result[Page]:
        intercepted = self._store.behavior.enter(operation, source_id)
        if intercepted is not None:
            return intercepted.value

        def matches(source: Document) -> bool:
            return source.get("record_type") == record_type and source.get("source_id") == source_id

        return Ok(
            _page_of(
                self._store.searchable.jobs,
                matches,
                sort_field=sort_field,
                fields=fields,
                page=page,
            )
        )

    def latest_crawl_id(self, source_id: str) -> Result[str | None]:
        """検索(最後の `refresh_search()` の時点の状態)。最新の `crawl` の ID。"""
        intercepted = self._store.behavior.enter("jobs.latest_crawl_id", source_id)
        if intercepted is not None:
            return intercepted.value
        crawls = [
            (job_id, source)
            for job_id, source in self._store.searchable.jobs.items()
            if source.get("record_type") == "job"
            and source.get("job_type") == "crawl"
            and source.get("source_id") == source_id
        ]
        crawls.sort(key=lambda item: item[0])
        crawls.sort(key=lambda item: str(item[1].get("queued_at", "")), reverse=True)
        return Ok(crawls[0][0] if crawls else None)

    def _read_document(
        self,
        operation: str,
        result_key: str,
        document_id: str,
        record_type: str,
        fields: Sequence[str],
    ) -> Result[StoredRecord | None]:
        failure = _document_failure(self._store, operation, result_key)
        if failure is not None:
            return failure
        source = self._store.live.jobs.get(document_id)
        if source is None or source.get("record_type") != record_type:
            return Ok(None)
        return Ok(StoredRecord(document_id, _project(source, [*fields, "record_type"])))


class _InMemoryDeletionsReader:
    def __init__(self, store: _Store) -> None:
        self._store = store

    def get_result(self, job_id: str) -> Result[StoredRecord | None]:
        intercepted = self._store.behavior.enter("deletions.get_result", job_id)
        if intercepted is not None:
            return intercepted.value
        failure = _document_failure(self._store, "deletions.get_result", job_id)
        if failure is not None:
            return failure
        document_id = f"deletion_result-{job_id}"
        source = self._store.live.deletions.get(document_id)
        if source is None or source.get("record_type") != "deletion_result":
            return Ok(None)
        return Ok(StoredRecord(document_id, _project(source, DELETION_RESULT_FIELDS)))


class _InMemorySearchIndexReader:
    """検索インデックス(エイリアス)。すべて検索で、最後の `refresh_search()` の時点の状態を読む。"""

    def __init__(self, store: _Store) -> None:
        self._store = store

    def count_by_source(self, source_ids: Sequence[str]) -> Result[dict[str, int]]:
        """文書のないソースは 0。"""
        unique_ids = list(dict.fromkeys(source_ids))
        intercepted = self._store.behavior.enter(
            "search_index.count_by_source", _key_of(unique_ids)
        )
        if intercepted is not None:
            return intercepted.value
        documents = self._store.searchable.search_index.values()
        return Ok(
            {
                source_id: sum(1 for source in documents if source.get("source_id") == source_id)
                for source_id in unique_ids
            }
        )

    def list_extract_failed(self, source_id: str, page: PageRequest) -> Result[Page]:
        """`last_seen_at`、同順位は `document_id`(`_id`)の昇順。"""
        return self._list_documents(
            "search_index.list_extract_failed",
            "index_status",
            "extract_failed",
            "last_seen_at",
            EXTRACT_FAILED_FIELDS,
            source_id,
            page,
        )

    def list_summary_pending(self, source_id: str, page: PageRequest) -> Result[Page]:
        """`indexed_at`、同順位は `document_id`(`_id`)の昇順。"""
        return self._list_documents(
            "search_index.list_summary_pending",
            "summary_status",
            "pending",
            "indexed_at",
            SUMMARY_PENDING_FIELDS,
            source_id,
            page,
        )

    def existing_ids(self, document_ids: Sequence[str]) -> Result[frozenset[str]]:
        unique_ids = list(dict.fromkeys(document_ids))
        if len(unique_ids) > MAX_EXISTENCE_IDS:
            raise ValueError("too many document ids")
        intercepted = self._store.behavior.enter("search_index.existing_ids", _key_of(unique_ids))
        if intercepted is not None:
            return intercepted.value
        searchable = self._store.searchable.search_index
        return Ok(frozenset(document_id for document_id in unique_ids if document_id in searchable))

    def _list_documents(
        self,
        operation: str,
        status_field: str,
        status_value: str,
        sort_field: str,
        fields: Sequence[str],
        source_id: str,
        page: PageRequest,
    ) -> Result[Page]:
        intercepted = self._store.behavior.enter(operation, source_id)
        if intercepted is not None:
            return intercepted.value

        def matches(source: Document) -> bool:
            return source.get("source_id") == source_id and source.get(status_field) == status_value

        return Ok(
            _page_of(
                self._store.searchable.search_index,
                matches,
                sort_field=sort_field,
                fields=fields,
                page=page,
            )
        )


class _InMemoryCountsReader:
    """件数(`msearch`)。検索なので、最後の `refresh_search()` の時点の状態を数える。"""

    def __init__(self, store: _Store) -> None:
        self._store = store

    def count_for_source(
        self, source_id: str, targets: Sequence[CountTarget]
    ) -> dict[CountTarget, Result[int]]:
        unique_targets = tuple(dict.fromkeys(targets))
        intercepted = self._store.behavior.enter("counts.count_for_source", source_id)
        if intercepted is not None:
            return dict.fromkeys(unique_targets, intercepted.value)
        results: dict[CountTarget, Result[int]] = {}
        for target in unique_targets:
            failure = _document_failure(self._store, "counts.count_for_source", target)
            results[target] = failure if failure is not None else Ok(self._count(source_id, target))
        return results

    def _count(self, source_id: str, target: CountTarget) -> int:
        searchable = self._store.searchable
        match target:
            case "document_count":
                return _count_matching(searchable.search_index, source_id)
            case "extract_failed":
                return _count_matching(
                    searchable.search_index, source_id, "index_status", "extract_failed"
                )
            case "summary_pending":
                return _count_matching(
                    searchable.search_index, source_id, "summary_status", "pending"
                )
            case "skipped" | "oversize":
                return _count_matching(searchable.jobs, source_id, "record_type", target)


def _count_matching(
    documents: Mapping[str, Document],
    source_id: str,
    field: str | None = None,
    value: str | None = None,
) -> int:
    return sum(
        1
        for source in documents.values()
        if source.get("source_id") == source_id and (field is None or source.get(field) == value)
    )


class _InMemoryClusterReader:
    def __init__(self, store: _Store) -> None:
        self._store = store

    def read(self) -> Result[ClusterSnapshot]:
        intercepted = self._store.behavior.enter("cluster.read")
        if intercepted is not None:
            return intercepted.value
        snapshot = self._store.cluster_snapshot
        if snapshot is None:
            raise AssertionError("the test did not set cluster_snapshot")
        return Ok(snapshot)
