"""異常・取り消し・喪失・メンテナンスの最終対応と、終了通知 `failed`・`cancelled`(4.7・4.8)。

観点 #25・#30(取り消しと `send_started_at` の前後)、#31(`failed` 通知の条件)、#33(Store 層の異常)。
終了通知 `failed`・`cancelled` は、開始通知が成功した後で、`enumeration_completed` の初回の送信を
始める前に限って送る。送信を始めた後は、取り消しても削除を止められない。
"""

from collections.abc import Callable
from typing import Any

import pytest

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.connectors.interface import ConnectorError, ErrorCategory
from loreley_crawler.crawl import CrawlFailure, CrawlSettings
from loreley_crawler.crawl.executor import ReadyToFinish
from loreley_crawler.crawl.run import COUNT_CHECK_FAILED_DETAIL
from loreley_crawler.crawl.tally import RegistrationTally
from loreley_crawler.infrastructure.indexer_client import (
    BatchResults,
    CrawlStatus,
    DocumentFailed,
    FailureType,
    IndexerRejected,
    IndexerUnavailable,
)
from loreley_crawler.jobs import JobStatus
from tests.crawl.support import CrawlEnv, crawl_env, outcomes, run_full
from tests.fakes import in_memory_repository as ops
from tests.fakes.fake_connector import FETCH, NEXT
from tests.fakes.fake_indexer_client import (
    FINISH_CRAWL,
    GET_CRAWL_STATUS,
    REGISTER_DOCUMENTS,
    REPORT_LAST_SEEN,
    START_CRAWL,
)
from tests.jobs.support import JOB_ID, SOURCE_ID


def running() -> CrawlStatus:
    return CrawlStatus(JOB_ID, SOURCE_ID, "running", finish_received_at="2026-11-13T00:00:00.000Z")


def request_cancel(env: CrawlEnv) -> None:
    env.jobs.cancel_requests.request(env.context.job_id)


# --- 終了通知 failed(観点 #31) ---


@pytest.mark.parametrize(
    ("arrange", "reason"),
    [
        (
            lambda env: env.indexer.behavior.inject(REPORT_LAST_SEEN, IndexerRejected(400, "x")),
            "indexer_rejected",
        ),
        (
            lambda env: env.indexer.behavior.inject(
                REPORT_LAST_SEEN, IndexerUnavailable("http_503"), times=None
            ),
            "indexer_unavailable",
        ),
        (
            lambda env: env.indexer.registration_failures.update(a=FailureType.WRITE_CONFLICT),
            "conflict_unresolved",
        ),
        (
            lambda env: env.connector.behavior.inject(
                NEXT, ConnectorError.of(ErrorCategory.ENUMERATION_INCOMPLETE, "失敗"), times=None
            ),
            "enumeration_failed",
        ),
    ],
)
def test_a_failure_after_the_start_notice_sends_a_failed_finish_notice_with_the_minimal_content(
    arrange: Any, reason: str
) -> None:
    with crawl_env(files={"a": b"1"}) as env:
        arrange(env)

        body = run_full(env)

        assert body["status"] == "failed"
        assert body["failure_reason"] == reason
        assert outcomes(env) == ["failed"]
        sent = env.indexer.calls_of(FINISH_CRAWL)[0].arguments
        assert (sent["enumerated_count"], sent["skipped_document_ids"]) == (None, None)
        assert sent["oversize_document_ids"] is None
        assert body["finish_notice"] == {
            "content": {
                "source_id": SOURCE_ID,
                "outcome": "failed",
                "finished_at": body["finish_notice"]["content"]["finished_at"],
            },
            "send_started_at": None,  # `failed` の通知は、送信の開始を記録しない
        }
        assert env.indexer.calls_of(GET_CRAWL_STATUS) == []  # 確認に入らない
        assert "confirmation" not in body


def test_a_document_id_mismatch_sends_a_failed_notice() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(
            REGISTER_DOCUMENTS,
            BatchResults((DocumentFailed("a", "f" * 64, FailureType.DOCUMENT_REJECTED),)),
        )

        body = run_full(env)

        assert body["failure_reason"] == "document_id_mismatch"
        assert outcomes(env) == ["failed"]


