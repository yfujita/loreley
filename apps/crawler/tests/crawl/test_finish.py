"""終了通知(`enumeration_completed`)と最終状態(architecture 7.5・4.2。観点 #2・#5・#6・#7・#8)。

終了通知は、すべての応答を確認した後に、内容を `finish_notice` に保存して固定してから送る。
202 は受理の確認ではない(受理はポーリングで確認する)。
"""

from typing import Any

import pytest

from loreley_crawler.common.timestamps import format_instant
from loreley_crawler.connectors.interface import Completed, DocumentRef
from loreley_crawler.crawl import CrawlSettings
from loreley_crawler.documents import DocumentsSettings
from loreley_crawler.infrastructure.indexer_client import (
    BatchResults,
    Change,
    CrawlStatus,
    DocumentRegistered,
    FailureType,
    IndexerRejected,
    IndexerUnavailable,
)
from tests.crawl.support import crawl_env, document_id_of, finish_calls, run_full
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import DEFAULT_NOW
from tests.fakes.fake_connector import fetched_document
from tests.fakes.fake_indexer_client import (
    FINISH_CRAWL,
    GET_CRAWL_STATUS,
    REGISTER_DOCUMENTS,
    REPORT_LAST_SEEN,
)
from tests.jobs.support import JOB_ID, SOURCE_ID


def test_a_clean_crawl_ends_succeeded_with_the_notice_confirmed() -> None:
    with crawl_env(files={"a": b"1", "b": b"2"}) as env:
        body = run_full(env)

        assert body["status"] == "succeeded"
        assert body["finished_at"] == format_instant(DEFAULT_NOW)
        assert body["confirmation"] == "confirmed"
        assert body["deletion_summary"]["status"] == "deleted"
        assert body["registration"]["partial"] is False
        assert "warnings" not in body
        assert "failure_reason" not in body


def test_the_finish_notice_follows_every_last_seen_and_batch_and_precedes_the_polling() -> None:
    with crawl_env(
        files={n: b"x" for n in "abcde"},
        settings=CrawlSettings(chunk_size=2, batch_max_documents=2),
    ) as env:
        run_full(env)  # 観点 #2

        events = env.events
        assert events[0] == "start"
        finish = events.index("finish:enumeration_completed")
        assert all(e.startswith(("last_seen", "fetch", "register")) for e in events[1:finish])
        assert events.count("last_seen:2") + events.count("last_seen:1") == 3
        assert events[finish + 1 :] == ["status"]


def test_the_notice_carries_the_counts_and_the_ids_for_the_count_check() -> None:  # 観点 #7・#8
    refs = [DocumentRef(n, n) for n in ["ok", "gone", "big", "rejected", "ok", "/bad"]]
    documents = {
        "ok": fetched_document(b"ok"),
        "big": fetched_document(b"x" * 100),
        "rejected": fetched_document(b"r"),
    }
    with crawl_env(
        items=[*refs, Completed()],
        documents=documents,
        documents_settings=DocumentsSettings(max_raw_bytes=10),
    ) as env:
        env.indexer.registration_failures["rejected"] = FailureType.DOCUMENT_REJECTED

        body = run_full(env)

        (sent,) = finish_calls(env)
        assert sent["outcome"].value == "enumeration_completed"
        assert sent["source_id"] == SOURCE_ID
        assert sent["crawl_id"] == JOB_ID
        # 重複と識別子エラーを除き、スキップ・サイズ超過を含む。
        assert sent["enumerated_count"] == 4
        assert sent["skipped_document_ids"] == [document_id_of("gone"), document_id_of("rejected")]
        assert sent["oversize_document_ids"] == [document_id_of("big")]
        assert body["registration"]["enumerated_count"] == 4


