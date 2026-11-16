"""所有を失った・メンテナンス中のとき、後続の削除を 1 回も行わず `failed` にする(#16・#34)。

ソース削除は不可逆なデータ削除なので、安全側に倒す。「後続の削除が呼ばれない」ことは、破壊的な
操作の時系列(`destructive_events`)が、失った時点までで止まっていることで確かめる。
"""

import logging
from collections.abc import Callable

import pytest

from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.infrastructure.indexer_client import IndexerRejected
from loreley_crawler.jobs.locks.lock_document import new_lock_fields
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import DEFAULT_NOW
from tests.fakes.fake_indexer_client import (
    DELETE_DELETION_RECORDS,
    DELETE_DOCUMENTS,
    DISCARD_DELETIONS,
)
from tests.jobs.support import JOB_ID, LOCK_ID, OTHER_JOB_ID, OTHER_OWNER, SOURCE_ID
from tests.source_delete.support import SourceDeleteEnv, source_delete_env

STEP_1 = "indexer:discard"
STEP_2 = "indexer:delete_documents"
STEP_3_SKIP_SCAN = "jobs:scan:skip"
STEP_3 = [STEP_3_SKIP_SCAN, "jobs:delete_ids:1", "jobs:scan:oversize", "jobs:delete_ids:1"]
STEP_4 = "indexer:delete_deletion_records"

Trigger = Callable[[SourceDeleteEnv, Callable[[], None]], None]


def during_discard(env: SourceDeleteEnv, action: Callable[[], None]) -> None:
    env.indexer.behavior.before(DISCARD_DELETIONS, action)


def during_delete_documents(env: SourceDeleteEnv, action: Callable[[], None]) -> None:
    env.indexer.behavior.before(DELETE_DOCUMENTS, action)


def during_the_scan_of_step_3(env: SourceDeleteEnv, action: Callable[[], None]) -> None:
    env.jobs.jobs_repository.behavior.before(ops.SCAN, action)


def during_delete_deletion_records(env: SourceDeleteEnv, action: Callable[[], None]) -> None:
    env.indexer.behavior.before(DELETE_DELETION_RECORDS, action)


# 失った(立った)時点 → その時点までに、実際に行われた破壊的な操作。
# 順 3 は、削除する記録があるとき、各削除の前に所有を確認する。
STOPPING_POINTS: list[tuple[Trigger, list[str]]] = [
    (during_discard, [STEP_1]),
    (during_delete_documents, [STEP_1, STEP_2]),
    (during_the_scan_of_step_3, [STEP_1, STEP_2, STEP_3_SKIP_SCAN]),
    (during_delete_deletion_records, [STEP_1, STEP_2, *STEP_3, STEP_4]),
]
STOPPING_POINT_IDS = ["discard", "delete_documents", "step_3_scan", "delete_deletion_records"]


def assert_the_config_is_kept(env: SourceDeleteEnv) -> None:
    """設定の削除(順 5)は行われていない。順 0 の `deleting` は残る(再実行で復旧する)。"""
    assert "sources:delete:docs" not in env.events
    source = env.source_body()
    assert source is not None and source["status"] == "deleting"


# --- 所有権の喪失 ---


def test_a_loss_recorded_before_the_run_stops_before_the_first_write() -> None:
    with source_delete_env() as env:
        env.seed_document_records()
        env.heartbeat.record_loss("lock_missing")

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "lock_lost")
        assert env.destructive_events() == []
        assert "sources:replace:docs" not in env.events  # 順 0 も行わない
        source = env.source_body()
        assert source is not None and source["status"] == "active"


@pytest.mark.parametrize(("trigger", "expected"), STOPPING_POINTS, ids=STOPPING_POINT_IDS)
def test_a_loss_stops_every_later_deletion_and_fails_with_lock_lost(
    trigger: Trigger, expected: list[str]
) -> None:
    with source_delete_env() as env:
        env.seed_document_records()
        trigger(env, lambda: env.heartbeat.record_loss("lock_taken_over"))

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "lock_lost")
        assert body["failure_detail"] == "ロックの所有権を失った(lock_taken_over)"
        assert env.destructive_events() == expected
        assert_the_config_is_kept(env)
        assert env.context.is_terminal


@pytest.mark.parametrize(("trigger", "expected"), STOPPING_POINTS, ids=STOPPING_POINT_IDS)
def test_a_loss_leaves_the_records_the_later_steps_would_have_deleted(
    trigger: Trigger, expected: list[str]
) -> None:
    with source_delete_env() as env:
        env.seed_document_records()
        trigger(env, lambda: env.heartbeat.record_loss("lock_taken_over"))
        records_before = set(env.jobs.jobs_repository.record_ids())

        env.run()

        deleted = records_before - set(env.jobs.jobs_repository.record_ids())
        # 順 3 の削除は、所有を失う前に始まっていた分だけ(スキップ・サイズ超過の記録)。
        if "jobs:delete_ids:1" in expected:
            assert deleted <= {"skip-docs-aaa", "oversize-docs-aaa"}
        else:
            assert deleted == set()


def test_an_expired_lease_without_a_recorded_loss_stops_the_next_deletion() -> None:
    """ハートビートが止まってリースが切れた(喪失は記録されていない)ときも、要請しない。"""
    with source_delete_env() as env:
        during_discard(env, lambda: env.jobs.clock.advance(seconds=301))

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "lock_lost")
        assert body["failure_detail"] == "ロックの所有権を失った(lease_expired)"
        assert env.destructive_events() == [STEP_1]


