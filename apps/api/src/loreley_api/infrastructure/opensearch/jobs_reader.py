"""`loreley-jobs` の読み取り(R-3〜R-7・R-10 の `skipped`・`oversize`。C 3.3)。

ID での取得は `mget`(書き込み直後でも見える)、一覧・集計は `search`(最大で約 1 秒古い。C 3.2)。
"""

import math
from collections.abc import Mapping, Sequence

from loreley_api.common.results import Result
from loreley_api.infrastructure.opensearch import queries
from loreley_api.infrastructure.opensearch.failure import ResponseShapeError, guarded_read
from loreley_api.infrastructure.opensearch.ports import (
    LOCK_FIELDS,
    JobListQuery,
    Page,
    PageRequest,
    RecordResults,
    SourceJobsSummary,
    StoredRecord,
)
from loreley_api.infrastructure.opensearch.reading import fetch_documents, search_page
from loreley_api.infrastructure.opensearch.readonly_client import ReadOnlyOpenSearch
from loreley_api.infrastructure.opensearch.responses import (
    as_list,
    as_mapping,
    as_str,
    parse_hits,
    parse_search,
)

LOCK_RECORD_TYPE = "lock"
JOB_RECORD_TYPE = "job"


class OpenSearchJobsReader:
    def __init__(self, readonly: ReadOnlyOpenSearch, *, jobs_index: str) -> None:
        self._readonly = readonly
        self._jobs_index = jobs_index

    def latest_by_source(self, source_ids: Sequence[str]) -> Result[dict[str, SourceJobsSummary]]:
        return guarded_read(
            "jobs.latest_by_source", "store", lambda: self._read_latest_by_source(source_ids)
        )

    def get_locks(self, source_ids: Sequence[str]) -> RecordResults:
        unique_source_ids = tuple(dict.fromkeys(source_ids))
        lock_ids = [f"{LOCK_RECORD_TYPE}-{source_id}" for source_id in unique_source_ids]
        results = fetch_documents(
            self._readonly,
            index=self._jobs_index,
            ids=lock_ids,
            target="store",
            operation="jobs.get_locks",
            source_includes=LOCK_FIELDS,
            expected_record_type=LOCK_RECORD_TYPE,
        )
        return {
            source_id: results[lock_id]
            for source_id, lock_id in zip(unique_source_ids, lock_ids, strict=True)
        }

    def get_jobs(self, job_ids: Sequence[str], fields: Sequence[str]) -> RecordResults:
        # `record_type` を確かめるために、指定がなくても読む。
        source_includes = list(dict.fromkeys([*fields, "record_type"]))
        return fetch_documents(
            self._readonly,
            index=self._jobs_index,
            ids=job_ids,
            target="store",
            operation="jobs.get_jobs",
            source_includes=source_includes,
            expected_record_type=JOB_RECORD_TYPE,
        )

    def list_jobs(self, query: JobListQuery) -> Result[Page]:
        return search_page(
            self._readonly,
            index=self._jobs_index,
            body=queries.jobs_list_body(query),
            target="store",
            operation="jobs.list_jobs",
        )

    def latest_crawl_id(self, source_id: str) -> Result[str | None]:
        return guarded_read(
            "jobs.latest_crawl_id", "store", lambda: self._read_latest_crawl_id(source_id)
        )

    def list_skipped(self, source_id: str, page: PageRequest) -> Result[Page]:
        return search_page(
            self._readonly,
            index=self._jobs_index,
            body=queries.skipped_list_body(source_id, page),
            target="store",
            operation="jobs.list_skipped",
        )

    def list_oversize(self, source_id: str, page: PageRequest) -> Result[Page]:
        return search_page(
            self._readonly,
            index=self._jobs_index,
            body=queries.oversize_list_body(source_id, page),
            target="store",
            operation="jobs.list_oversize",
        )

    def _read_latest_crawl_id(self, source_id: str) -> str | None:
        response = self._readonly.search(
            index=self._jobs_index, body=queries.latest_crawl_id_body(source_id)
        )
        hits = parse_search(response).hits
        return hits[0].record_id if hits else None

    def _read_latest_by_source(self, source_ids: Sequence[str]) -> dict[str, SourceJobsSummary]:
        unique_source_ids = tuple(dict.fromkeys(source_ids))
        if not unique_source_ids:
            return {}
        response = self._readonly.search(
            index=self._jobs_index, body=queries.latest_by_source_body(unique_source_ids)
        )
        aggregations = parse_search(response).aggregations
        buckets = as_list(as_mapping(aggregations.get("by_source")).get("buckets"))
        summaries = {}
        for bucket in buckets:
            bucket_mapping = as_mapping(bucket)
            summaries[as_str(bucket_mapping.get("key"))] = _parse_summary(bucket_mapping)
        return summaries


def _parse_summary(bucket: Mapping[str, object]) -> SourceJobsSummary:
    crawl = as_mapping(bucket.get("crawl"))
    delete = as_mapping(bucket.get("delete"))
    completed = as_mapping(crawl.get("completed"))
    return SourceJobsSummary(
        latest_crawl=_first_hit(as_mapping(crawl.get("latest"))),
        latest_source_delete=_first_hit(as_mapping(delete.get("latest"))),
        last_completed_epoch_millis=_epoch_millis(as_mapping(completed.get("at")).get("value")),
    )


def _first_hit(top_hits_aggregation: Mapping[str, object]) -> StoredRecord | None:
    hits = parse_hits(as_mapping(top_hits_aggregation.get("hits")))
    return hits[0] if hits else None


def _epoch_millis(value: object) -> int | None:
    """`max` 集計の値(エポックミリ秒。該当なしは `null`)。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ResponseShapeError("max aggregation value is not a number")
    return int(value)
