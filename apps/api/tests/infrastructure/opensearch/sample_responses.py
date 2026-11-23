"""OpenSearch の応答の組み立て(台本用)。実機の応答の形に合わせた最小の形。"""

from collections.abc import Mapping, Sequence


def hit(record_id: str, source: Mapping[str, object] | None = None) -> dict[str, object]:
    result: dict[str, object] = {"_id": record_id}
    if source is not None:
        result["_source"] = dict(source)
    return result


def search_response(
    hits: Sequence[Mapping[str, object]] = (),
    *,
    total: int | None = None,
    aggregations: Mapping[str, object] | None = None,
    timed_out: bool = False,
    failed_shards: int = 0,
) -> dict[str, object]:
    """`total` を省くと、`hits.total` のない応答(`track_total_hits: false`)になる。"""
    hits_section: dict[str, object] = {"hits": list(hits)}
    if total is not None:
        hits_section["total"] = {"value": total, "relation": "eq"}
    response: dict[str, object] = {
        "took": 1,
        "timed_out": timed_out,
        "_shards": {
            "total": 1,
            "successful": 1 - failed_shards,
            "skipped": 0,
            "failed": failed_shards,
        },
        "hits": hits_section,
    }
    if aggregations is not None:
        response["aggregations"] = dict(aggregations)
    return response


def mget_doc(
    record_id: str, source: Mapping[str, object] | None = None, *, found: bool = True
) -> dict[str, object]:
    doc: dict[str, object] = {"_index": "x", "_id": record_id, "found": found}
    if found and source is not None:
        doc["_source"] = dict(source)
    return doc


def mget_response(*docs: Mapping[str, object]) -> dict[str, object]:
    return {"docs": list(docs)}


def msearch_response(*sub_responses: Mapping[str, object]) -> dict[str, object]:
    return {"took": 1, "responses": list(sub_responses)}


SUB_REQUEST_ERROR: dict[str, object] = {
    "status": 500,
    "error": {"type": "search_phase_execution_exception", "reason": "secret-reason"},
}
