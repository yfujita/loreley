"""クエリ本文の組み立て(R-1〜R-12。C 3.3・3.4)。純粋関数で、I/O をしない。

形は C 3.3 に従う。共通の規約(C 3.2):
- `_source` は必要な項目だけを指定する。`content`・`summary`・`connector_config`・`finish_notice` の
  ID 一覧などは読まない。
- ページングは `from`・`size`・`track_total_hits: true`。並べ替えは「指定の項目 + ID の昇順」で、
  同順位でも取りこぼし・重複が出ないようにする。
- 件数だけの取得は `size: 0` の検索(`count` API は使わない)。
- 検索インデックスは `ids`・`term`・`terms` だけでフィルタし、`content`・`summary` を読まない
  (C 3.6)。

`mget` の本文と `cat.*` の固定の引数は `readonly_client.py` が持つ(この列の定数だけ、ここに置く)。
"""

from collections.abc import Sequence

from loreley_api.infrastructure.opensearch.ports import (
    JOB_BRIEF_FIELDS,
    MAX_SOURCES,
    CountTarget,
    JobListQuery,
    PageRequest,
)

type Body = dict[str, object]

# `cat.*` の列(C 3.4)。応答の行は、この列をキーに持つ。
CAT_INDICES_COLUMNS = ("index", "health", "docs.count")
CAT_SHARDS_COLUMNS = ("index", "shard", "prirep", "state", "node")
CAT_NODES_COLUMNS = ("name",)

CLUSTER_HEALTH_FIELDS = (
    "cluster_name",
    "status",
    "number_of_nodes",
    "active_shards",
    "relocating_shards",
    "initializing_shards",
    "unassigned_shards",
)

# R-10 の `_source`(タブごと。C 3.3)。`document_id` は `_id`(検索インデックス)または項目。
SKIPPED_FIELDS = (
    "document_id",
    "external_id",
    "stage",
    "reason",
    "attempts",
    "consecutive_skips",
    "first_skipped_at",
    "last_skipped_at",
    "last_job_id",
)
OVERSIZE_FIELDS = (
    "document_id",
    "external_id",
    "detected_by",
    "size",
    "first_detected_at",
    "last_detected_at",
    "last_job_id",
)
EXTRACT_FAILED_FIELDS = (
    "title",
    "external_id",
    "mime_type",
    "size",
    "source_updated_at",
    "last_seen_at",
)
SUMMARY_PENDING_FIELDS = ("title", "external_id", "mime_type", "source_updated_at", "indexed_at")

_ORDER_ASCENDING = "asc"
_ORDER_DESCENDING = "desc"


def sources_all_body() -> Body:
    """R-1: データソースの全件。`connector_config` は読まない。"""
    return {
        "size": MAX_SOURCES,
        "track_total_hits": True,
        "sort": [{"source_id": _ORDER_ASCENDING}],
        "_source": {"excludes": ["connector_config"]},
        "query": {"match_all": {}},
    }


def latest_by_source_body(source_ids: Sequence[str]) -> Body:
    """R-3: ソースごとの最新の `crawl`・最新の `source_delete`・最終完了日時。"""
    latest_job = {
        "top_hits": {
            "size": 1,
            "sort": [{"queued_at": _ORDER_DESCENDING}, {"job_id": _ORDER_ASCENDING}],
            "_source": {"includes": list(JOB_BRIEF_FIELDS)},
        }
    }
    return {
        "size": 0,
        # 総件数を使わない。既定のままだと、10,000 件超で `relation: gte` が返り、検証が失敗する。
        "track_total_hits": False,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"record_type": "job"}},
                    {"terms": {"source_id": list(source_ids)}},
                ]
            }
        },
        "aggs": {
            "by_source": {
                "terms": {"field": "source_id", "size": len(source_ids)},
                "aggs": {
                    "crawl": {
                        "filter": {"term": {"job_type": "crawl"}},
                        "aggs": {
                            "latest": latest_job,
                            "completed": {
                                "filter": {
                                    "terms": {"status": ["succeeded", "partially_succeeded"]}
                                },
                                "aggs": {"at": {"max": {"field": "finished_at"}}},
                            },
                        },
                    },
                    "delete": {
                        "filter": {"term": {"job_type": "source_delete"}},
                        "aggs": {"latest": latest_job},
                    },
                },
            }
        },
    }


def jobs_list_body(query: JobListQuery) -> Body:
    """R-6: ジョブ一覧。"""
    filters: list[object] = [{"term": {"record_type": "job"}}]
    if query.source_id is not None:
        filters.append({"term": {"source_id": query.source_id}})
    if len(query.statuses) == 1:
        filters.append({"term": {"status": query.statuses[0]}})
    elif len(query.statuses) > 1:
        filters.append({"terms": {"status": list(query.statuses)}})
    return _page_body(
        query.page,
        filters=filters,
        sort_field="queued_at",
        tiebreaker="job_id",
        source_fields=JOB_BRIEF_FIELDS,
    )


