"""応答の解釈: HTTP ステータスとエラーコードから型付きの結果へ(architecture 7.8。indexer-api 3.4)。

`IndexerUnavailable`: 500・503(接続エラー・タイムアウトは test_failures.py)。
`IndexerRejected`: 400・409・404・405・その他。ステータスとエラーコードを持つ。
"""

from typing import Any

import pytest

from loreley_crawler.infrastructure.indexer_client import (
    MALFORMED_RESPONSE,
    BatchResults,
    Change,
    CrawlStatus,
    DeletionRecordsDeleted,
    DiscardResult,
    DocumentFailed,
    DocumentRegistered,
    DocumentsDeleted,
    FailureType,
    IndexerRejected,
    IndexerUnavailable,
    LastSeenEntry,
    LastSeenResult,
    LastSeenResults,
    Succeeded,
)
from tests.fakes.local_http_server import Reply
from tests.infrastructure.indexer_client.support import (
    CRAWL_ID,
    DOCUMENT_ID,
    EXTERNAL_ID,
    OPERATIONS,
    SOURCE_ID,
    Operation,
    batch_of,
    call_with,
    last_seen_of,
    serving,
)


def error_reply(status: int, code: str) -> Reply:
    return Reply(
        status=status,
        body={"error": {"code": code, "message": "SENTINEL-MESSAGE", "retryable": False}},
    )


# --- 失敗の区分(全 API に共通) ---


@pytest.mark.parametrize("operation", OPERATIONS.values(), ids=OPERATIONS.keys())
@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (error_reply(500, "internal_error"), IndexerUnavailable("http_500")),
        (error_reply(503, "unavailable"), IndexerUnavailable("http_503")),
        (error_reply(400, "invalid_request"), IndexerRejected(400, "invalid_request")),
        (error_reply(409, "lock_not_owned"), IndexerRejected(409, "lock_not_owned")),
        (error_reply(409, "crawl_start_conflict"), IndexerRejected(409, "crawl_start_conflict")),
        (error_reply(404, "crawl_not_found"), IndexerRejected(404, "crawl_not_found")),
        (error_reply(404, "not_found"), IndexerRejected(404, "not_found")),
        (error_reply(405, "method_not_allowed"), IndexerRejected(405, "method_not_allowed")),
        (error_reply(413, "http_error"), IndexerRejected(413, "http_error")),
        (error_reply(502, "http_error"), IndexerRejected(502, "http_error")),
        (Reply(status=404, raw=b"<html>not json</html>"), IndexerRejected(404, None)),
        (Reply(status=409, body={"error": "not an object"}), IndexerRejected(409, None)),
        (Reply(status=400, body={"error": {"code": 5}}), IndexerRejected(400, None)),
        (Reply(status=401, raw=b""), IndexerRejected(401, None)),
    ],
    ids=lambda value: str(value)[:40],
)
def test_error_responses_are_classified_the_same_way_for_every_api(
    operation: Operation, reply: Reply, expected: object
) -> None:
    assert call_with(reply, operation) == expected


def test_a_redirect_is_rejected_and_not_followed() -> None:
    reply = Reply(status=302, headers={"location": "/elsewhere"}, raw=b"")
    with serving(reply) as (client, server):
        assert OPERATIONS["status"](client) == IndexerRejected(302, None)
        assert len(server.requests) == 1


def test_the_indexer_error_message_never_appears_in_the_result() -> None:
    result = call_with(error_reply(409, "lock_not_owned"), OPERATIONS["delete_documents"])

    assert "SENTINEL-MESSAGE" not in repr(result)


# --- 成功の応答 ---

ENTRY_OK = {
    "external_id": EXTERNAL_ID,
    "document_id": DOCUMENT_ID,
    "status": "ok",
    "change": "created",
    "extract_failed": False,
}
ENTRY_FAILED = {
    "external_id": "page-10024",
    "document_id": "7f2216b2a91e74fe53ce071ed0bd8dcebccaa904f9a8d8004f592b0a4210a9c5",
    "status": "failed",
    "failure_type": "document_rejected",
    "message": "the document was rejected (mapper_parsing_exception)",
}


