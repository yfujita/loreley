"""クエリ本文の形(C 3.2・3.3 の R-1〜R-11。C 11章 7)。

偽物はクエリの意味を実行しないので、ここで本文の形(フィルタ・並べ替え・`_source`・ページング)を
固定する。意味の確認は結合テストの範囲(AAA-U-1〜3)。
"""

from collections.abc import Callable

import pytest

from loreley_api.infrastructure.opensearch import JobListQuery, PageRequest, queries
from loreley_api.infrastructure.opensearch.ports import JOB_BRIEF_FIELDS, CountTarget

# 読んではならない項目(C 3.2・3.6)。
FORBIDDEN_SOURCE_FIELDS = {"content", "summary", "connector_config", "finish_notice"}


def dig(value: object, *path: str | int) -> object:
    for key in path:
        if isinstance(value, dict):
            value = value[key]
        else:
            assert isinstance(value, list)
            assert isinstance(key, int)
            value = value[key]
    return value


def includes_of(body: dict[str, object]) -> list[str]:
    source = body["_source"]
    assert isinstance(source, dict)
    includes = source["includes"]
    assert isinstance(includes, list)
    return includes


def test_r1_reads_all_sources_without_connector_config() -> None:
    assert queries.sources_all_body() == {
        "size": 10_000,
        "track_total_hits": True,
        "sort": [{"source_id": "asc"}],
        "_source": {"excludes": ["connector_config"]},
        "query": {"match_all": {}},
    }


def test_r3_aggregates_the_latest_jobs_per_source_in_one_search() -> None:
    body = queries.latest_by_source_body(["a", "b"])

    assert body["size"] == 0
    assert body["track_total_hits"] is False  # 総件数を使わない(10,000 件超でも失敗にしない)
    assert body["query"] == {
        "bool": {
            "filter": [
                {"term": {"record_type": "job"}},
                {"terms": {"source_id": ["a", "b"]}},
            ]
        }
    }
    assert dig(body, "aggs", "by_source", "terms") == {"field": "source_id", "size": 2}
    crawl = dig(body, "aggs", "by_source", "aggs", "crawl")
    assert dig(crawl, "filter") == {"term": {"job_type": "crawl"}}
    assert dig(crawl, "aggs", "completed") == {
        "filter": {"terms": {"status": ["succeeded", "partially_succeeded"]}},
        "aggs": {"at": {"max": {"field": "finished_at"}}},
    }
    assert dig(crawl, "aggs", "latest", "top_hits") == {
        "size": 1,
        "sort": [{"queued_at": "desc"}, {"job_id": "asc"}],
        "_source": {"includes": list(JOB_BRIEF_FIELDS)},
    }
    delete = dig(body, "aggs", "by_source", "aggs", "delete")
    assert dig(delete, "filter") == {"term": {"job_type": "source_delete"}}
    assert dig(delete, "aggs", "latest") == dig(crawl, "aggs", "latest")


PAGE = PageRequest(page=3, items_per_page=25, descending=True)


def test_r6_lists_jobs_with_paging_sort_and_the_job_brief_fields() -> None:
    body = queries.jobs_list_body(JobListQuery(page=PAGE))

    assert body == {
        "from": 50,
        "size": 25,
        "track_total_hits": True,
        "sort": [{"queued_at": "desc"}, {"job_id": "asc"}],
        "_source": {"includes": list(JOB_BRIEF_FIELDS)},
        "query": {"bool": {"filter": [{"term": {"record_type": "job"}}]}},
    }


def test_r6_adds_the_source_and_status_filters_only_when_given() -> None:
    one_status = queries.jobs_list_body(
        JobListQuery(page=PAGE, source_id="s", statuses=("failed",))
    )
    active = queries.jobs_list_body(JobListQuery(page=PAGE, statuses=("queued", "running")))

    assert dig(one_status, "query", "bool", "filter") == [
        {"term": {"record_type": "job"}},
        {"term": {"source_id": "s"}},
        {"term": {"status": "failed"}},
    ]
    assert dig(active, "query", "bool", "filter") == [
        {"term": {"record_type": "job"}},
        {"terms": {"status": ["queued", "running"]}},
    ]


def test_the_sort_direction_applies_to_the_main_field_only() -> None:
    ascending = PageRequest(page=1, items_per_page=25, descending=False)

    body = queries.jobs_list_body(JobListQuery(page=ascending))

    assert body["sort"] == [{"queued_at": "asc"}, {"job_id": "asc"}]


def test_r7_reads_only_the_id_of_the_latest_crawl() -> None:
    assert queries.latest_crawl_id_body("s") == {
        "size": 1,
        "_source": False,
        "track_total_hits": False,
        "sort": [{"queued_at": "desc"}, {"job_id": "asc"}],
        "query": {
            "bool": {
                "filter": [
                    {"term": {"record_type": "job"}},
                    {"term": {"job_type": "crawl"}},
                    {"term": {"source_id": "s"}},
                ]
            }
        },
    }