def latest_crawl_id_body(source_id: str) -> Body:
    """R-7: そのソースの最新の `crawl` ジョブ 1 件(`_id` だけ使う)。"""
    return {
        "size": 1,
        "_source": False,
        # 総件数を使わない(R-3 と同じ理由)。
        "track_total_hits": False,
        "sort": [{"queued_at": _ORDER_DESCENDING}, {"job_id": _ORDER_ASCENDING}],
        "query": {
            "bool": {
                "filter": [
                    {"term": {"record_type": "job"}},
                    {"term": {"job_type": "crawl"}},
                    {"term": {"source_id": source_id}},
                ]
            }
        },
    }


def skipped_list_body(source_id: str, page: PageRequest) -> Body:
    """R-10: `skipped` タブ(`loreley-jobs`)。"""
    return _page_body(
        page,
        filters=[{"term": {"record_type": "skip"}}, {"term": {"source_id": source_id}}],
        sort_field="last_skipped_at",
        tiebreaker="document_id",
        source_fields=SKIPPED_FIELDS,
    )


def oversize_list_body(source_id: str, page: PageRequest) -> Body:
    """R-10: `oversize` タブ(`loreley-jobs`)。"""
    return _page_body(
        page,
        filters=[{"term": {"record_type": "oversize"}}, {"term": {"source_id": source_id}}],
        sort_field="last_detected_at",
        tiebreaker="document_id",
        source_fields=OVERSIZE_FIELDS,
    )


def extract_failed_list_body(source_id: str, page: PageRequest) -> Body:
    """R-10: `extract_failed` タブ(検索インデックス)。"""
    return _page_body(
        page,
        filters=[{"term": {"source_id": source_id}}, {"term": {"index_status": "extract_failed"}}],
        sort_field="last_seen_at",
        tiebreaker="document_id",
        source_fields=EXTRACT_FAILED_FIELDS,
    )


def summary_pending_list_body(source_id: str, page: PageRequest) -> Body:
    """R-10: `summary_pending` タブ(検索インデックス)。"""
    return _page_body(
        page,
        filters=[{"term": {"source_id": source_id}}, {"term": {"summary_status": "pending"}}],
        sort_field="indexed_at",
        tiebreaker="document_id",
        source_fields=SUMMARY_PENDING_FIELDS,
    )


def count_by_source_body(source_ids: Sequence[str]) -> Body:
    """R-9(EP-01): ソースごとの登録文書数。`index_status` は問わない(AAPI-P-23)。"""
    return {
        "size": 0,
        "track_total_hits": True,
        "query": {"terms": {"source_id": list(source_ids)}},
        "aggs": {"by_source": {"terms": {"field": "source_id", "size": len(source_ids)}}},
    }


def count_body(target: CountTarget, source_id: str) -> Body:
    """R-9(EP-02・11): 1 つの件数。`msearch` のサブ要求の本文。"""
    return {
        "size": 0,
        "track_total_hits": True,
        "query": {"bool": {"filter": _count_filters(target, source_id)}},
    }


def existing_ids_body(document_ids: Sequence[str]) -> Body:
    """R-11: 検索インデックスにある `document_id`(`_id`)。"""
    return {
        "size": len(document_ids),
        "_source": False,
        "track_total_hits": False,
        "query": {"ids": {"values": list(document_ids)}},
    }


def _count_filters(target: CountTarget, source_id: str) -> list[object]:
    by_source = {"term": {"source_id": source_id}}
    match target:
        case "document_count":
            return [by_source]
        case "skipped":
            return [{"term": {"record_type": "skip"}}, by_source]
        case "oversize":
            return [{"term": {"record_type": "oversize"}}, by_source]
        case "extract_failed":
            return [by_source, {"term": {"index_status": "extract_failed"}}]
        case "summary_pending":
            return [by_source, {"term": {"summary_status": "pending"}}]


def _page_body(
    page: PageRequest,
    *,
    filters: list[object],
    sort_field: str,
    tiebreaker: str,
    source_fields: Sequence[str],
) -> Body:
    order = _ORDER_DESCENDING if page.descending else _ORDER_ASCENDING
    return {
        "from": page.offset,
        "size": page.items_per_page,
        "track_total_hits": True,
        "sort": [{sort_field: order}, {tiebreaker: _ORDER_ASCENDING}],
        "_source": {"includes": list(source_fields)},
        "query": {"bool": {"filter": filters}},
    }