def test_start_and_finish_succeed_on_200_and_202_whatever_the_body() -> None:
    assert (
        call_with(Reply(body={"crawl_id": CRAWL_ID, "status": "running"}), OPERATIONS["start"])
        == Succeeded()
    )
    assert call_with(Reply(status=200, raw=b""), OPERATIONS["start"]) == Succeeded()
    assert call_with(Reply(status=202, raw=b""), OPERATIONS["finish"]) == Succeeded()


def test_the_batch_response_is_parsed_per_document_in_order() -> None:
    reply = Reply(
        body={
            "results": [
                ENTRY_OK,
                ENTRY_FAILED,
                {**ENTRY_OK, "change": "unchanged", "extract_failed": True},
            ]
        }
    )

    result = call_with(reply, batch_of(EXTERNAL_ID, "page-10024", EXTERNAL_ID))

    assert result == BatchResults(
        documents=(
            DocumentRegistered(EXTERNAL_ID, DOCUMENT_ID, Change.CREATED, extract_failed=False),
            DocumentFailed(
                "page-10024", ENTRY_FAILED["document_id"], FailureType.DOCUMENT_REJECTED
            ),
            DocumentRegistered(EXTERNAL_ID, DOCUMENT_ID, Change.UNCHANGED, extract_failed=True),
        )
    )


@pytest.mark.parametrize("failure_type", list(FailureType))
def test_every_failure_type_of_a_document_is_understood(failure_type: FailureType) -> None:
    entry = {**ENTRY_FAILED, "failure_type": failure_type.value}

    result = call_with(Reply(body={"results": [entry]}), batch_of("page-10024"))

    assert isinstance(result, BatchResults)
    assert result.documents[0].failure_type == failure_type


def test_the_last_seen_response_is_parsed_per_document_in_order() -> None:
    reply = Reply(
        body={
            "results": [
                {"document_id": DOCUMENT_ID, "result": "updated"},
                {"document_id": "b" * 64, "result": "not_found"},
                {"document_id": "c" * 64, "result": "update_conflict"},
                {"document_id": "d" * 64, "result": "lock_not_owned"},
                {"document_id": "e" * 64, "result": "unchanged"},
            ]
        }
    )

    operation = last_seen_of(DOCUMENT_ID, "b" * 64, "c" * 64, "d" * 64, "e" * 64)
    assert call_with(reply, operation) == LastSeenResults(
        entries=(
            LastSeenEntry(DOCUMENT_ID, LastSeenResult.UPDATED),
            LastSeenEntry("b" * 64, LastSeenResult.NOT_FOUND),
            LastSeenEntry("c" * 64, LastSeenResult.UPDATE_CONFLICT),
            LastSeenEntry("d" * 64, LastSeenResult.LOCK_NOT_OWNED),
            LastSeenEntry("e" * 64, LastSeenResult.UNCHANGED),
        )
    )


def test_a_running_status_with_waiting_for_omits_the_unrecorded_fields() -> None:
    reply = Reply(
        body={
            "crawl_id": "job-2",
            "source_id": SOURCE_ID,
            "status": "running",
            "finish_received_at": "2026-11-09T01:20:05Z",
            "waiting_for": "job-1",
        }
    )

    assert call_with(reply, OPERATIONS["status"]) == CrawlStatus(
        crawl_id="job-2",
        source_id=SOURCE_ID,
        status="running",
        finish_received_at="2026-11-09T01:20:05Z",
        waiting_for="job-1",
    )


def test_a_deleted_status_carries_the_numbers_and_the_times_as_returned() -> None:
    reply = Reply(
        body={
            "crawl_id": CRAWL_ID,
            "source_id": SOURCE_ID,
            "status": "deleted",
            "forced": False,
            "enumerated_count": 1203,
            "n_seen": 1202,
            "e_missing": 1,
            "target_count": 12,
            "denominator": 1215,
            "ttl": 86400,  # 使わない項目は読まない
            "ratio_threshold": 0.5,
            "min_delete_count": 10,
            "deleted_count": 12,
            "finish_received_at": "2026-11-09T01:12:31Z",
            "deletion_started_at": "2026-11-09T01:12:40Z",
            "finished_at": "2026-11-09T01:12:55Z",
        }
    )

    assert call_with(reply, OPERATIONS["status"]) == CrawlStatus(
        crawl_id=CRAWL_ID,
        source_id=SOURCE_ID,
        status="deleted",
        forced=False,
        target_count=12,
        denominator=1215,
        deleted_count=12,
        enumerated_count=1203,
        n_seen=1202,
        e_missing=1,
        finish_received_at="2026-11-09T01:12:31Z",
        deletion_started_at="2026-11-09T01:12:40Z",
        finished_at="2026-11-09T01:12:55Z",
    )