@pytest.mark.parametrize("arrange", ["config", "start_rejected", "start_unavailable"])
def test_no_failed_notice_before_the_start_notice_succeeded(arrange: str) -> None:
    with crawl_env(files={"a": b"1"}, seed_source=arrange != "config") as env:
        if arrange == "start_rejected":
            env.indexer.behavior.inject(START_CRAWL, IndexerRejected(409, "crawl_start_conflict"))
        if arrange == "start_unavailable":
            env.indexer.behavior.inject(START_CRAWL, IndexerUnavailable("timeout"), times=None)

        body = run_full(env)

        assert body["status"] == "failed"
        assert env.indexer.calls_of(FINISH_CRAWL) == []
        assert "finish_notice" not in body


def test_a_failed_notice_that_cannot_be_delivered_is_given_up_and_the_reason_stays() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(REPORT_LAST_SEEN, IndexerRejected(400, "x"))
        env.indexer.behavior.inject(FINISH_CRAWL, IndexerUnavailable("http_503"), times=None)

        body = run_full(env)

        assert body["failure_reason"] == "indexer_rejected"  # `finish_notice_failed` にならない
        assert len(env.indexer.calls_of(FINISH_CRAWL)) == 3


def test_a_failure_after_the_finish_send_started_sends_no_failed_notice() -> None:  # 観点 #31
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(GET_CRAWL_STATUS, RuntimeError("boom"))

        body = run_full(env)

        assert body["failure_reason"] == "internal_error"
        assert outcomes(env) == ["enumeration_completed"]
        assert body["finish_notice"]["send_started_at"] is not None


def test_losing_the_lease_while_polling_fails_with_lock_lost_and_sends_no_failed_notice() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(GET_CRAWL_STATUS, running())
        env.indexer.behavior.before(
            GET_CRAWL_STATUS, lambda: env.heartbeat.record_loss("lock_taken_over")
        )

        body = run_full(env)

        assert body["failure_reason"] == "lock_lost"
        assert outcomes(env) == ["enumeration_completed"]  # 元の理由を上書きしない
        assert body["registration"]["partial"] is False
        assert "confirmation" not in body  # 確認を終えられなかったジョブには書かない


# --- 所有権の喪失・メンテナンス・Store 層の異常・想定外の例外 ---


def test_a_document_level_lock_not_owned_fails_with_lock_lost_and_a_failed_notice() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.registration_failures["a"] = FailureType.LOCK_NOT_OWNED

        body = run_full(env)

        assert body["failure_reason"] == "lock_lost"
        assert "lock_not_owned" in body["failure_detail"]
        assert env.heartbeat.lost_reason == "lock_not_owned"
        # 終了通知は所有確認の対象外。`enumeration_completed` は送らず、`failed` を可能なら送る。
        assert outcomes(env) == ["failed"]


def test_a_lost_lease_between_requests_fails_with_lock_lost() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.before(
            REPORT_LAST_SEEN, lambda: env.heartbeat.record_loss("lock_missing")
        )

        body = run_full(env)

        assert body["failure_reason"] == "lock_lost"
        assert "lock_missing" in body["failure_detail"]
        assert env.indexer.calls_of(REGISTER_DOCUMENTS) == []


def test_the_maintenance_flag_mid_crawl_fails_with_maintenance_and_a_failed_notice() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.before(REPORT_LAST_SEEN, lambda: env.jobs.seed_maintenance(True))

        body = run_full(env)

        assert body["failure_reason"] == "maintenance"
        assert outcomes(env) == ["failed"]
        assert env.indexer.calls_of(REGISTER_DOCUMENTS) == []  # 書き込みの要請は止まる


def test_an_exhausted_store_outage_fails_with_store_unavailable_when_it_can_be_recorded() -> None:
    with crawl_env(
        files={"a": b"1", "b": b"2"}, settings=CrawlSettings(batch_max_documents=1)
    ) as env:
        # 1 つ目のバッチの後のジョブ記録の更新が、リトライを尽くして失敗する(3 回)。
        # 最終状態の記録は、その後に成功する。
        env.indexer.behavior.before(
            REGISTER_DOCUMENTS,
            lambda: env.jobs.jobs_repository.behavior.inject(
                ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=3
            ),
        )

        body = run_full(env)

        assert body["status"] == "failed"
        assert body["failure_reason"] == "store_unavailable"
        assert "timeout" in body["failure_detail"]
        assert outcomes(env) == ["failed"]  # 観点 #33


