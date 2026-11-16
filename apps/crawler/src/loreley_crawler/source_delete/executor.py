"""ソース削除ジョブの実行対象 `SourceDeleteExecutor`(Job Runner が呼ぶ。module 4.6)。

`__call__`(`JobExecutor`)は、実行開始から最終状態の記録までを行う(architecture 8.1)。
ソース削除は**不可逆なデータ削除**なので、安全側に倒す: 所有を失った・メンテナンス中・Indexer の
拒否・想定外の応答では、後続の削除を行わずに `failed` にする。

| 順 | 内容 |
| --- | --- |
| 0 | `running` にし、設定を `status=deleting` にする(設定がなくても進める) |
| 1 | Indexer のソース削除 1(discard。そのソースの終端でない削除結果を `discarded` にする) |
| 2 | Indexer のソース削除 2(そのソースの文書をすべて削除) |
| 3 | そのソースの `skip`・`oversize` 記録を削除(他のソースの記録・ロック・ジョブ記録は消さない) |
| 4 | Indexer のソース削除 3(削除記録の削除) |
| 5 | 設定の削除(`status=deleting` のときだけ) |
| 6 | 最終状態 `succeeded` を記録(ロック文書の削除は Job Runner が最後に行う) |

- 順 1・2・4 の各試行の前に、所有・メンテナンスフラグを確認する(CA-U-17)。順 0・3・5 の各試行の
  前は、所有だけを確認する(Store 層の操作で、メンテナンスの対象である検索インデックスの書き込みでは
  ないため)。取り消しは確認しない(ソース削除は取り消せない)。
- 所有を失ったら `failed`(`lock_lost`)、フラグが立っていれば `failed`(`maintenance`)。
  Store 層の異常が続けば `failed`(`store_unavailable`)、Store 層の想定外の応答・想定外の例外は
  `failed`(`internal_error`)。ロックは保持する(Job Runner の解放まで。喪失時は削除されない)。
- **再実行**で復旧する(8.3): 順 1・2・4 は冪等、順 3・5 は削除済みなら成功。途中で止まった `failed`
  のジョブは、もう一度 `source_delete` を起動する(`deleting` のソースも受け付ける)。
- 最終状態は 1 度だけ。`JobContext.finish` が False(すでに終端)を返したときは、実行結果を
  再判定せず、何も書き足さない。
- `JobNotStartable`(取り消しに負けた)は Job Runner が扱うので伝播する。最終状態を記録できなかった
  例外はそのまま伝播し、Job Runner の最後の手段が扱う。
"""

import logging

from loreley_crawler.common.errors import (
    StoreUnavailableError,
    StoreUnexpectedResponseError,
    is_store_unavailable,
)
from loreley_crawler.infrastructure.indexer_client import LockInfo
from loreley_crawler.jobs import (
    Check,
    FailureReason,
    JobContext,
    JobNotStartable,
    JobRecord,
    JobStatus,
    MaintenanceDetected,
    OwnershipLost,
    loggable_id,
)
from loreley_crawler.source_delete.dependencies import SourceDeleteDependencies
from loreley_crawler.source_delete.failure import SourceDeleteFailure
from loreley_crawler.source_delete.indexer_calls import call_indexer
from loreley_crawler.sources import SourceNotDeleting

logger = logging.getLogger(__name__)

# Store 層の操作(順 0・3・5)の確認点。所有だけ(メモリ上の確認で、I/O なし)。
STORE_CHECKS = Check.OWNERSHIP

SOURCE_NOT_DELETING_DETAIL = "設定が deleting でないため、設定を削除しなかった"