def test_a_lock_taken_over_is_noticed_by_the_heartbeat_and_stops_the_next_deletion() -> None:
    with source_delete_env() as env:

        def another_job_takes_the_lock() -> None:
            env.jobs.jobs_repository.seed(
                LOCK_ID,
                new_lock_fields(
                    source_id=SOURCE_ID,
                    owner=OTHER_OWNER,
                    job_id=OTHER_JOB_ID,
                    acquired_at=DEFAULT_NOW,
                ),
            )
            env.heartbeat.tick()  # ハートビートの更新が、他のジョブのロックを見つける

        during_delete_documents(env, another_job_takes_the_lock)

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "lock_lost")
        assert env.destructive_events() == [STEP_1, STEP_2]
        lock = env.jobs.lock_body()
        assert lock is not None and lock["job_id"] == OTHER_JOB_ID  # 他のジョブのロックを消さない


# --- メンテナンスフラグ(#34。順 1・2・4 の前) ---


def test_a_flag_raised_before_the_run_stops_before_the_first_indexer_call() -> None:
    with source_delete_env() as env:
        env.jobs.seed_maintenance(True)

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "maintenance")
        assert body["failure_detail"] == "メンテナンスフラグが立っている"
        assert env.destructive_events() == []
        # 順 0 は行う(設定を `deleting` にする。新しいクロールを起動させない側の変更)。
        source = env.source_body()
        assert source is not None and source["status"] == "deleting"


@pytest.mark.parametrize("enabled", ["yes", 1, None, "false"])
def test_a_malformed_flag_counts_as_raised(enabled: object) -> None:
    """形式が不正(`enabled` が真偽値でない)なら、立っているとみなす(fail-closed。7.9)。"""
    with source_delete_env() as env:
        env.jobs.seed_maintenance(enabled)

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "maintenance")
        assert env.destructive_events() == []


def test_a_flag_explicitly_false_does_not_stop_the_job() -> None:
    with source_delete_env() as env:
        env.jobs.seed_maintenance(False)

        assert env.run()["status"] == "succeeded"


def test_a_flag_raised_during_the_first_indexer_call_stops_the_second() -> None:
    with source_delete_env() as env:
        env.seed_document_records()
        during_discard(env, lambda: env.jobs.seed_maintenance(True))

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "maintenance")
        assert env.destructive_events() == [STEP_1]
        assert_the_config_is_kept(env)


def test_a_flag_raised_during_the_second_indexer_call_stops_step_4_and_5() -> None:
    with source_delete_env() as env:
        env.seed_document_records()
        during_delete_documents(env, lambda: env.jobs.seed_maintenance(True))

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "maintenance")
        assert STEP_4 not in env.events
        assert_the_config_is_kept(env)


def test_the_flag_is_read_before_each_of_the_indexer_calls() -> None:
    with source_delete_env() as env:
        flag_reads_at_each_call: list[int] = []

        def count_reads() -> None:
            flag_reads_at_each_call.append(
                len(
                    [
                        c
                        for c in env.jobs.jobs_repository.behavior.calls_of(ops.FETCH)
                        if c.key == "maintenance"
                    ]
                )
            )

        for step in (DISCARD_DELETIONS, DELETE_DOCUMENTS, DELETE_DELETION_RECORDS):
            env.indexer.behavior.before(step, count_reads)

        env.run()

        # 各 Indexer の呼び出しの前に、1 回ずつ読む(順 1・2・4)。
        assert flag_reads_at_each_call == [1, 2, 3]


def test_an_unreadable_flag_store_fails_without_calling_the_indexer() -> None:
    with source_delete_env() as env:
        env.jobs.jobs_repository.behavior.inject(
            ops.FETCH, StoreUnavailableError("timeout"), key="maintenance", times=None
        )

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "store_unavailable")
        assert env.destructive_events() == []


# --- 取り消しは確認点でない / 他者が終端にしたジョブ ---


def mark_the_job_released_by_the_admin(env: SourceDeleteEnv) -> None:
    env.jobs.jobs_repository.seed(
        JOB_ID,
        {
            **env.jobs.job_body(),
            "status": "failed",
            "failure_reason": "lock_released",
            "finished_at": "2026-11-13T00:09:00.000Z",
        },
    )


def test_a_job_finished_by_someone_else_is_not_overwritten_and_is_not_judged_again(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`finish` の False は「すでに終端」。成功を再判定して上書きしない。"""
    with source_delete_env() as env:
        during_discard(env, lambda: mark_the_job_released_by_the_admin(env))

        with caplog.at_level(logging.INFO):
            body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "lock_released")
        assert body["finished_at"] == "2026-11-13T00:09:00.000Z"
        assert env.heartbeat.lost_reason == "job_record_superseded"  # Job Runner はロックを消さない
        assert "already finished" in caplog.text
        assert "source delete ended:" not in caplog.text  # 成功として記録していない


def test_a_failure_after_someone_else_finished_the_job_does_not_overwrite_it() -> None:
    with source_delete_env() as env:
        during_delete_documents(env, lambda: mark_the_job_released_by_the_admin(env))
        env.indexer.behavior.inject(DELETE_DOCUMENTS, IndexerRejected(400, "invalid_request"))

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "lock_released")
        assert STEP_4 not in env.events
