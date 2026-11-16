"""Indexer への要請(順 1・2・4)のエラー別の扱い(architecture 7.8・8.1。テスト観点 #11 の対応分)。

- 500・503・接続エラー・タイムアウト: リトライ(最大 3 回・バックオフ)し、直らなければ
  `failed`(`indexer_unavailable`)。後続の削除は行わない
- 400・409(`lock_not_owned` 以外)・404・405・契約外の応答: リトライせず `failed`(`indexer_rejected`)
- 409 `lock_not_owned`: リトライせず所有権の喪失を記録して `failed`(`lock_lost`)
"""

import pytest

from loreley_crawler.infrastructure.indexer_client import (
    MALFORMED_RESPONSE,
    IndexerRejected,
    IndexerUnavailable,
)
from tests.fakes.fake_indexer_client import (
    DELETE_DELETION_RECORDS,
    DELETE_DOCUMENTS,
    DISCARD_DELETIONS,
)
from tests.source_delete.support import INDEXER_STEPS, SourceDeleteEnv, source_delete_env

UNAVAILABLE_REASONS = ["http_500", "http_503", "connection_error", "timeout"]


def attempts_of(env: SourceDeleteEnv, step: str) -> int:
    return len(env.indexer.calls_of(step))


# --- 一時的な障害: リトライして成功する ---


@pytest.mark.parametrize("step", INDEXER_STEPS)
@pytest.mark.parametrize("reason", UNAVAILABLE_REASONS)
def test_a_transient_failure_is_retried_and_the_job_completes(step: str, reason: str) -> None:
    with source_delete_env() as env:
        env.indexer.behavior.inject(step, IndexerUnavailable(reason), times=2)

        body = env.run()

        assert body["status"] == "succeeded"
        assert attempts_of(env, step) == 3
        assert env.sleeps == [1.0, 2.0]  # バックオフ(初回 1 秒・2 倍)
        assert env.source_body() is None


# --- 直らない障害: failed(indexer_unavailable) ---


@pytest.mark.parametrize("step", INDEXER_STEPS)
@pytest.mark.parametrize("reason", UNAVAILABLE_REASONS)
def test_a_failure_that_persists_fails_the_job_after_three_attempts(step: str, reason: str) -> None:
    with source_delete_env() as env:
        env.seed_document_records()
        env.indexer.behavior.inject(step, IndexerUnavailable(reason), times=None)

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "indexer_unavailable")
        assert attempts_of(env, step) == 3  # 最大 3 回(最初の 1 回を含む)
        assert env.sleeps == [1.0, 2.0]
        # 後続の削除は 1 回も呼ばれない。順 5 の設定の削除もしない(再実行で続きから消す)。
        position = INDEXER_STEPS.index(step)
        assert env.indexer_calls() == [*INDEXER_STEPS[:position], *([step] * 3)]
        assert "sources:delete:docs" not in env.events
        source = env.source_body()
        assert source is not None and source["status"] == "deleting"
        # 説明は固定の語彙(操作名と理由)だけ。
        assert body["failure_detail"] == f"Indexer が応答しない({step}。{reason})"


def test_a_failure_before_step_3_does_not_touch_the_document_records() -> None:
    with source_delete_env() as env:
        records = env.seed_document_records()
        env.indexer.behavior.inject(DELETE_DOCUMENTS, IndexerUnavailable("http_503"), times=None)

        env.run()

        assert set(env.jobs.jobs_repository.record_ids()) >= records
        assert {"skip-docs-aaa", "oversize-docs-aaa"} <= set(env.jobs.jobs_repository.record_ids())
        assert not [e for e in env.events if e.startswith("jobs:scan:")]


def test_a_failure_of_step_4_leaves_the_config_and_the_job_failed() -> None:
    with source_delete_env() as env:
        env.seed_document_records()
        env.indexer.behavior.inject(
            DELETE_DELETION_RECORDS, IndexerUnavailable("timeout"), times=None
        )

        body = env.run()

        assert body["failure_reason"] == "indexer_unavailable"
        # 順 3 までは済んでいる(再実行で、順 3・5 は削除済みなら成功)。
        assert "skip-docs-aaa" not in env.jobs.jobs_repository.record_ids()
        assert "sources:delete:docs" not in env.events