def test_the_content_is_saved_before_the_first_send_and_the_resend_is_identical() -> (
    None
):  # 観点 #5
    with crawl_env(files={"a": b"1"}, advance_clock_on_sleep=True) as env:
        saved: list[dict[str, Any]] = []
        env.indexer.behavior.before(
            FINISH_CRAWL, lambda: saved.append(env.job_body()["finish_notice"])
        )
        # 応答が失われ、待った後で再送する。時計は進むが、`finished_at` は変わらない。
        env.indexer.behavior.inject(FINISH_CRAWL, IndexerUnavailable("timeout"), times=1)

        body = run_full(env)

        first, second = finish_calls(env)
        assert first == second
        (at_first_send,) = saved
        assert at_first_send["content"] == body["finish_notice"]["content"]
        assert at_first_send["send_started_at"] is not None  # 送信の開始は、送る前に記録済み
        content = body["finish_notice"]["content"]
        assert content["finished_at"] == format_instant(first["finished_at"])
        assert content["enumerated_count"] == 1
        assert env.sleeps[0] == 1.0
        assert format_instant(first["finished_at"]) == format_instant(DEFAULT_NOW)


def test_the_saved_content_matches_what_was_sent() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        body = run_full(env)

        (sent,) = finish_calls(env)
        assert body["finish_notice"]["content"] == {
            "source_id": SOURCE_ID,
            "outcome": "enumeration_completed",
            "finished_at": format_instant(sent["finished_at"]),
            "enumerated_count": 1,
            "skipped_document_ids": [],
            "oversize_document_ids": [],
        }


def test_a_202_alone_is_not_taken_as_the_notice_being_accepted() -> None:  # 観点 #6
    with crawl_env(files={"a": b"1"}) as env:
        # 202 の後の最初の応答が `running` で、`finish_received_at` がない(受理の根拠なし)。
        env.indexer.behavior.inject(GET_CRAWL_STATUS, CrawlStatus(JOB_ID, SOURCE_ID, "running"))

        body = run_full(env)

        assert env.indexer.calls_of(GET_CRAWL_STATUS)[1:] != []  # ポーリングを続けた
        assert body["warnings"] == [{"code": "finish_not_acknowledged"}]
        assert body["confirmation"] == "confirmed"
        assert body["status"] == "succeeded"  # 警告は status を変えない


def test_a_terminal_status_without_evidence_of_receipt_leaves_a_warning() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(
            GET_CRAWL_STATUS, CrawlStatus(JOB_ID, SOURCE_ID, "discarded", reason="source_deleted")
        )

        body = run_full(env)

        assert body["warnings"] == [{"code": "finish_not_acknowledged"}]
        assert body["deletion_summary"]["status"] == "discarded"
        assert body["status"] == "succeeded"


def test_a_failed_status_with_an_outcome_reason_counts_as_receipt() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(
            GET_CRAWL_STATUS, CrawlStatus(JOB_ID, SOURCE_ID, "failed", reason="outcome_failed")
        )

        assert "warnings" not in run_full(env)


# --- 最終状態 ---


def test_a_skipped_document_makes_the_job_partially_succeeded() -> None:
    with crawl_env(files={"a": b"1", "b": b"2"}) as env:
        env.indexer.registration_failures["b"] = FailureType.DOCUMENT_REJECTED

        assert run_full(env)["status"] == "partially_succeeded"


def test_an_invalid_id_alone_makes_the_job_partially_succeeded() -> None:  # 観点 #38
    with crawl_env(
        items=[DocumentRef("a", "a"), DocumentRef("/bad", "bad"), Completed()],
        documents={"a": fetched_document(b"1")},
    ) as env:
        body = run_full(env)

        assert body["status"] == "partially_succeeded"
        assert body["registration"]["skipped_count"] == 0
        assert finish_calls(env)[0]["enumerated_count"] == 1  # 識別子エラーは数えない


