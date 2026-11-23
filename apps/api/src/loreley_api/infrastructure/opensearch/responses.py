"""応答の検証と素の値への変換(C 3.2 の「部分的な失敗を成功と読まない」。AAA-P-39)。

OpenSearch は HTTP 200 のまま一部の失敗を返しうる。応答を使う前に次を確かめる。
- `search`・`msearch`(サブ要求ごと): `timed_out=true`・`_shards.failed>0`・`_shards`・`hits` が
  期待の形でない応答は失敗(部分的な結果を使わない)。
- `mget`: `docs[i]` に `error` がある、または `found` が真偽値でない文書は、その文書の取得が失敗
  (`found=false` の「記録なし」とは読まない)。他の文書の結果は使う。

失敗は例外(`failure.py`)で表し、Reader が `Failed` にする。`mget` の文書ごとの失敗は、他の文書の
結果を残すため、`Failed` の値として返す。
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from loreley_api.common.results import FailureTarget, Ok
from loreley_api.infrastructure.opensearch.failure import (
    DocumentError,
    PartialResponseError,
    ResponseShapeError,
    failed_from_exception,
)
from loreley_api.infrastructure.opensearch.ports import RecordResults, StoredRecord


@dataclass(frozen=True)
class ParsedSearch:
    # `track_total_hits: false` の問い合わせの応答は `total` を持たないので `None`。
    total: int | None
    hits: tuple[StoredRecord, ...]
    aggregations: Mapping[str, object]


@dataclass(frozen=True)
class CountedSearch:
    """総件数(`hits.total`)つきの検索結果。"""

    total: int
    hits: tuple[StoredRecord, ...]
    aggregations: Mapping[str, object]


def as_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ResponseShapeError("expected an object")
    return value


def as_list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ResponseShapeError("expected an array")
    return value


def as_int(value: object) -> int:
    # `bool` は `int` の子だが、件数として読まない。
    if isinstance(value, bool) or not isinstance(value, int):
        raise ResponseShapeError("expected an integer")
    return value


def as_str(value: object) -> str:
    if not isinstance(value, str):
        raise ResponseShapeError("expected a string")
    return value


def parse_search(response: object) -> ParsedSearch:
    """`search` の応答(または `msearch` のサブ応答)を検証して、素の値にする。"""
    body = as_mapping(response)
    timed_out = body.get("timed_out")
    if timed_out is True:
        raise PartialResponseError(timed_out=True)
    if timed_out is not False:
        raise ResponseShapeError("timed_out is not a boolean")
    shards = as_mapping(body.get("_shards"))
    if as_int(shards.get("failed")) > 0:
        raise PartialResponseError(timed_out=False)

    hits_section = as_mapping(body.get("hits"))
    hits = parse_hits(hits_section)
    total = _parse_total(hits_section["total"]) if "total" in hits_section else None
    aggregations = body.get("aggregations")
    return ParsedSearch(
        total=total,
        hits=hits,
        aggregations=as_mapping(aggregations) if aggregations is not None else {},
    )


def parse_hits(hits_section: Mapping[str, object]) -> tuple[StoredRecord, ...]:
    """`hits` の節(`search` の応答と、`top_hits` 集計で同じ形)から、ヒットの一覧を取り出す。"""
    return tuple(_parse_hit(hit) for hit in as_list(hits_section.get("hits")))


def parse_counted_search(response: object) -> CountedSearch:
    """`track_total_hits: true` の問い合わせの応答。総件数がなければ形の異常。"""
    parsed = parse_search(response)
    if parsed.total is None:
        raise ResponseShapeError("total is missing")
    return CountedSearch(parsed.total, parsed.hits, parsed.aggregations)


def parse_msearch(response: object, expected_count: int) -> list[object]:
    """`msearch` の応答から、サブ応答を要求と同じ順に取り出す(数が違えば形の異常)。"""
    responses = as_list(as_mapping(response).get("responses"))
    if len(responses) != expected_count:
        raise ResponseShapeError("unexpected number of responses")
    return responses


def is_sub_request_error(sub_response: object) -> bool:
    """`msearch` のサブ応答が、サブ要求ごとのエラー(`error`)か。"""
    return isinstance(sub_response, Mapping) and "error" in sub_response


def parse_mget(
    response: object,
    ids: Sequence[str],
    *,
    target: FailureTarget,
    operation: str,
    expected_record_type: str | None = None,
) -> RecordResults:
    """`mget` の応答を、要求した ID ごとの結果にする。

    `expected_record_type` を指定すると、`found=true` でも `record_type` が違う文書は
    「記録なし」(`Ok(None)`)にする(ロック・スキップ記録の ID が `job_id` として渡されたとき
    に 404 にするため。C 3.2)。
    """
    docs = as_list(as_mapping(response).get("docs"))
    if len(docs) != len(ids):
        raise ResponseShapeError("unexpected number of documents")
    results: RecordResults = {}
    for requested_id, doc in zip(ids, docs, strict=True):
        try:
            record = _parse_document(doc, requested_id, expected_record_type)
        except (ResponseShapeError, DocumentError):
            results[requested_id] = failed_from_exception(
                DocumentError(), target, operation=operation
            )
            continue
        results[requested_id] = Ok(record)
    return results


def _parse_document(
    doc: object, requested_id: str, expected_record_type: str | None
) -> StoredRecord | None:
    document = as_mapping(doc)
    if "error" in document:
        raise DocumentError("document error")
    found = document.get("found")
    if not isinstance(found, bool):
        raise ResponseShapeError("found is not a boolean")
    if document.get("_id") != requested_id:
        raise ResponseShapeError("unexpected document id")
    if not found:
        return None
    # `_source: false` の取得では `_source` がない。
    source = as_mapping(document["_source"]) if "_source" in document else {}
    if expected_record_type is not None and source.get("record_type") != expected_record_type:
        return None
    return StoredRecord(record_id=requested_id, source=source)


def _parse_hit(hit: object) -> StoredRecord:
    hit_mapping = as_mapping(hit)
    source = hit_mapping.get("_source")
    return StoredRecord(
        record_id=as_str(hit_mapping.get("_id")),
        source=as_mapping(source) if source is not None else {},
    )


def _parse_total(total: object) -> int:
    total_mapping = as_mapping(total)
    # `track_total_hits: true` なら常に `eq`。`gte` は頭打ちの値で、総件数として使えない。
    if total_mapping.get("relation", "eq") != "eq":
        raise ResponseShapeError("total is not exact")
    return as_int(total_mapping.get("value"))
