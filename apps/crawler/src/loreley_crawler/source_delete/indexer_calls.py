"""ソース削除 1〜3 の Indexer への呼び出し: リトライ・確認点・失敗の対応づけ(architecture 8.1)。

どの呼び出しも、各試行の前に確認点(所有・メンテナンスフラグ)を通す(R8。architecture 7.9・8.1。
CA-U-17)。取り消しは確認しない(ソース削除は取り消せない。crawler-api 4.2)。
- `IndexerUnavailable`(500・503・接続エラー・タイムアウト): リトライし、直らなければ
  `failed`(`indexer_unavailable`)。再実行で続きから完了する(8.3)
- 409 `lock_not_owned`: リトライせず、所有権の喪失として記録して `failed`(`lock_lost`)
- そのほかの拒否(400・409・404・405・契約外の応答): リトライせず `failed`(`indexer_rejected`)

本文・Indexer のエラーメッセージ・リクエストの値は、説明にもログにも出さない(R11)。
"""

from collections.abc import Callable

from loreley_crawler.infrastructure.indexer_client import IndexerRejected, IndexerUnavailable
from loreley_crawler.jobs import (
    LOSS_LOCK_NOT_OWNED,
    Check,
    FailureReason,
    JobContext,
    OwnershipLost,
)
from loreley_crawler.source_delete.failure import SourceDeleteFailure

# Indexer の API ごとの確認点。取り消しを含めない(ソース削除は取り消せない)。
INDEXER_CHECKS = Check.OWNERSHIP | Check.MAINTENANCE

LOCK_NOT_OWNED = "lock_not_owned"


def call_indexer[T](
    context: JobContext,
    step: str,
    operation: Callable[[], T | IndexerUnavailable | IndexerRejected],
) -> T:
    """`operation`(Indexer への 1 回の要請)を、確認点つきでリトライして呼び、成功の結果を返す。

    `step` は説明に載せる固定の名前(`IndexerClient` の操作名)。失敗は例外(`OwnershipLost`・
    `MaintenanceDetected`・`SourceDeleteFailure`)で知らせる。
    """
    reply = context.retrier(INDEXER_CHECKS).run(
        operation, is_retryable_result=lambda reply: isinstance(reply, IndexerUnavailable)
    )
    if isinstance(reply, IndexerUnavailable):
        raise SourceDeleteFailure(
            FailureReason.INDEXER_UNAVAILABLE,
            f"Indexer が応答しない({step}。{reply.reason})",
        )
    if isinstance(reply, IndexerRejected):
        if reply.status_code == 409 and reply.error_code == LOCK_NOT_OWNED:
            context.record_lock_not_owned()
            raise OwnershipLost(LOSS_LOCK_NOT_OWNED)
        raise SourceDeleteFailure(
            FailureReason.INDEXER_REJECTED,
            f"Indexer が要請を拒否した({step}。HTTP {reply.status_code}、{reply.error_code})",
        )
    return reply