def test_oversize_and_extract_failure_do_not_change_the_status() -> None:  # 観点 #22
    with crawl_env(
        files={"big": b"x" * 100, "ok": b"1"},
        documents_settings=DocumentsSettings(max_raw_bytes=10),
    ) as env:
        env.indexer.behavior.inject(
            REGISTER_DOCUMENTS,
            BatchResults((DocumentRegistered("ok", document_id_of("ok"), Change.CREATED, True),)),
        )

        body = run_full(env)

        assert body["status"] == "succeeded"
        assert body["registration"]["oversize_count"] == 1
        assert body["registration"]["error_count"] == 1


@pytest.mark.parametrize("status", ["skipped_by_ratio", "validation_failed", "failed", "discarded"])
def test_a_deletion_that_did_not_happen_does_not_fail_the_job(status: str) -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(
            GET_CRAWL_STATUS,
            CrawlStatus(
                JOB_ID,
                SOURCE_ID,
                status,
                reason="some_reason",
                forced=False,
                target_count=3,
                finish_received_at="2026-11-13T00:00:00.000Z",
            ),
        )

        body = run_full(env)

        assert body["status"] == "succeeded"
        assert body["confirmation"] == "confirmed"
        assert body["deletion_summary"] == {
            "status": status,
            "reason": "some_reason",
            "forced": False,
            "target_count": 3,
            "finish_received_at": "2026-11-13T00:00:00.000Z",
        }


# --- 終了通知の失敗 ---


def test_an_unavailable_indexer_on_the_notice_fails_the_job_after_three_attempts() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(FINISH_CRAWL, IndexerUnavailable("http_503"), times=None)

        body = run_full(env)

        assert body["failure_reason"] == "finish_notice_failed"
        assert len(finish_calls(env)) == 3
        assert env.sleeps == [1.0, 2.0]
        # 送信を始めた後なので、`failed` の通知は送らない。ポーリングにも入らない。
        assert {call["outcome"].value for call in finish_calls(env)} == {"enumeration_completed"}
        assert env.indexer.calls_of(GET_CRAWL_STATUS) == []
        assert "confirmation" not in body
        assert body["registration"]["partial"] is False


@pytest.mark.parametrize("error_code", ["finish_content_mismatch", "finish_source_mismatch"])
def test_a_conflicting_notice_is_not_retried_and_fails_the_job(error_code: str) -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(FINISH_CRAWL, IndexerRejected(409, error_code), times=None)

        body = run_full(env)

        assert body["failure_reason"] == "finish_notice_failed"
        assert len(finish_calls(env)) == 1


@pytest.mark.parametrize(
    ("status_code", "error_code"), [(400, "invalid_request"), (404, "not_found")]
)
def test_other_rejections_of_the_notice_are_indexer_rejected(
    status_code: int, error_code: str
) -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(FINISH_CRAWL, IndexerRejected(status_code, error_code))

        body = run_full(env)

        assert body["failure_reason"] == "indexer_rejected"
        assert len(finish_calls(env)) == 1


def test_the_notice_is_not_sent_when_the_maintenance_flag_is_raised_just_before() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        # 整理の走査の直前にフラグが立つ。削除の判断のきっかけになる通知は、送らない。
        env.jobs.jobs_repository.behavior.before(ops.SCAN, lambda: env.jobs.seed_maintenance(True))

        body = run_full(env)

        assert body["failure_reason"] == "maintenance"
        assert [call["outcome"].value for call in finish_calls(env)] == ["failed"]
        assert env.indexer.calls_of(GET_CRAWL_STATUS) == []


def test_the_notice_is_not_sent_when_the_lease_was_lost_just_before() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.jobs.jobs_repository.behavior.before(
            ops.SCAN, lambda: env.heartbeat.record_loss("lock_missing")
        )

        body = run_full(env)

        assert body["failure_reason"] == "lock_lost"
        assert [call["outcome"].value for call in finish_calls(env)] == ["failed"]


def test_no_request_is_left_for_the_last_seen_after_the_notice() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        run_full(env)

        operations = env.indexer.operations()
        assert operations.index(FINISH_CRAWL) > max(
            i for i, op in enumerate(operations) if op in (REPORT_LAST_SEEN, REGISTER_DOCUMENTS)
        )
