"""`infra/opensearch/schema/*.json` との契約(C 3.5。C 11章 9)。

`queries.py` が組み立てるクエリのフィルタ・並べ替え・集計の項目が、スキーマで期待の型
(`keyword`・`date`)にマップされていることを確かめる。スキーマを変えるとテストが落ち、
本書(C 3.5)とクエリの更新漏れに気づける。

クエリの本文から項目を取り出して検査するので、`queries.py` に新しい項目を足すと、このテストの
期待表(`EXPECTED_FIELD_TYPES`)の更新が要る。
"""

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from loreley_api.infrastructure.opensearch import JobListQuery, PageRequest, queries
from loreley_api.infrastructure.opensearch.ports import CountTarget

SCHEMA_DIR = Path(__file__).resolve().parents[4] / "infra" / "opensearch" / "schema"

PAGE = PageRequest(page=1, items_per_page=25, descending=True)
Body = dict[str, object]

# C 3.5 の表: フィルタ・並べ替え・集計に使う項目の型(索引 → 項目 → 型)。
EXPECTED_FIELD_TYPES: dict[str, dict[str, str]] = {
    "sources": {"source_id": "keyword"},
    "jobs": {
        "record_type": "keyword",
        "source_id": "keyword",
        "job_type": "keyword",
        "status": "keyword",
        "job_id": "keyword",
        "document_id": "keyword",
        "queued_at": "date",
        "finished_at": "date",
        "last_skipped_at": "date",
        "last_detected_at": "date",
    },
    "search-index": {
        "source_id": "keyword",
        "index_status": "keyword",
        "summary_status": "keyword",
        "document_id": "keyword",
        "last_seen_at": "date",
        "indexed_at": "date",
    },
}
EXPECTED_DYNAMIC = {"sources": "strict", "jobs": False, "search-index": "strict"}

COUNT_TARGETS: tuple[CountTarget, ...] = (
    "document_count",
    "skipped",
    "oversize",
    "extract_failed",
    "summary_pending",
)
JOB_STORE_COUNT_TARGETS = {"skipped", "oversize"}


def bodies_by_index() -> dict[str, list[Body]]:
    """`queries.py` の全ビルダーの出力(索引ごと)。"""
    return {
        "sources": [queries.sources_all_body()],
        "jobs": [
            queries.latest_by_source_body(["a"]),
            queries.jobs_list_body(JobListQuery(page=PAGE)),
            queries.jobs_list_body(
                JobListQuery(page=PAGE, source_id="a", statuses=("queued", "running"))
            ),
            queries.jobs_list_body(JobListQuery(page=PAGE, source_id="a", statuses=("failed",))),
            queries.latest_crawl_id_body("a"),
            queries.skipped_list_body("a", PAGE),
            queries.oversize_list_body("a", PAGE),
            *(
                queries.count_body(target, "a")
                for target in COUNT_TARGETS
                if target in JOB_STORE_COUNT_TARGETS
            ),
        ],
        "search-index": [
            queries.extract_failed_list_body("a", PAGE),
            queries.summary_pending_list_body("a", PAGE),
            queries.count_by_source_body(["a"]),
            queries.existing_ids_body(["d"]),
            *(
                queries.count_body(target, "a")
                for target in COUNT_TARGETS
                if target not in JOB_STORE_COUNT_TARGETS
            ),
        ],
    }


def load_mappings(index: str) -> Mapping[str, Mapping[str, object]]:
    schema = json.loads((SCHEMA_DIR / f"{index}.json").read_text(encoding="utf-8"))
    return schema["mappings"]


def mapped_type(index: str, field: str) -> str | None:
    properties = load_mappings(index)["properties"]
    assert isinstance(properties, dict)
    definition = properties.get(field)
    return definition["type"] if definition else None


def collect_field_usages(node: object) -> dict[str, set[str]]:
    """クエリ本文で、フィルタ・並べ替え・集計に使う項目(役割 → 項目名の集合)。

    `_source`(読むだけの項目)と `ids`(`_id` の指定)は、マッピングに依存しないので対象外。
    """
    usages: dict[str, set[str]] = {"filter": set(), "sort": set(), "aggregation": set()}
    _collect(node, usages)
    return usages


def _collect(node: object, usages: dict[str, set[str]]) -> None:
    if isinstance(node, list):
        for item in node:
            _collect(item, usages)
        return
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if key == "_source":
            continue
        if key in {"term", "terms"} and isinstance(value, dict):
            if "field" in value:  # 集計の `terms`: {"field": ..., "size": ...}
                usages["aggregation"].add(str(value["field"]))
            else:  # クエリの `term`・`terms`: {"<項目>": 値}
                usages["filter"].update(value)
            continue
        if key == "max" and isinstance(value, dict):
            usages["aggregation"].add(str(value["field"]))
            continue
        if key == "sort":
            assert isinstance(value, list)
            for entry in value:
                assert isinstance(entry, dict)
                usages["sort"].update(entry)
            continue
        _collect(value, usages)


# --- スキーマが期待どおりであること ---


@pytest.mark.parametrize("index", sorted(EXPECTED_FIELD_TYPES))
def test_the_fields_used_by_the_queries_are_mapped_with_the_expected_types(index: str) -> None:
    for field, expected_type in EXPECTED_FIELD_TYPES[index].items():
        assert mapped_type(index, field) == expected_type, f"{index}.{field}"