class SourceDeleteExecutor:
    def __init__(self, dependencies: SourceDeleteDependencies) -> None:
        self._dependencies = dependencies

    def __call__(self, record: JobRecord, context: JobContext) -> None:
        """`JobExecutor`。最終状態の記録まで行う(上記)。"""
        logger.info(
            "source delete started: job_id=%s source_id=%s",
            loggable_id(context.job_id),
            loggable_id(record.source_id),
        )
        try:
            self._delete_source(record, context)
        except JobNotStartable:
            raise
        except Exception as error:
            _finish_as_failed(context, error)

    def _delete_source(self, record: JobRecord, context: JobContext) -> None:
        source_id = record.source_id
        lock = LockInfo(owner=_job_owner(record), job_id=context.job_id)
        client = self._dependencies.indexer_client

        context.start_running()
        self._mark_source_deleting(context, source_id)  # 順 0
        call_indexer(
            context, "discard_deletions", lambda: client.discard_deletions(source_id, lock=lock)
        )
        call_indexer(
            context, "delete_documents", lambda: client.delete_documents(source_id, lock=lock)
        )
        self._delete_document_records(context, source_id)  # 順 3
        call_indexer(
            context,
            "delete_deletion_records",
            lambda: client.delete_deletion_records(source_id, lock=lock),
        )
        self._delete_source_config(context, source_id)  # 順 5

        # 順 6。False は、すでに終端(他者が終端にした)。再判定しない。
        recorded = context.finish(JobStatus.SUCCEEDED)
        _log_ended(context, "succeeded", recorded)

    def _mark_source_deleting(self, context: JobContext, source_id: str) -> None:
        # 設定がない(`SourceNotFound`)ときも進める。以降の削除は冪等で、設定が消えた後の再実行でも
        # Indexer 側の文書・削除記録が残っていれば消すため(architecture 8.3)。
        context.retrier(STORE_CHECKS).run(
            lambda: self._dependencies.source_store.mark_deleting(source_id),
            is_retryable_error=is_store_unavailable,
        )

    def _delete_document_records(self, context: JobContext, source_id: str) -> None:
        self._dependencies.document_records.delete_all_of_source(
            source_id=source_id, retrier=context.retrier(STORE_CHECKS)
        )

    def _delete_source_config(self, context: JobContext, source_id: str) -> None:
        result = context.retrier(STORE_CHECKS).run(
            lambda: self._dependencies.source_store.delete(source_id),
            is_retryable_error=is_store_unavailable,
        )
        if isinstance(result, SourceNotDeleting):
            # 順 0 の後に、設定が作り直された。別の設定を消さないために、削除しない。
            raise SourceDeleteFailure(FailureReason.INTERNAL_ERROR, SOURCE_NOT_DELETING_DETAIL)


def _finish_as_failed(context: JobContext, error: Exception) -> None:
    reason, detail = _failure_of(error)
    recorded = context.finish(JobStatus.FAILED, failure_reason=reason, failure_detail=detail)
    _log_ended(context, f"failed({reason.value})", recorded)


def _failure_of(error: Exception) -> tuple[FailureReason, str]:
    """例外を、`failed` の理由コードと説明にする(architecture 4.8)。説明は固定文と固定名だけ。"""
    if isinstance(error, SourceDeleteFailure):
        return error.reason, error.detail
    if isinstance(error, OwnershipLost):
        return FailureReason.LOCK_LOST, f"ロックの所有権を失った({error.reason})"
    if isinstance(error, MaintenanceDetected):
        return FailureReason.MAINTENANCE, "メンテナンスフラグが立っている"
    if isinstance(error, StoreUnavailableError):
        return FailureReason.STORE_UNAVAILABLE, f"Store 層の操作に失敗した({error.reason})"
    if isinstance(error, StoreUnexpectedResponseError):
        return FailureReason.INTERNAL_ERROR, f"Store 層の想定外の応答({error.error_type})"
    # 例外のメッセージには、識別子・設定値が入りうるので載せない(R11)。型名だけ。
    logger.warning("source delete ended with an unexpected error: error=%s", type(error).__name__)
    return FailureReason.INTERNAL_ERROR, f"想定外の例外: {type(error).__name__}"


def _log_ended(context: JobContext, outcome: str, recorded: bool) -> None:
    """最終状態の記録を、ログに残す。`recorded` が False なら、すでに終端だった。"""
    if recorded:
        logger.info(
            "source delete ended: job_id=%s outcome=%s", loggable_id(context.job_id), outcome
        )
    else:
        logger.warning(
            "source delete ended but the job was already finished: job_id=%s intended=%s",
            loggable_id(context.job_id),
            outcome,
        )


def _job_owner(record: JobRecord) -> str:
    owner = record.fields.get("owner")
    if not isinstance(owner, str):
        raise StoreUnexpectedResponseError("malformed_job_record")
    return owner