@pytest.mark.parametrize(
    ("build", "filters", "sort_field", "source_fields"),
    [
        (
            queries.skipped_list_body,
            [{"term": {"record_type": "skip"}}, {"term": {"source_id": "s"}}],
            "last_skipped_at",
            queries.SKIPPED_FIELDS,
        ),
        (
            queries.oversize_list_body,
            [{"term": {"record_type": "oversize"}}, {"term": {"source_id": "s"}}],
            "last_detected_at",
            queries.OVERSIZE_FIELDS,
        ),
        (
            queries.extract_failed_list_body,
            [{"term": {"source_id": "s"}}, {"term": {"index_status": "extract_failed"}}],
            "last_seen_at",
            queries.EXTRACT_FAILED_FIELDS,
        ),
        (
            queries.summary_pending_list_body,
            [{"term": {"source_id": "s"}}, {"term": {"summary_status": "pending"}}],
            "indexed_at",
            queries.SUMMARY_PENDING_FIELDS,
        ),
    ],
)
def test_r10_tab_lists_have_their_filter_sort_and_source(
    build: Callable[[str, PageRequest], dict[str, object]],
    filters: list[object],
    sort_field: str,
    source_fields: tuple[str, ...],
) -> None:
    body = build("s", PAGE)

    assert body == {
        "from": 50,
        "size": 25,
        "track_total_hits": True,
        "sort": [{sort_field: "desc"}, {"document_id": "asc"}],
        "_source": {"includes": list(source_fields)},
        "query": {"bool": {"filter": filters}},
    }


def test_no_list_reads_a_forbidden_source_field() -> None:
    bodies = [
        queries.jobs_list_body(JobListQuery(page=PAGE)),
        queries.skipped_list_body("s", PAGE),
        queries.oversize_list_body("s", PAGE),
        queries.extract_failed_list_body("s", PAGE),
        queries.summary_pending_list_body("s", PAGE),
    ]

    for body in bodies:
        assert FORBIDDEN_SOURCE_FIELDS.isdisjoint(includes_of(body))


def test_r9_counts_documents_per_source_with_a_terms_aggregation() -> None:
    assert queries.count_by_source_body(["a", "b", "c"]) == {
        "size": 0,
        "track_total_hits": True,
        "query": {"terms": {"source_id": ["a", "b", "c"]}},
        "aggs": {"by_source": {"terms": {"field": "source_id", "size": 3}}},
    }


@pytest.mark.parametrize(
    ("target", "filters"),
    [
        ("document_count", [{"term": {"source_id": "s"}}]),
        ("skipped", [{"term": {"record_type": "skip"}}, {"term": {"source_id": "s"}}]),
        ("oversize", [{"term": {"record_type": "oversize"}}, {"term": {"source_id": "s"}}]),
        (
            "extract_failed",
            [{"term": {"source_id": "s"}}, {"term": {"index_status": "extract_failed"}}],
        ),
        (
            "summary_pending",
            [{"term": {"source_id": "s"}}, {"term": {"summary_status": "pending"}}],
        ),
    ],
)
def test_r9_a_count_is_a_size_zero_search_with_exact_total(
    target: CountTarget, filters: list[object]
) -> None:
    assert queries.count_body(target, "s") == {
        "size": 0,
        "track_total_hits": True,
        "query": {"bool": {"filter": filters}},
    }


def test_document_count_does_not_filter_by_index_status() -> None:
    """登録文書数は `index_status` を問わない(AAPI-P-23)。"""
    filters = dig(queries.count_body("document_count", "s"), "query", "bool", "filter")

    assert filters == [{"term": {"source_id": "s"}}]


def test_r11_looks_up_document_ids_without_reading_the_source() -> None:
    assert queries.existing_ids_body(["d1", "d2"]) == {
        "size": 2,
        "_source": False,
        "track_total_hits": False,
        "query": {"ids": {"values": ["d1", "d2"]}},
    }


@pytest.mark.parametrize(
    ("page", "items_per_page"),
    [(1, 25), (400, 25), (100, 100), (1, 100), (200, 50)],
)
def test_the_window_boundary_is_accepted(page: int, items_per_page: int) -> None:
    request = PageRequest(page=page, items_per_page=items_per_page, descending=False)

    assert request.offset + request.items_per_page <= 10_000


@pytest.mark.parametrize(
    ("page", "items_per_page"),
    [(0, 25), (401, 25), (101, 100), (1, 101), (1, 0), (-1, 25)],
)
def test_a_page_outside_the_window_is_rejected(page: int, items_per_page: int) -> None:
    with pytest.raises(ValueError, match=r"page|items_per_page"):
        PageRequest(page=page, items_per_page=items_per_page, descending=False)