def test_a_bulk_delete_that_never_succeeds_fails_with_store_unavailable() -> None:
    with crawl_env(files={"a": b"ok"}) as env:
        record_id = env.seed_document_record("skip", "a")
        env.jobs.jobs_repository.fail_bulk_delete_of([record_id], times=None)

        body = run_full(env)

        assert body["failure_reason"] == "store_unavailable"
        assert body["registration"]["partial"] is False  # 確定は整理の前
        assert outcomes(env) == ["failed"]
        assert record_id in env.jobs.jobs_repository.record_ids()


def test_an_unexpected_store_response_fails_with_internal_error() -> None:
    with crawl_env(files={"a": b"ok"}) as env:
        env.jobs.jobs_repository.behavior.inject(
            ops.SCAN, StoreUnexpectedResponseError("http_400"), times=None
        )

        body = run_full(env)

        assert body["failure_reason"] == "internal_error"
        assert "http_400" in body["failure_detail"]
        assert outcomes(env) == ["failed"]


def test_an_unexpected_exception_fails_with_internal_error_and_names_only_its_type() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(REGISTER_DOCUMENTS, RuntimeError("secret /path/to/body"))

        body = run_full(env)

        assert body["failure_reason"] == "internal_error"
        assert body["failure_detail"] == "想定外の例外: RuntimeError"
        assert outcomes(env) == ["failed"]


# --- JobContext.finish の False は再判定しない ---


def test_a_job_finished_by_another_writer_is_left_alone_when_the_final_state_is_recorded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with crawl_env(files={"a": b"1"}) as env:
        # ポーリング中に、管理者のロック解放が `failed`(`lock_released`)にした。
        env.indexer.behavior.before(
            GET_CRAWL_STATUS,
            lambda: env.jobs.seed_job(
                JOB_ID,
                status=JobStatus.FAILED,
                failure_reason="lock_released",
                registration={"partial": False},
            ),
        )

        body = run_full(env)  # 例外なし

        assert body["status"] == "failed"
        assert body["failure_reason"] == "lock_released"
        assert env.context.is_terminal
        # 最終状態を記録できなかった(すでに終端)ことを、「記録した」とは書かない。
        assert "already finished: job_id" in caplog.text
        assert "crawl ended: job_id" not in caplog.text


def test_a_job_finished_by_another_writer_gets_no_failed_notice_and_no_overwrite() -> None:
    with crawl_env(files={"a": b"1", "b": b"2"}, settings=CrawlSettings(chunk_size=1)) as env:
        env.indexer.behavior.before(
            REPORT_LAST_SEEN,
            lambda: env.jobs.seed_job(
                JOB_ID, status=JobStatus.FAILED, failure_reason="lock_released"
            ),
        )

        body = run_full(env)

        assert body["failure_reason"] == "lock_released"  # 上書きしない
        assert env.indexer.calls_of(FINISH_CRAWL) == []  # 送らない(4.8: `lock_released` は送らない)


# --- 取り消し(観点 #14・#25・#30) ---


def test_a_cancel_during_the_chunks_sends_a_cancelled_notice_and_keeps_partial_true() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.before(REPORT_LAST_SEEN, lambda: request_cancel(env))

        body = run_full(env)

        assert body["status"] == "cancelled"
        assert "failure_reason" not in body
        assert outcomes(env) == ["cancelled"]
        assert body["registration"]["partial"] is True
        assert env.indexer.calls_of(GET_CRAWL_STATUS) == []
        assert env.connector.close_count == 1
        assert [stream.closed for stream in env.connector.streams] == [True]
        assert body["finish_notice"]["content"]["outcome"] == "cancelled"
        assert env.jobs.cancel_requests.is_requested(JOB_ID) is False  # 終端後に要求を消す


def test_a_cancel_after_the_content_is_fixed_but_before_the_send_replaces_the_notice() -> None:
    # 観点 #30。内容を固定した後・`send_started_at` の記録の前に取り消される。固定した
    # `enumeration_completed` はまだ届いていないので送らず、`cancelled` を新たに固定して送る。
    with crawl_env(files={"a": b"1"}) as env:
        registry = env.jobs.cancel_requests
        requested_by_the_user = registry.is_requested

        def is_requested(job_id: str) -> bool:
            # 内容の固定(`finish_notice` の保存)の後、送信の開始の記録の前だけ、要求が届いている。
            notice = env.job_body().get("finish_notice")
            is_fixed_and_unsent = notice is not None and notice["send_started_at"] is None
            return requested_by_the_user(job_id) or is_fixed_and_unsent

        registry.is_requested = is_requested  # type: ignore[method-assign]

        body = run_full(env)

        assert body["status"] == "cancelled"
        assert outcomes(env) == ["cancelled"]  # `enumeration_completed` は送らない
        assert body["finish_notice"]["content"]["outcome"] == "cancelled"
        assert "enumerated_count" not in body["finish_notice"]["content"]
        assert body["finish_notice"]["send_started_at"] is None
        assert body["registration"]["partial"] is False  # 確定後の取り消しは、`false` のまま
        assert env.indexer.calls_of(GET_CRAWL_STATUS) == []