@pytest.mark.parametrize("index", sorted(EXPECTED_DYNAMIC))
def test_the_dynamic_mode_is_the_one_the_queries_assume(index: str) -> None:
    """`dynamic: false` の `loreley-jobs` では、未マップの項目は `_source` からだけ読める。"""
    assert load_mappings(index)["dynamic"] == EXPECTED_DYNAMIC[index]


def test_the_connector_config_is_not_searchable_and_is_excluded_from_the_listing() -> None:
    properties = load_mappings("sources")["properties"]
    assert isinstance(properties, dict)
    assert properties["connector_config"] == {"type": "object", "enabled": False}
    assert queries.sources_all_body()["_source"] == {"excludes": ["connector_config"]}


# --- クエリがスキーマに沿っていること ---


@pytest.mark.parametrize("index", sorted(EXPECTED_FIELD_TYPES))
def test_every_field_the_queries_filter_sort_or_aggregate_on_is_declared_in_the_contract(
    index: str,
) -> None:
    used: set[str] = set()
    for body in bodies_by_index()[index]:
        for fields in collect_field_usages(body).values():
            used |= fields

    assert used <= set(EXPECTED_FIELD_TYPES[index])
    assert used, "the detector found no field (it would miss every violation)"


@pytest.mark.parametrize("index", sorted(EXPECTED_FIELD_TYPES))
def test_the_queries_use_keyword_for_filters_and_keyword_or_date_for_sorts(index: str) -> None:
    for body in bodies_by_index()[index]:
        usages = collect_field_usages(body)
        for field in usages["filter"]:
            assert mapped_type(index, field) == "keyword", f"filter {index}.{field}"
        for field in usages["sort"]:
            assert mapped_type(index, field) in {"keyword", "date"}, f"sort {index}.{field}"


@pytest.mark.parametrize("index", sorted(EXPECTED_FIELD_TYPES))
def test_the_aggregations_use_keyword_for_terms_and_date_for_max(index: str) -> None:
    for body in bodies_by_index()[index]:
        _check_aggregations(index, body)


def _check_aggregations(index: str, node: object) -> None:
    if isinstance(node, list):
        for item in node:
            _check_aggregations(index, item)
        return
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if key == "aggs":
            assert isinstance(value, dict)
            for aggregation in value.values():
                _check_aggregation(index, aggregation)
        _check_aggregations(index, value)


def _check_aggregation(index: str, aggregation: object) -> None:
    assert isinstance(aggregation, dict)
    terms = aggregation.get("terms")
    if isinstance(terms, dict):
        assert mapped_type(index, str(terms["field"])) == "keyword"
    maximum = aggregation.get("max")
    if isinstance(maximum, dict):
        assert mapped_type(index, str(maximum["field"])) == "date"


def test_the_aggregation_check_covers_both_terms_and_max() -> None:
    jobs_aggregations = collect_field_usages(queries.latest_by_source_body(["a"]))["aggregation"]

    assert jobs_aggregations == {"source_id", "finished_at"}


def test_no_query_reads_the_body_text_or_the_summary() -> None:
    """`content`・`summary` は読まない(C 3.6)。`_source` の項目名にも現れない。"""
    forbidden = {"content", "summary", "connector_config", "finish_notice"}
    for bodies in bodies_by_index().values():
        for body in bodies:
            source = body.get("_source")
            includes = source.get("includes", []) if isinstance(source, dict) else []
            assert forbidden.isdisjoint(includes)


# --- 検出器の自己テスト(合成のクエリ) ---


def test_the_detector_finds_fields_in_nested_clauses_and_aggregations() -> None:
    body = {
        "query": {
            "bool": {"filter": [{"term": {"a": 1}}, {"terms": {"b": [1]}}, {"ids": {"values": []}}]}
        },
        "sort": [{"c": "asc"}, {"d": "desc"}],
        "_source": {"includes": ["not_a_filter_field"]},
        "aggs": {
            "x": {
                "terms": {"field": "e", "size": 3},
                "aggs": {"y": {"max": {"field": "f"}}, "z": {"top_hits": {"sort": [{"g": "asc"}]}}},
            }
        },
    }

    assert collect_field_usages(body) == {
        "filter": {"a", "b"},
        "sort": {"c", "d", "g"},
        "aggregation": {"e", "f"},
    }


def test_an_unmapped_field_has_no_type() -> None:
    """`dynamic: false` の `loreley-jobs` の `failure_reason` は検索に使えない(`_source` だけ)。"""
    assert mapped_type("jobs", "failure_reason") is None


def test_the_bodies_cover_every_query_builder() -> None:
    """ビルダーを足したのに、この契約テストの対象に入れ忘れることを防ぐ。"""
    builders = {
        name for name in dir(queries) if name.endswith("_body") and not name.startswith("_")
    }
    assert builders == {
        "sources_all_body",
        "latest_by_source_body",
        "jobs_list_body",
        "latest_crawl_id_body",
        "skipped_list_body",
        "oversize_list_body",
        "extract_failed_list_body",
        "summary_pending_list_body",
        "count_by_source_body",
        "count_body",
        "existing_ids_body",
    }
