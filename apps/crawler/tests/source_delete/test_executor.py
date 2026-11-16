"""ソース削除ジョブの実行(architecture 8.1 の順 0〜6。テスト観点 #16)。

正常系: 順序、ロックと所有、設定の削除、他のソースの記録を消さないこと、再実行(冪等)。
安全側の分岐(`failed`)は `test_safety.py`・`test_indexer_errors.py`・`test_store_errors.py`。
"""

import pytest

from loreley_crawler.jobs import JobNotStartable
from loreley_crawler.sources import SourceStatus
from tests.fakes import in_memory_repository as ops
from tests.fakes.fake_indexer_client import DISCARD_DELETIONS
from tests.jobs.support import JOB_ID, LOCK_ID, OWNER, SOURCE_ID
from tests.source_delete.support import (
    EXPECTED_LOCK,
    INDEXER_STEPS,
    OTHER_JOB_ID,
    OTHER_SOURCE_ID,
    OVERSIZE_ID,
    SKIP_ID,
    source_delete_env,
)

FULL_RUN = [
    "indexer:discard",
    "indexer:delete_documents",
    "jobs:scan:skip",
    "jobs:delete_ids:1",
    "jobs:scan:oversize",
    "jobs:delete_ids:1",
    "indexer:delete_deletion_records",
    "sources:delete:docs",
]


def test_the_steps_run_in_the_order_of_the_design() -> None:
    with source_delete_env() as env:
        env.seed_document_records()

        body = env.run()

        assert body["status"] == "succeeded"
        # 順 0(設定を deleting に)→ 1 → 2 → 3(skip・oversize)→ 4 → 5 → 6(最終状態)。
        written = [e for e in env.events if e != "jobs:replace:" + JOB_ID]
        assert written == ["sources:replace:docs", *FULL_RUN]
        # 最終状態の記録(順 6)は、順 5 の後。実行開始(running)は、順 0 より前。
        job_writes = [i for i, e in enumerate(env.events) if e == f"jobs:replace:{JOB_ID}"]
        assert job_writes[0] < env.events.index("sources:replace:docs")
        assert job_writes[-1] > env.events.index("sources:delete:docs")


def test_the_job_is_running_and_the_source_is_deleting_before_the_first_indexer_call() -> None:
    with source_delete_env() as env:
        observed: list[tuple[object, object, object]] = []

        def observe() -> None:
            source = env.source_body()
            observed.append(
                (
                    env.jobs.job_body()["status"],
                    source and source["status"],
                    source and source["updated_at"],
                )
            )

        env.indexer.behavior.before(DISCARD_DELETIONS, observe)
        original_updated_at = env.source_body()["updated_at"]  # type: ignore[index]

        env.run()

        # `updated_at` は変えない(定期起動の起点に使うため。architecture 3.2)。
        assert observed == [("running", "deleting", original_updated_at)]


def test_every_indexer_call_carries_the_source_and_the_lock_of_the_job() -> None:
    with source_delete_env() as env:
        env.run()

        calls = env.indexer.calls_of(*INDEXER_STEPS)
        assert [call.operation for call in calls] == list(INDEXER_STEPS)
        assert [call.arguments["source_id"] for call in calls] == [SOURCE_ID] * 3
        assert [call.arguments["lock"] for call in calls] == [EXPECTED_LOCK] * 3
        assert EXPECTED_LOCK.owner == OWNER
        assert EXPECTED_LOCK.job_id == JOB_ID


def test_the_lock_and_the_heartbeat_hold_at_every_step_until_the_end() -> None:
    with source_delete_env() as env:
        held: list[str] = []

        def check_held(step: str) -> None:
            lock = env.jobs.lock_body()
            owned = env.heartbeat.is_owned()
            held.append(step if lock is not None and lock["job_id"] == JOB_ID and owned else "")

        for step in INDEXER_STEPS:
            env.indexer.behavior.before(step, lambda step=step: check_held(step))
        env.jobs.jobs_repository.behavior.before(ops.SCAN, lambda: check_held("scan"))
        env.jobs.sources_repository.behavior.before(ops.DELETE, lambda: check_held("config"))

        env.run()

        assert held == [*INDEXER_STEPS[:2], "scan", INDEXER_STEPS[2], "config"]
        # 実行対象は、ロック文書を削除しない(最後の削除は Job Runner。`test_end_to_end.py`)。
        lock = env.jobs.lock_body()
        assert lock is not None and lock["job_id"] == JOB_ID
        assert env.heartbeat.lost_reason is None