def test_a_failed_status_carries_the_reason() -> None:
    reply = Reply(
        body={
            "crawl_id": "j",
            "source_id": SOURCE_ID,
            "status": "failed",
            "reason": "indexer_restart",
        }
    )

    result = call_with(reply, OPERATIONS["status"])

    assert isinstance(result, CrawlStatus)
    assert (result.status, result.reason) == ("failed", "indexer_restart")


def test_the_source_deletion_responses_are_parsed() -> None:
    assert call_with(
        Reply(body={"discarded_crawl_ids": ["job-1", "job-2"]}), OPERATIONS["discard"]
    ) == DiscardResult(("job-1", "job-2"))
    assert call_with(
        Reply(body={"deleted_count": 1215}), OPERATIONS["delete_documents"]
    ) == DocumentsDeleted(1215)
    assert call_with(
        Reply(body={"deleted": False}), OPERATIONS["delete_records"]
    ) == DeletionRecordsDeleted(False)


# --- 成功のステータスの違い(開始通知などは 200、終了通知は 202) ---


@pytest.mark.parametrize("operation", OPERATIONS.values(), ids=OPERATIONS.keys())
@pytest.mark.parametrize("status", [201, 204, 206])
def test_a_2xx_other_than_the_contract_status_is_malformed_for_every_api(
    operation: Operation, status: int
) -> None:
    assert call_with(Reply(status=status, raw=b"{}"), operation) == IndexerRejected(
        status, MALFORMED_RESPONSE
    )


def test_the_finish_status_is_202_and_the_others_are_200() -> None:
    assert call_with(Reply(status=200, raw=b""), OPERATIONS["finish"]) == IndexerRejected(
        200, MALFORMED_RESPONSE
    )
    assert call_with(Reply(status=202, raw=b""), OPERATIONS["start"]) == IndexerRejected(
        202, MALFORMED_RESPONSE
    )


# --- 要請と結果の対応(件数・ID の並び) ---

OTHER_ID = "7f2216b2a91e74fe53ce071ed0bd8dcebccaa904f9a8d8004f592b0a4210a9c5"


@pytest.mark.parametrize(
    "results",
    [
        [],  # 件数が少ない
        [
            {"document_id": DOCUMENT_ID, "result": "updated"},
            {"document_id": OTHER_ID, "result": "updated"},
        ],  # 件数が多い
        [{"document_id": OTHER_ID, "result": "updated"}],  # 別の ID
    ],
    ids=["fewer", "more", "other-id"],
)
def test_last_seen_results_that_do_not_match_the_requested_ids_are_malformed(
    results: list[dict[str, str]],
) -> None:
    reply = Reply(body={"results": results})

    assert call_with(reply, last_seen_of(DOCUMENT_ID)) == IndexerRejected(200, MALFORMED_RESPONSE)


def test_last_seen_results_in_a_different_order_are_malformed() -> None:
    reply = Reply(
        body={
            "results": [
                {"document_id": OTHER_ID, "result": "updated"},
                {"document_id": DOCUMENT_ID, "result": "updated"},
            ]
        }
    )

    assert call_with(reply, last_seen_of(DOCUMENT_ID, OTHER_ID)) == IndexerRejected(
        200, MALFORMED_RESPONSE
    )


@pytest.mark.parametrize(
    "results",
    [
        [],
        [ENTRY_OK, {**ENTRY_OK, "external_id": "second.md"}],
        [{**ENTRY_OK, "external_id": "other.md"}],
    ],
    ids=["fewer", "more", "other-external-id"],
)
def test_batch_results_that_do_not_match_the_requested_documents_are_malformed(
    results: list[dict[str, object]],
) -> None:
    reply = Reply(body={"results": results})

    assert call_with(reply, batch_of(EXTERNAL_ID)) == IndexerRejected(200, MALFORMED_RESPONSE)