def test_a_cancel_while_the_finish_notice_is_being_retried_stops_the_retries() -> None:  # 観点 #30
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.before(FINISH_CRAWL, lambda: request_cancel(env))
        env.indexer.behavior.inject(FINISH_CRAWL, IndexerUnavailable("timeout"), times=None)

        body = run_full(env)

        assert body["status"] == "cancelled"
        assert outcomes(env) == ["enumeration_completed"]  # リトライをやめ、`cancelled` は送らない
        assert body["finish_notice"]["send_started_at"] is not None
        assert "confirmation" not in body  # 届いたかどうかは不明のまま
        assert body["registration"]["partial"] is False


def test_a_cancel_after_the_notice_stops_the_polling_as_unconfirmed() -> None:  # 観点 #14・#25
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(GET_CRAWL_STATUS, running())
        env.indexer.behavior.before(GET_CRAWL_STATUS, lambda: request_cancel(env))

        body = run_full(env)

        assert body["status"] == "cancelled"
        assert outcomes(env) == [
            "enumeration_completed"
        ]  # 削除は止まらない。`cancelled` は送らない
        assert body["confirmation"] == "unconfirmed"
        assert body["deletion_summary"]["status"] == "running"
        assert body["warnings"] == [{"code": "polling_aborted", "confirmation": "unconfirmed"}]
        assert body["registration"]["partial"] is False
        assert len(env.indexer.calls_of(GET_CRAWL_STATUS)) == 1


def test_a_cancel_before_the_start_notice_sends_nothing() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        request_cancel(env)

        body = run_full(env)

        assert body["status"] == "cancelled"
        assert env.indexer.calls == []
        assert body["registration"]["partial"] is True
        assert "finish_notice" not in body


def test_a_cancel_request_is_cleared_when_the_job_ends() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        request_cancel(env)

        run_full(env)

        assert env.jobs.cancel_requests.is_requested(JOB_ID) is False


def test_when_the_final_state_cannot_be_recorded_the_error_propagates_to_the_job_runner() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.before(
            REGISTER_DOCUMENTS,
            lambda: env.jobs.jobs_repository.behavior.inject(
                ops.REPLACE, StoreUnavailableError("timeout"), key=JOB_ID, times=None
            ),
        )

        with pytest.raises(StoreUnavailableError):
            env.executor(env.record, env.context)

        # 記録できなかったので、ジョブは `running` のまま(Job Runner がロックを残し、回復に委ねる)。
        assert env.job_body()["status"] == "running"
        assert env.connector.close_count == 1


def test_the_finish_notice_is_retried_even_after_the_lease_was_lost() -> None:
    # 終了通知は所有確認の対象外(architecture 5.7)。リトライの確認点は、取り消しだけ。
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.before(
            FINISH_CRAWL, lambda: env.heartbeat.record_loss("lock_taken_over")
        )
        env.indexer.behavior.inject(FINISH_CRAWL, IndexerUnavailable("timeout"), times=1)

        body = run_full(env)

        assert outcomes(env) == ["enumeration_completed"] * 2
        assert body["failure_reason"] == "lock_lost"  # ポーリングの待ちで、喪失を知る
        assert "confirmation" not in body