def test_the_final_state_is_succeeded_without_a_failure_reason_and_the_config_is_gone() -> None:
    with source_delete_env() as env:
        body = env.run()

        assert body["status"] == "succeeded"
        assert body["finished_at"] == "2026-11-13T00:00:00.000Z"
        assert "failure_reason" not in body
        assert "failure_detail" not in body
        assert env.source_body() is None
        assert env.context.is_terminal


def test_only_the_records_of_this_source_are_deleted_in_step_3() -> None:
    with source_delete_env() as env:
        remaining = env.seed_document_records()
        before = set(env.jobs.jobs_repository.record_ids())

        env.run()

        after = set(env.jobs.jobs_repository.record_ids())
        assert before - after == {SKIP_ID, OVERSIZE_ID}
        assert after == remaining
        # 他のソースの記録・ロック文書・ジョブ記録、メンテナンスフラグ、このジョブの記録とロック。
        assert {
            f"skip-{OTHER_SOURCE_ID}-aaa",
            f"oversize-{OTHER_SOURCE_ID}-aaa",
            OTHER_JOB_ID,
            f"lock-{OTHER_SOURCE_ID}",
            "maintenance",
            JOB_ID,
            LOCK_ID,
        } <= after


def test_records_of_a_source_whose_id_only_starts_the_same_are_not_deleted() -> None:
    with source_delete_env() as env:
        repository = env.jobs.jobs_repository
        for source_id in ("doc", "docs2", "docs-"):
            repository.seed(
                f"skip-{source_id}-x",
                {"record_type": "skip", "source_id": source_id, "document_id": "x"},
            )
        env.seed_document_records()

        env.run()

        assert {"skip-doc-x", "skip-docs2-x", "skip-docs--x"} <= set(repository.record_ids())


def test_a_malformed_record_of_the_source_without_a_document_id_is_deleted_too() -> None:
    with source_delete_env() as env:
        env.jobs.jobs_repository.seed(
            "skip-docs-bad", {"record_type": "skip", "source_id": SOURCE_ID}
        )

        env.run()

        assert "skip-docs-bad" not in env.jobs.jobs_repository.record_ids()


def test_the_step_3_scans_each_record_type_once_and_then_deletes() -> None:
    with source_delete_env() as env:
        env.seed_document_records()

        env.run()

        scans = [e for e in env.events if e.startswith("jobs:scan:")]
        assert scans == ["jobs:scan:skip", "jobs:scan:oversize"]
        assert env.jobs.jobs_repository.open_scan_count == 0  # PIT を閉じている


# --- 再実行(冪等。architecture 8.3) ---


def test_a_missing_config_still_completes_and_the_idempotent_steps_run() -> None:
    """設定がない(順 5 の後に止まった・すでに削除済み)でも成功する。Indexer の掃除も行う。"""
    with source_delete_env(seed_source=False) as env:
        body = env.run()

        assert body["status"] == "succeeded"
        assert env.indexer_calls() == list(INDEXER_STEPS)
        assert "sources:replace:docs" not in env.events  # 作らない・書かない
        assert env.source_body() is None


def test_a_source_that_is_already_deleting_is_not_rewritten_and_completes() -> None:
    with source_delete_env(source_status=SourceStatus.DELETING) as env:
        body = env.run()

        assert body["status"] == "succeeded"
        assert "sources:replace:docs" not in env.events
        assert env.source_body() is None


def test_the_cancel_request_is_not_a_check_point_of_a_source_delete() -> None:
    """ソース削除は取り消せない(crawler-api 4.2)。確認点に取り消しを含めない。"""
    with source_delete_env() as env:
        env.jobs.cancel_requests.request(JOB_ID)

        body = env.run()

        assert body["status"] == "succeeded"
        assert env.indexer_calls() == list(INDEXER_STEPS)


def test_a_job_that_lost_the_start_to_a_cancel_does_nothing_and_raises_not_startable() -> None:
    """Job Runner が取り出した後、実行開始の条件付き更新の前に取り消されたジョブ。"""
    with source_delete_env() as env:
        env.jobs.jobs_repository.seed(
            JOB_ID, {**env.jobs.job_body(), "status": "cancelled", "finished_at": "x"}
        )

        with pytest.raises(JobNotStartable):
            env.executor(env.record, env.context)

        assert env.indexer_calls() == []
        assert env.destructive_events() == []
        assert env.source_body()["status"] == "active"  # type: ignore[index]
        assert env.jobs.job_body()["status"] == "cancelled"  # 取り消しを上書きしない