def test_empty_requests_match_empty_results() -> None:
    assert call_with(Reply(body={"results": []}), last_seen_of()) == LastSeenResults(entries=())


# --- エラーコードの形 ---


@pytest.mark.parametrize("code", ["lock_not_owned", "a", "x1_y2", "a" * 64])
def test_an_error_code_of_the_expected_shape_is_kept(code: str) -> None:
    assert call_with(error_reply(409, code), OPERATIONS["status"]) == IndexerRejected(409, code)


@pytest.mark.parametrize(
    "code",
    ["", "Lock_Not_Owned", "lock-not-owned", "a b", "a" * 65, "SENTINEL\nINJECTED", "日本"],
)
def test_an_error_code_of_an_unexpected_shape_is_dropped(code: str) -> None:
    result = call_with(error_reply(409, code), OPERATIONS["status"])

    assert result == IndexerRejected(409, None)


# --- 成功のステータスなのに、応答が契約と合わない ---


@pytest.mark.parametrize(
    ("operation", "body"),
    [
        ("batch", {}),
        ("batch", {"results": "x"}),
        ("batch", {"results": [{**ENTRY_OK, "change": "other"}]}),
        ("batch", {"results": [{**ENTRY_FAILED, "failure_type": "store_error"}]}),
        ("batch", {"results": [{**ENTRY_OK, "status": "pending"}]}),
        ("batch", {"results": [{**ENTRY_OK, "extract_failed": "false"}]}),
        ("batch", {"results": [{"external_id": "x"}]}),
        ("batch", {"results": ["x"]}),
        ("batch", []),
        ("last_seen", {"results": [{"document_id": DOCUMENT_ID, "result": "ok"}]}),
        ("status", {"crawl_id": "j", "source_id": "s"}),
        ("status", {"crawl_id": "j", "source_id": "s", "status": "deleted", "deleted_count": "1"}),
        ("status", {"crawl_id": "j", "source_id": "s", "status": "deleted", "deleted_count": True}),
        # 契約にない `status` は、終端とみなさず(`confirmed` の根拠にせず)、契約違反の応答にする。
        ("status", {"crawl_id": "j", "source_id": "s", "status": "processing"}),
        ("status", {"crawl_id": "j", "source_id": "s", "status": "Running"}),
        ("status", {"crawl_id": "j", "source_id": "s", "status": ""}),
        ("discard", {"discarded_crawl_ids": [1]}),
        ("delete_documents", {"deleted_count": 1.5}),
        ("delete_records", {"deleted": "true"}),
    ],
)
def test_a_success_status_with_a_body_off_the_contract_is_rejected_as_malformed(
    operation: str, body: Any
) -> None:
    assert call_with(Reply(body=body), OPERATIONS[operation]) == IndexerRejected(
        200, MALFORMED_RESPONSE
    )


@pytest.mark.parametrize(
    "operation", ["batch", "last_seen", "status", "discard", "delete_documents"]
)
def test_a_success_status_with_a_body_that_is_not_json_is_malformed(operation: str) -> None:
    assert call_with(Reply(raw=b"\xff not json"), OPERATIONS[operation]) == IndexerRejected(
        200, MALFORMED_RESPONSE
    )


def test_parse_failures_do_not_echo_the_response_values() -> None:
    reply = Reply(body={"results": [{**ENTRY_OK, "change": "SENTINEL-VALUE"}]})

    result = call_with(reply, OPERATIONS["batch"])

    assert "SENTINEL-VALUE" not in repr(result)


@pytest.mark.parametrize(
    "status",
    ["running", "deleted", "skipped_by_ratio", "validation_failed", "discarded", "failed"],
)
def test_every_status_of_the_contract_is_accepted(status: str) -> None:
    reply = Reply(body={"crawl_id": "j", "source_id": SOURCE_ID, "status": status})

    assert call_with(reply, OPERATIONS["status"]) == CrawlStatus(
        crawl_id="j", source_id=SOURCE_ID, status=status
    )
