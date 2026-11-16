"""`RecordFilter`・`SortKey` から OpenSearch のクエリ DSL への変換。"""

from collections.abc import Sequence
from typing import Any

from loreley_crawler.infrastructure.opensearch.queries import RecordFilter, SortKey


def build_record_query(record_filter: RecordFilter) -> dict[str, Any]:
    filters: list[dict[str, Any]] = [
        {"term": {name: value}} for name, value in record_filter.equals.items()
    ]
    filters += [{"terms": {name: list(values)}} for name, values in record_filter.one_of.items()]
    filters += [{"exists": {"field": name}} for name in record_filter.exists]
    must_not = [{"exists": {"field": name}} for name in record_filter.missing]
    if not filters and not must_not:
        return {"match_all": {}}
    return {"bool": {"filter": filters, "must_not": must_not}}


def build_sort(sort: Sequence[SortKey]) -> list[dict[str, str]]:
    return [{key.field_name: "desc" if key.descending else "asc"} for key in sort]