# --- 拒否: failed(indexer_rejected)。リトライしない ---

REJECTIONS = [
    IndexerRejected(400, "invalid_request"),
    IndexerRejected(409, "crawl_finished"),  # lock_not_owned 以外の 409
    IndexerRejected(409, None),
    IndexerRejected(404, "not_found"),
    IndexerRejected(405, "method_not_allowed"),
    IndexerRejected(401, "http_error"),
    IndexerRejected(200, MALFORMED_RESPONSE),  # 契約外の 2xx
]


@pytest.mark.parametrize("step", INDEXER_STEPS)
@pytest.mark.parametrize("rejection", REJECTIONS, ids=lambda r: f"{r.status_code}-{r.error_code}")
def test_a_rejection_is_not_retried_and_fails_the_job(
    step: str, rejection: IndexerRejected
) -> None:
    with source_delete_env() as env:
        env.seed_document_records()
        env.indexer.behavior.inject(step, rejection, times=None)

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "indexer_rejected")
        assert attempts_of(env, step) == 1
        assert env.sleeps == []
        assert env.indexer_calls() == INDEXER_STEPS[: INDEXER_STEPS.index(step) + 1]
        assert "sources:delete:docs" not in env.events
        detail = f"HTTP {rejection.status_code}、{rejection.error_code}"
        assert body["failure_detail"] == f"Indexer が要請を拒否した({step}。{detail})"
        assert env.heartbeat.lost_reason is None  # 所有権の喪失ではない


# --- 409 lock_not_owned: failed(lock_lost) ---


@pytest.mark.parametrize("step", INDEXER_STEPS)
def test_lock_not_owned_is_recorded_as_a_loss_and_fails_the_job_without_retry(step: str) -> None:
    with source_delete_env() as env:
        env.seed_document_records()
        env.indexer.behavior.inject(step, IndexerRejected(409, "lock_not_owned"), times=None)

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "lock_lost")
        assert body["failure_detail"] == "ロックの所有権を失った(lock_not_owned)"
        assert attempts_of(env, step) == 1
        assert env.sleeps == []
        # 喪失を記録した(Job Runner はロック文書を削除しない)。以降の確認点も止まる。
        assert env.heartbeat.lost_reason == "lock_not_owned"
        assert env.indexer_calls() == INDEXER_STEPS[: INDEXER_STEPS.index(step) + 1]
        assert "sources:delete:docs" not in env.events


# --- リトライのたびに確認点を通す(R8) ---


def test_the_ownership_is_checked_before_every_retry() -> None:
    losses: list[str] = []

    def lose_the_lock_while_waiting() -> None:
        if not losses:
            losses.append("lost")
            env.heartbeat.record_loss("lock_taken_over")

    with source_delete_env(on_sleep=lose_the_lock_while_waiting) as env:
        env.indexer.behavior.inject(DELETE_DOCUMENTS, IndexerUnavailable("http_503"), times=None)

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "lock_lost")
        assert attempts_of(env, DELETE_DOCUMENTS) == 1  # 待ちの間に失った。再試行しない
        assert "indexer:delete_deletion_records" not in env.events


def test_the_maintenance_flag_is_checked_before_every_retry() -> None:
    raised: list[str] = []

    def raise_the_flag_while_waiting() -> None:
        if not raised:
            raised.append("raised")
            env.jobs.seed_maintenance(True)

    with source_delete_env(on_sleep=raise_the_flag_while_waiting) as env:
        env.indexer.behavior.inject(DISCARD_DELETIONS, IndexerUnavailable("timeout"), times=None)

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "maintenance")
        assert attempts_of(env, DISCARD_DELETIONS) == 1


# --- 想定外 ---


def test_an_unexpected_exception_from_the_client_fails_with_internal_error_by_type_only() -> None:
    with source_delete_env() as env:
        env.indexer.behavior.inject(
            DELETE_DOCUMENTS, RuntimeError("SENTINEL_SECRET at /data/secret.txt"), times=None
        )

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "internal_error")
        assert body["failure_detail"] == "想定外の例外: RuntimeError"
        assert "SENTINEL" not in str(body)
        assert attempts_of(env, DELETE_DOCUMENTS) == 1
        assert "indexer:delete_deletion_records" not in env.events
