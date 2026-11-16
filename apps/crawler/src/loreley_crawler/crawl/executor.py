"""クロールジョブの実行対象 `CrawlExecutor`(Job Runner が呼ぶ。module 4.5)。

`__call__`(`JobExecutor`)は、実行開始から最終状態の記録までを行う(architecture 4.5 の手順 6〜13)。

正常: 開始通知 -> チャンク処理 -> 登録結果の確定・整理 -> 終了通知(`enumeration_completed`)->
削除結果のポーリング -> 最終状態(`succeeded`。スキップ・識別子エラーがあれば
`partially_succeeded`)。

異常(最終状態は、終端にできたら Job Runner の最後の手段が上書きしない。4.8):
- `CrawlFailure`: その理由コードの `failed`
- 取り消し(`CancellationRequested`): `cancelled`(4.7)。終了通知 `cancelled` は、
  `enumeration_completed` の初回の送信を始める前に限り送る。送信後はポーリングを打ち切る
  (ポーリング中なら確認結果の区分 `unconfirmed`)
- 所有権の喪失(`OwnershipLost`): `failed`(`lock_lost`)。`lock_not_owned` は喪失として記録済み
- メンテナンス(`MaintenanceDetected`): `failed`(`maintenance`)
- Store 層の異常: `StoreUnavailableError`(`StoreWriteFailedError` を含む)は `failed`
  (`store_unavailable`)、`StoreUnexpectedResponseError` は `failed`(`internal_error`)
- 想定外の例外: `failed`(`internal_error`)
- 終了通知 `failed` は、開始通知が成功した後で、`enumeration_completed` の初回の送信を始める
  前に限り、最終状態の前に可能なら送る(届かなくてよい。ロックを失っていても送る。終了通知は
  所有確認の対象外。5.7)。送信を始めた後は送らない(元の理由を `finish_notice_failed` に
  上書きさせないため)
- すでにジョブが終端になっていた(他者が `failed`(`lock_released`)にした)ときは、何も書かず、
  終了通知も送らない
- `JobNotStartable`(取り消しに負けた)は、Job Runner が扱うので伝播する

最終状態を記録できなかった(Store 層の異常が続くなど)ときの例外は、そのまま伝播する。Job Runner の
最後の手段が `failed` を試み、それも記録できなければ、ロックを残して回復に委ねる。

`run_until_finish_notice` は、実行開始から終了通知の手前まで(P6a の範囲)だけを実行する
テスト用の入口で、`CrawlFailure` だけを `failed` として記録する(終了通知 `failed` は送らない)。
ほかの例外は伝播する。
"""

