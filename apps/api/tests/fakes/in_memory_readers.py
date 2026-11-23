"""OpenSearch の Reader(Protocol)の偽物(D 7.2。C 11章 16)。

`services`・`routers` のテストで、Reader の下の OpenSearch を持ち込まずに、読み取りの結果を
作る。**検索は古いスナップショット、`mget` はリアルタイム**を再現する(`stalled` の偽陽性が
出ないことの確認用):

- `get_locks`・`get_jobs`・`get`(ソース)・`get_result` は、書き込んだ直後の状態を読む(`mget`)。
- `list_jobs`・`latest_crawl_id` は、`refresh_search()` を呼んだ時点の状態を読む(検索。最大で
  約 1 秒古い)。書き込みだけでは検索に現れない。

障害の注入(`behavior` は `FakeBehavior`):
- 呼び出し全体の失敗: `readers.behavior.inject("jobs.get_locks", failed, times=None)`
  (操作名は `jobs.get_locks`・`jobs.get_jobs`・`jobs.list_jobs`・`jobs.latest_crawl_id`・
  `sources.get`・`deletions.get_result`・`cluster.read`)。`mget` の操作では、すべての ID が同じ
  失敗になる(本物の Reader と同じ)。
- 文書単位の失敗(`mget` だけ): `readers.fail_document("jobs.get_locks", "source-b", failed)`。
  他の文書は読める。
- 読みと読みの間の書き込み: `readers.behavior.before("jobs.get_locks", callback)`。
- 読んだ呼び出しは `readers.behavior.calls_of(...)` に残る(`key` は ID、複数ならカンマ区切り)。

P3 で使うメソッドだけを実装している(EP-01・02・11 用の `latest_by_source`・`list_skipped`・
`list_oversize` と、`SearchIndexReader`・`CountsReader` は、P4 で足す)。
"""

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from loreley_api.common.results import Failed, Ok, Result
from loreley_api.infrastructure.opensearch import (
    ClusterSnapshot,
    JobListQuery,
    Page,
    RecordResults,
    StoredRecord,
)
from loreley_api.infrastructure.opensearch.ports import JOB_BRIEF_FIELDS, LOCK_FIELDS
from tests.fakes.behavior import FakeBehavior

STORE_UNAVAILABLE = Failed(kind="unavailable", target="store", error_class_name="ConnectionError")
STORE_TIMEOUT = Failed(kind="timeout", target="store", error_class_name="ConnectionTimeout")

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

type Document = dict[str, Any]


class _Documents:
    """3 つの索引の文書(`_id` → `_source`)。`sources`・`jobs`・`deletions` が索引に対応する。"""

    def __init__(self) -> None:
        self.sources: dict[str, Document] = {}
        self.jobs: dict[str, Document] = {}
        self.deletions: dict[str, Document] = {}

    def copy(self) -> "_Documents":
        snapshot = _Documents()
        snapshot.sources = copy.deepcopy(self.sources)
        snapshot.jobs = copy.deepcopy(self.jobs)
        snapshot.deletions = copy.deepcopy(self.deletions)
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
        self.behavior = FakeBehavior()
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


def _key_of(ids: Sequence[str]) -> str:
    return ",".join(ids)


def _document_failure(store: _Store, operation: str, document_key: str) -> Failed | None:
    return store.document_failures.get((operation, document_key))


class _InMemorySourcesReader:
    def __init__(self, store: _Store) -> None:
        self._store = store

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
        matched = [
            (job_id, source)
            for job_id, source in self._store.searchable.jobs.items()
            if source.get("record_type") == "job"
            and (query.source_id is None or source.get("source_id") == query.source_id)
            and (not query.statuses or source.get("status") in query.statuses)
        ]
        matched.sort(key=lambda item: item[0])
        matched.sort(
            key=lambda item: str(item[1].get("queued_at", "")), reverse=query.page.descending
        )
        page_items = matched[query.page.offset : query.page.offset + query.page.items_per_page]
        items = tuple(
            StoredRecord(job_id, _project(source, JOB_BRIEF_FIELDS))
            for job_id, source in page_items
        )
        return Ok(Page(total=len(matched), items=items))

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