def test_a_job_finished_by_another_writer_is_logged_and_left_alone(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with crawl_env(files={"a": b"1", "b": b"2"}, settings=CrawlSettings(chunk_size=1)) as env:
        env.indexer.behavior.before(
            REPORT_LAST_SEEN,
            lambda: env.jobs.seed_job(
                JOB_ID, status=JobStatus.FAILED, failure_reason="lock_released"
            ),
        )

        run_full(env)

        assert "already finished by another writer" in caplog.text


# --- 終了通知(`enumeration_completed`)の送信直前の確認(削除のきっかけになる通知) ---


def after_the_content_is_fixed(env: CrawlEnv, action: Callable[[], None]) -> None:
    """内容を固定(`finish_notice` の保存。`send_started_at` は null)した直後に 1 度だけ行う。"""
    original = env.context.update
    is_done = False

    def update(changes: Any) -> Any:
        nonlocal is_done
        result = original(changes)
        notice = changes.get("finish_notice")
        if notice is not None and notice["send_started_at"] is None and not is_done:
            is_done = True
            action()
        return result

    env.context.update = update  # type: ignore[method-assign]


@pytest.mark.parametrize(
    ("trigger", "reason"),
    [
        (lambda env: env.heartbeat.record_loss("lock_missing"), "lock_lost"),
        (lambda env: env.jobs.seed_maintenance(True), "maintenance"),
    ],
    ids=["lease_lost", "maintenance"],
)
def test_enumeration_completed_is_not_sent_when_the_job_is_stopped_after_the_content_is_fixed(
    trigger: Any, reason: str
) -> None:
    with crawl_env(files={"a": b"1"}) as env:
        after_the_content_is_fixed(env, lambda: trigger(env))

        body = run_full(env)

        assert body["failure_reason"] == reason
        assert outcomes(env) == ["failed"]  # `enumeration_completed` は送らない
        assert body["finish_notice"]["content"]["outcome"] == "failed"
        assert env.indexer.calls_of(GET_CRAWL_STATUS) == []


def test_enumeration_completed_is_not_sent_when_a_cancel_arrives_after_the_content_is_fixed() -> (
    None
):
    with crawl_env(files={"a": b"1"}) as env:
        after_the_content_is_fixed(env, lambda: request_cancel(env))

        body = run_full(env)

        assert body["status"] == "cancelled"
        assert outcomes(env) == ["cancelled"]


def test_a_cancel_right_after_send_started_at_is_recorded_counts_as_after_the_send_started() -> (
    None
):
    # 設計書 4.7: 記録の直後・初回の送信の前の取り消しは「送信開始後」。`cancelled` は送らない。
    with crawl_env(files={"a": b"1"}) as env:
        registry = env.jobs.cancel_requests
        requested_by_the_user = registry.is_requested

        def is_requested(job_id: str) -> bool:
            notice = env.job_body().get("finish_notice")
            is_recorded = notice is not None and notice["send_started_at"] is not None
            return requested_by_the_user(job_id) or is_recorded

        registry.is_requested = is_requested  # type: ignore[method-assign]

        body = run_full(env)

        assert body["status"] == "cancelled"
        assert outcomes(env) == []  # 何も送らない(届いていないので、削除も起きない)
        assert body["finish_notice"]["send_started_at"] is not None
        assert "confirmation" not in body
        assert body["registration"]["partial"] is False


def test_the_maintenance_flag_does_not_stop_the_polling_or_the_notice_retry() -> None:
    # 送信を始めた後は、メンテナンスで止めない(削除は Indexer 側で進みうる。仕様どおり)。
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.before(FINISH_CRAWL, lambda: env.jobs.seed_maintenance(True))
        env.indexer.behavior.inject(FINISH_CRAWL, IndexerUnavailable("timeout"), times=1)
        env.indexer.behavior.inject(GET_CRAWL_STATUS, running())

        body = run_full(env)

        assert body["status"] == "succeeded"
        assert outcomes(env) == ["enumeration_completed"] * 2
        assert body["confirmation"] == "confirmed"


def break_the_tally_by_losing_the_registrations(monkeypatch: pytest.MonkeyPatch) -> None:
    """登録の結果を数えない(合計が列挙数より少なくなる)。"""
    monkeypatch.setattr(RegistrationTally, "record_registered", lambda self, result: False)


def break_the_tally_by_double_counting(monkeypatch: pytest.MonkeyPatch) -> None:
    """登録された文書をスキップにも載せる(合計が列挙数より多くなる)。"""
    original = RegistrationTally.record_registered

    def record_registered(self: RegistrationTally, result: Any) -> bool:
        self.record_skipped(result.document_id)
        return original(self, result)

    monkeypatch.setattr(RegistrationTally, "record_registered", record_registered)


@pytest.mark.parametrize(
    "break_the_tally",
    [break_the_tally_by_losing_the_registrations, break_the_tally_by_double_counting],
    ids=["fewer_than_enumerated", "more_than_enumerated"],
)
def test_the_counts_that_do_not_add_up_stop_the_purge_and_the_notice_and_fail_the_job(
    break_the_tally: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 列挙した文書は、登録されたか、スキップか原本サイズ超過のどれかでなければならない。
    # 集計を壊して合わなくする(少ない向きも多い向きも)。壊れた集計をもとに、記録の整理も、
    # 削除のきっかけになる通知も行わず、`failed(internal_error)`(`failed` の通知は送る)。
    break_the_tally(monkeypatch)
    with crawl_env(files={"a": b"1", "b": b"2"}) as env:
        stale_skip = env.seed_document_record("skip", "a")
        stale_oversize = env.seed_document_record("oversize", "vanished")

        body = run_full(env)

        assert body["failure_reason"] == "internal_error"
        assert body["failure_detail"] == COUNT_CHECK_FAILED_DETAIL
        assert outcomes(env) == ["failed"]
        assert body["finish_notice"]["content"]["outcome"] == "failed"
        assert env.indexer.calls_of(GET_CRAWL_STATUS) == []
        # 整理は行われない(古いスキップ記録・消えた文書のサイズ超過記録が残る)。
        assert {stale_skip, stale_oversize} <= set(env.jobs.jobs_repository.record_ids())
        assert env.jobs.jobs_repository.behavior.calls_of(ops.SCAN, ops.DELETE_IDS) == []


# --- 取り消し・最終状態の境界 ---


def test_a_cancel_during_the_purge_cancels_the_job_and_leaves_the_records() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        stale = env.seed_document_record("skip", "vanished")
        env.jobs.jobs_repository.behavior.before(ops.SCAN, lambda: request_cancel(env))

        body = run_full(env)

        assert body["status"] == "cancelled"
        assert body["registration"]["partial"] is False  # 確定は整理の前
        assert outcomes(env) == ["cancelled"]
        assert stale in env.jobs.jobs_repository.record_ids()  # 取り消されたクロールは整理しない
        assert env.indexer.calls_of(GET_CRAWL_STATUS) == []


def test_a_failed_notice_replaces_the_fixed_notice_when_the_send_start_cannot_be_recorded() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        original = env.context.update

        def update(changes: Any) -> Any:
            notice = changes.get("finish_notice")
            if notice is not None and notice["send_started_at"] is not None:
                raise StoreUnavailableError("timeout")  # `send_started_at` の保存だけが失敗する
            return original(changes)

        env.context.update = update  # type: ignore[method-assign]

        body = run_full(env)

        assert body["failure_reason"] == "store_unavailable"
        # 固定済み・未送信の `enumeration_completed` を、`failed` で置き換えて送る。
        assert outcomes(env) == ["failed"]
        assert body["finish_notice"]["content"]["outcome"] == "failed"
        assert body["finish_notice"]["send_started_at"] is None


def test_a_base_exception_propagates_without_writing_a_final_state() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.connector.behavior.inject(FETCH, KeyboardInterrupt())

        with pytest.raises(KeyboardInterrupt):
            env.executor(env.record, env.context)

        assert env.job_body()["status"] == "running"
        assert env.connector.close_count == 1
        assert env.indexer.calls_of(FINISH_CRAWL) == []


@pytest.mark.parametrize(
    "arrange",
    [
        lambda env: env.indexer.behavior.inject(REGISTER_DOCUMENTS, RuntimeError("boom")),
        lambda env: env.indexer.behavior.before(REPORT_LAST_SEEN, lambda: request_cancel(env)),
        lambda env: env.indexer.behavior.inject(FINISH_CRAWL, IndexerRejected(409, "x")),
        lambda env: env.jobs.jobs_repository.behavior.inject(
            ops.SCAN, StoreUnexpectedResponseError("http_400"), times=None
        ),
        lambda env: None,
    ],
    ids=["unexpected_error", "cancelled", "finish_rejected", "store_error", "succeeded"],
)
def test_the_resources_are_closed_whatever_the_ending(arrange: Any) -> None:
    with crawl_env(files={"a": b"1"}) as env:
        arrange(env)

        run_full(env)

        assert env.connector.close_count == 1
        assert [stream.closed for stream in env.connector.streams] == [True]


def test_the_notice_itself_also_refuses_to_go_out_with_counts_that_do_not_add_up() -> None:
    # 二重防御: 整理の前の確認を通った後でも、送信の前にもう一度確かめる。
    with crawl_env(files={"a": b"1"}) as env:
        result = env.run()
        assert isinstance(result, ReadyToFinish)
        result.run.tally.record_skipped("f" * 64)  # 集計を壊す(列挙数より多くなる)

        with pytest.raises(CrawlFailure):
            result.run.send_finish_notice()

        assert env.indexer.calls_of(FINISH_CRAWL) == []