import logging
from dataclasses import dataclass

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.crawl.dependencies import CrawlDependencies
from loreley_crawler.crawl.failure import CrawlFailure
from loreley_crawler.crawl.run import CrawlRun
from loreley_crawler.crawl.start import prepare_crawl
from loreley_crawler.crawl.tally import RegistrationTally
from loreley_crawler.infrastructure.indexer_client import FinishOutcome
from loreley_crawler.jobs import (
    CancellationRequested,
    FailureReason,
    JobContext,
    JobNotStartable,
    JobRecord,
    JobStatus,
    MaintenanceDetected,
    OwnershipLost,
    loggable_id,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReadyToFinish:
    """列挙が `Completed` で、すべての応答を確認し、登録結果の確定と整理まで終えた。

    次は終了通知。`run` の列挙と Connector は閉じてあるが、状態(`tally` など)は読める。
    """

    run: CrawlRun


@dataclass(frozen=True)
class FailureRecorded:
    """ジョブを `failed` として記録した(`recorded` は `JobContext.finish` の戻り値)。

    False は、すでに終端だったこと(再判定しない)。`run` の状態(`start_notice_sent` など)は、
    終了通知 `failed` の条件に使う。
    """

    failure: CrawlFailure
    recorded: bool
    run: CrawlRun | None  # 実行開始に失敗したときは None(開始通知の前)


StageResult = ReadyToFinish | FailureRecorded


class CrawlExecutor:
    def __init__(self, dependencies: CrawlDependencies) -> None:
        self._dependencies = dependencies

    def __call__(self, record: JobRecord, context: JobContext) -> None:
        """`JobExecutor`。最終状態の記録まで行う(上記)。"""
        _log_start(record, context)
        run: CrawlRun | None = None
        try:
            run = self._begin(record, context)
            self._run_to_the_end(run, context)
        except JobNotStartable:
            raise
        except Exception as error:
            self._end_abnormally(context, run, error)
        finally:
            if run is not None:
                run.close()

    def run_until_finish_notice(self, record: JobRecord, context: JobContext) -> StageResult:
        """実行開始から、登録結果の確定・整理まで(終了通知の手前まで)を実行する(テスト用)。"""
        _log_start(record, context)
        run: CrawlRun | None = None
        try:
            run = self._begin(record, context)
            self._run_until_finish_notice(run)
            return ReadyToFinish(run)
        except CrawlFailure as failure:
            changes = {"registration": run.registration_record() if run else _zero_registration()}
            recorded = _finish_failed(context, failure.reason, failure.detail, changes)
            return FailureRecorded(failure, recorded, run)
        finally:
            if run is not None:
                run.close()

    # --- 正常 ---

    def _begin(self, record: JobRecord, context: JobContext) -> CrawlRun:
        prepared = prepare_crawl(
            record=record,
            context=context,
            source_reader=self._dependencies.source_reader,
            connector_registry=self._dependencies.connector_registry,
        )
        return CrawlRun(prepared=prepared, context=context, dependencies=self._dependencies)

    def _run_until_finish_notice(self, run: CrawlRun) -> None:
        """開始通知 -> チャンク処理 -> 登録結果の確定 -> 件数の確認 -> 整理(手順 9〜11 の前半)。"""
        run.send_start_notice()
        run.process_chunks()
        run.finalize_registration()
        run.check_the_counts_add_up()  # 壊れた集計をもとに整理しない(整理の前)
        run.purge_document_records()

    def _run_to_the_end(self, run: CrawlRun, context: JobContext) -> None:
        self._run_until_finish_notice(run)
        # 取得と列挙は終わった。ポーリングの間、Connector を開いたままにしない。
        run.close()
        run.send_finish_notice()
        polling = run.poll_deletion_status()
        has_skips_or_invalid_ids = bool(run.tally.skipped_document_ids) or (
            run.tally.invalid_id_count > 0
        )
        status = JobStatus.PARTIALLY_SUCCEEDED if has_skips_or_invalid_ids else JobStatus.SUCCEEDED
        # 原本サイズ超過・抽出失敗・削除結果(`skipped_by_ratio` など)は、status を変えない(4.2)。
        # False は、すでに終端(他者が終端にした)。実行結果を再判定しない。
        recorded = context.finish(status, changes=run.final_changes(polling))
        _log_ended(context, status.value, recorded)

    # --- 異常 ---

    def _end_abnormally(self, context: JobContext, run: CrawlRun | None, error: Exception) -> None:
        if context.is_terminal:
            # 他者が終端にした(`failed`(`lock_released`) など)。上書きも、終了通知も送らない。
            logger.warning(
                "the job was already finished by another writer: job_id=%s",
                loggable_id(context.job_id),
            )
            return
        if isinstance(error, CancellationRequested):
            self._end_cancelled(context, run)
            return
        reason, detail = _failure_of(error)
        if run is None:
            changes: dict[str, object] = {"registration": _zero_registration()}
        else:
            run.notify_outcome(FinishOutcome.FAILED)
            changes = run.final_changes(None)
        _finish_failed(context, reason, detail, changes)

    def _end_cancelled(self, context: JobContext, run: CrawlRun | None) -> None:
        if run is None:
            changes: dict[str, object] = {"registration": _zero_registration()}
        else:
            run.notify_outcome(FinishOutcome.CANCELLED)
            changes = run.final_changes(run.abort_polling_on_cancel())
        recorded = context.finish(JobStatus.CANCELLED, changes=changes)
        _log_ended(context, JobStatus.CANCELLED.value, recorded)


def _finish_failed(
    context: JobContext, reason: FailureReason, detail: str | None, changes: dict[str, object]
) -> bool:
    """`failed` を記録する。`changes` の登録結果は、確定前なら `partial=true` のまま(CA-K-15)。"""
    recorded = context.finish(
        JobStatus.FAILED, failure_reason=reason, failure_detail=detail, changes=changes
    )
    _log_ended(context, f"failed({reason.value})", recorded)
    return recorded


def _log_ended(context: JobContext, outcome: str, recorded: bool) -> None:
    """最終状態の記録を、ログに残す。`recorded` が False なら、すでに終端だった(他者が記録した)。"""
    if recorded:
        logger.info("crawl ended: job_id=%s outcome=%s", loggable_id(context.job_id), outcome)
    else:
        logger.warning(
            "crawl ended but the job was already finished: job_id=%s intended=%s",
            loggable_id(context.job_id),
            outcome,
        )


def _zero_registration() -> dict[str, object]:
    """集計が 1 件もない段階の登録結果(0 件・`partial=true`。CA-K-15)。"""
    return RegistrationTally().to_record(enumerated_count=0)


def _failure_of(error: Exception) -> tuple[FailureReason, str | None]:
    """例外を、`failed` の理由コードと説明にする(architecture 4.8)。説明は固定文と固定名だけ。"""
    if isinstance(error, CrawlFailure):
        return error.reason, error.detail
    if isinstance(error, OwnershipLost):
        return FailureReason.LOCK_LOST, f"ロックの所有権を失った({error.reason})"
    if isinstance(error, MaintenanceDetected):
        return FailureReason.MAINTENANCE, "メンテナンスフラグが立っている"
    if isinstance(error, StoreUnavailableError):
        return FailureReason.STORE_UNAVAILABLE, f"Store 層の操作に失敗した({error.reason})"
    if isinstance(error, StoreUnexpectedResponseError):
        return FailureReason.INTERNAL_ERROR, f"Store 層の想定外の応答({error.error_type})"
    # 例外のメッセージには、パス・設定値が入りうるので載せない(R11)。型名だけ。
    logger.warning("crawl ended with an unexpected error: error=%s", type(error).__name__)
    return FailureReason.INTERNAL_ERROR, f"想定外の例外: {type(error).__name__}"


def _log_start(record: JobRecord, context: JobContext) -> None:
    logger.info(
        "crawl started: job_id=%s source_id=%s",
        loggable_id(context.job_id),
        loggable_id(record.source_id),
    )
