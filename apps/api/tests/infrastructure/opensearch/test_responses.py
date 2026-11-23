"""部分的な失敗を成功と読まないこと(C 3.2。AAA-P-39。C 11章 6)。"""

import pytest

from loreley_api.common.results import Failed, Ok
from loreley_api.infrastructure.opensearch.failure import PartialResponseError, ResponseShapeError
from loreley_api.infrastructure.opensearch.ports import RecordResults, StoredRecord
from loreley_api.infrastructure.opensearch.responses import (
    parse_counted_search,
    parse_mget,
    parse_msearch,
    parse_search,
)
from tests.infrastructure.opensearch.sample_responses import (
    hit,
    mget_doc,
    mget_response,
    search_response,
)


def test_a_search_response_becomes_hits_and_a_total() -> None:
    response = search_response([hit("a", {"x": 1}), hit("b")], total=12_345)

    parsed = parse_counted_search(response)

    assert parsed.total == 12_345  # 窓(10,000)を超えても正確
    assert parsed.hits == (StoredRecord("a", {"x": 1}), StoredRecord("b", {}))


def test_a_response_without_a_total_is_allowed_when_the_total_is_not_requested() -> None:
    assert parse_search(search_response([hit("a")])).total is None


def test_a_missing_total_is_a_shape_error_when_the_total_is_required() -> None:
    with pytest.raises(ResponseShapeError):
        parse_counted_search(search_response([hit("a")]))


def test_a_timed_out_search_is_a_timeout_failure() -> None:
    with pytest.raises(PartialResponseError) as caught:
        parse_search(search_response([hit("a")], total=1, timed_out=True))

    assert caught.value.timed_out is True


def test_failed_shards_make_the_whole_response_a_failure() -> None:
    with pytest.raises(PartialResponseError) as caught:
        parse_search(search_response([hit("a")], total=1, failed_shards=1))

    assert caught.value.timed_out is False


@pytest.mark.parametrize(
    "response",
    [
        None,
        [],
        "x",
        {},
        {"timed_out": False, "hits": {"hits": []}},  # `_shards` がない
        {"timed_out": False, "_shards": {}, "hits": {"hits": []}},  # `failed` がない
        {"timed_out": False, "_shards": {"failed": "0"}, "hits": {"hits": []}},
        {"timed_out": False, "_shards": {"failed": True}, "hits": {"hits": []}},
        {"timed_out": False, "_shards": {"failed": 0}},  # `hits` がない
        {"timed_out": False, "_shards": {"failed": 0}, "hits": {}},
        {"timed_out": False, "_shards": {"failed": 0}, "hits": {"hits": "x"}},
        {"timed_out": False, "_shards": {"failed": 0}, "hits": {"hits": ["x"]}},
        {"timed_out": False, "_shards": {"failed": 0}, "hits": {"hits": [{"_source": {}}]}},
        {"timed_out": False, "_shards": {"failed": 0}, "hits": {"hits": [{"_id": 1}]}},
        {
            "timed_out": False,
            "_shards": {"failed": 0},
            "hits": {"hits": [{"_id": "a", "_source": 1}]},
        },
        {"_shards": {"failed": 0}, "hits": {"hits": []}},  # `timed_out` がない
        {"timed_out": "false", "_shards": {"failed": 0}, "hits": {"hits": []}},
        {"timed_out": False, "_shards": {"failed": 0}, "hits": {"hits": [], "total": 5}},
        {
            "timed_out": False,
            "_shards": {"failed": 0},
            "hits": {"hits": [], "total": {"value": 10_000, "relation": "gte"}},
        },
        {
            "timed_out": False,
            "_shards": {"failed": 0},
            "hits": {"hits": [], "total": {"value": "1", "relation": "eq"}},
        },
    ],
)
def test_a_malformed_search_response_is_a_shape_error(response: object) -> None:
    with pytest.raises(ResponseShapeError):
        parse_search(response)


def test_msearch_returns_the_sub_responses_in_request_order() -> None:
    sub_responses = [{"a": 1}, {"b": 2}]

    assert parse_msearch({"responses": sub_responses}, 2) == sub_responses


@pytest.mark.parametrize("response", [{}, {"responses": "x"}, {"responses": [{}]}, []])
def test_msearch_with_a_wrong_number_of_responses_is_a_shape_error(response: object) -> None:
    with pytest.raises(ResponseShapeError):
        parse_msearch(response, 2)


def parse(
    response: object, ids: list[str], expected_record_type: str | None = None
) -> RecordResults:
    return parse_mget(
        response,
        ids,
        target="store",
        operation="test.operation",
        expected_record_type=expected_record_type,
    )


def test_mget_returns_a_result_per_requested_id() -> None:
    response = mget_response(mget_doc("a", {"x": 1}), mget_doc("b", found=False))

    results = parse(response, ["a", "b"])

    assert results == {"a": Ok(StoredRecord("a", {"x": 1})), "b": Ok(None)}


def test_an_mget_document_error_fails_only_that_document() -> None:
    """他の文書の結果は使える。`found=false`(記録なし)とは区別する。"""
    response = mget_response(
        mget_doc("a", {"x": 1}),
        {"_index": "i", "_id": "b", "error": {"type": "x", "reason": "secret"}},
        mget_doc("c", found=False),
    )

    results = parse(response, ["a", "b", "c"])

    assert results["a"] == Ok(StoredRecord("a", {"x": 1}))
    assert results["b"] == Failed("unavailable", "store", "DocumentError")
    assert results["c"] == Ok(None)


@pytest.mark.parametrize("found", ["true", 1, None])
def test_an_mget_document_whose_found_is_not_a_boolean_is_a_failure(found: object) -> None:
    doc = {"_id": "a", "found": found, "_source": {}}

    results = parse(mget_response(doc), ["a"])

    assert results == {"a": Failed("unavailable", "store", "DocumentError")}


def test_an_mget_document_without_found_is_a_failure() -> None:
    results = parse(mget_response({"_id": "a"}), ["a"])

    assert results == {"a": Failed("unavailable", "store", "DocumentError")}


@pytest.mark.parametrize(
    "doc",
    [
        "not an object",
        {"_id": "other", "found": True, "_source": {}},  # 要求していない ID
        {"_id": "a", "found": True, "_source": "x"},
    ],
)
def test_a_malformed_mget_document_is_a_failure(doc: object) -> None:
    results = parse({"docs": [doc]}, ["a"])

    assert results == {"a": Failed("unavailable", "store", "DocumentError")}


@pytest.mark.parametrize("response", [{}, {"docs": "x"}, {"docs": []}, []])
def test_an_mget_response_with_a_wrong_number_of_documents_is_a_shape_error(
    response: object,
) -> None:
    with pytest.raises(ResponseShapeError):
        parse(response, ["a"])


def test_a_record_of_another_type_is_not_found_when_a_record_type_is_expected() -> None:
    """ロックの ID を `job_id` として渡されたときに 404 にするため(C 3.2)。"""
    response = mget_response(
        mget_doc("lock-a", {"record_type": "lock"}), mget_doc("job-b", {"record_type": "job"})
    )

    results = parse(response, ["lock-a", "job-b"], expected_record_type="job")

    assert results["lock-a"] == Ok(None)
    assert results["job-b"] == Ok(StoredRecord("job-b", {"record_type": "job"}))


def test_a_document_without_a_source_is_found_with_an_empty_source() -> None:
    """存在確認(`_source: false`)の取得。"""
    response = mget_response(mget_doc("a"))

    assert parse(response, ["a"]) == {"a": Ok(StoredRecord("a", {}))}
