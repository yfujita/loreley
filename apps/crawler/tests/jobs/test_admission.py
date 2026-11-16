"""受付(architecture 4.3 の手順 1〜5。crawler-api 4.1・4.6。テスト観点 #13 の `create` の競合)。

拒否は、判定順(設定 → メンテナンスフラグ → ロック → 再確認)と、書き込みの有無(拒否では何も
書かない・巻き戻しはロックだけを消す)を確かめる。競合は fake の割り込みフックで再現する。
"""

import logging
import threading
from collections.abc import Callable

import pytest

from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.jobs import (
    Accepted,
    AdmissionResult,
    ExistingJob,
    JobAdmission,
    JobStatus,
    JobTrigger,
    JobType,
    LockAlreadyHeld,
    MaintenanceEnabled,
    SourceConfigNotFound,
    SourceDeleting,
)
from loreley_crawler.sources import SourceStatus
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import DEFAULT_NOW
from tests.fakes.lost_response_repository import LostResponseRepository
from tests.jobs.support import (
    ADMITTED_JOB_ID,
    JOB_ID,
    LOCK_ID,
    NO_WAIT_RETRIER,
    OTHER_JOB_ID,
    OTHER_OWNER,
    OWNER,
    SOURCE_ID,
    WAIT_TIMEOUT_SECONDS,
    JobsEnv,
    fixed_token,
    make_env,
)


def make_admission(env: JobsEnv, *, random_token: Callable[[], str] = fixed_token) -> JobAdmission:
    return JobAdmission(
        settings=env.settings,
        source_reader=env.source_reader,
        job_store=env.job_store,
        lock_store=env.lock_store,
        read_maintenance_flag=env.read_maintenance_flag,
        clock=env.clock,
        retrier=NO_WAIT_RETRIER,
        wakeup=env.wakeup,
        random_token=random_token,
    )


def assert_nothing_written(env: JobsEnv) -> None:
    assert env.jobs_repository.write_calls() == []
    assert env.sources_repository.write_calls() == []


# --- 受理 ---


def test_a_manual_crawl_is_accepted_with_a_queued_job_and_its_lock() -> None:
    env = make_env()
    env.seed_source()

    result = make_admission(env).accept_manual_crawl(
        SOURCE_ID, force_delete=True, rewrite_mode=True
    )

    assert isinstance(result, Accepted)
    job = result.job
    assert (job.job_id, job.job_type, job.source_id) == (ADMITTED_JOB_ID, JobType.CRAWL, SOURCE_ID)
    assert (job.status, job.trigger) == (JobStatus.QUEUED, JobTrigger.MANUAL)
    assert (job.force_delete, job.rewrite_mode, job.queued_at) == (True, True, DEFAULT_NOW)
    assert env.job_body(ADMITTED_JOB_ID) == {
        "record_type": "job",
        "job_id": ADMITTED_JOB_ID,
        "job_type": "crawl",
        "source_id": SOURCE_ID,
        "trigger": "manual",
        "owner": OWNER,
        "status": "queued",
        "queued_at": "2026-11-13T00:00:00.000Z",
        "force_delete": True,
        "rewrite_mode": True,
    }
    lock = env.lock_body()
    assert lock is not None
    assert (lock["owner"], lock["job_id"], lock["lease_expires_at"]) == (
        OWNER,
        ADMITTED_JOB_ID,
        None,
    )


def test_the_manual_crawl_defaults_both_flags_to_false() -> None:
    env = make_env()
    env.seed_source()

    result = make_admission(env).accept_manual_crawl(SOURCE_ID)

    assert isinstance(result, Accepted)
    assert (result.job.force_delete, result.job.rewrite_mode) == (False, False)


def test_a_scheduled_crawl_always_has_both_flags_false() -> None:  # テスト観点 #23
    env = make_env()
    env.seed_source()

    result = make_admission(env).accept_scheduled_crawl(SOURCE_ID)

    assert isinstance(result, Accepted)
    assert result.job.trigger is JobTrigger.SCHEDULE
    body = env.job_body(ADMITTED_JOB_ID)
    assert (body["trigger"], body["force_delete"], body["rewrite_mode"]) == (
        "schedule",
        False,
        False,
    )


def test_a_source_delete_is_a_manual_job_without_the_crawl_flags() -> None:
    env = make_env()
    env.seed_source()

    result = make_admission(env).accept_source_delete(SOURCE_ID)

    assert isinstance(result, Accepted)
    assert (result.job.job_type, result.job.trigger) == (JobType.SOURCE_DELETE, JobTrigger.MANUAL)
    assert (result.job.force_delete, result.job.rewrite_mode) == (False, False)
    assert env.job_body(ADMITTED_JOB_ID)["job_type"] == "source_delete"


def test_accepting_wakes_the_job_runner_but_rejecting_does_not() -> None:
    env = make_env()
    admission = make_admission(env)

    admission.accept_manual_crawl(SOURCE_ID)  # 設定がない
    assert env.wakeup.wait(0) is False

    env.seed_source()
    admission.accept_manual_crawl(SOURCE_ID)
    assert env.wakeup.wait(0) is True


def test_a_source_delete_accepts_a_deleting_source() -> None:  # architecture 8.3
    env = make_env()
    env.seed_source(status=SourceStatus.DELETING)

    result = make_admission(env).accept_source_delete(SOURCE_ID)

    assert isinstance(result, Accepted)


def test_accepting_never_changes_the_source_settings() -> None:
    env = make_env()
    env.seed_source()

    make_admission(env).accept_source_delete(SOURCE_ID)

    assert env.sources_repository.write_calls() == []
    assert env.sources_repository.body_of(SOURCE_ID) is not None


# --- 拒否と判定順(crawler-api 4.1 の判定順) ---


@pytest.mark.parametrize("entrance", ["manual", "scheduled", "source_delete"])
def test_a_missing_source_is_rejected_without_writing(entrance: str) -> None:
    env = make_env()
    admission = make_admission(env)

    result = {
        "manual": admission.accept_manual_crawl,
        "scheduled": admission.accept_scheduled_crawl,
        "source_delete": admission.accept_source_delete,
    }[entrance](SOURCE_ID)

    assert result == SourceConfigNotFound()
    assert_nothing_written(env)


@pytest.mark.parametrize("entrance", ["manual", "scheduled"])
def test_a_crawl_of_a_deleting_source_is_rejected_without_writing(entrance: str) -> None:
    env = make_env()
    env.seed_source(status=SourceStatus.DELETING)
    admission = make_admission(env)

    result = (
        admission.accept_manual_crawl(SOURCE_ID)
        if entrance == "manual"
        else admission.accept_scheduled_crawl(SOURCE_ID)
    )

    assert result == SourceDeleting()
    assert_nothing_written(env)


@pytest.mark.parametrize("enabled", [True, "false", None, 0])
def test_a_raised_or_malformed_maintenance_flag_rejects_every_entrance(enabled: object) -> None:
    env = make_env()
    env.seed_source()
    env.seed_maintenance(enabled)
    admission = make_admission(env)

    assert admission.accept_manual_crawl(SOURCE_ID) == MaintenanceEnabled()
    assert admission.accept_scheduled_crawl(SOURCE_ID) == MaintenanceEnabled()
    assert admission.accept_source_delete(SOURCE_ID) == MaintenanceEnabled()
    assert env.jobs_repository.write_calls() == []


def test_the_flag_explicitly_false_does_not_reject() -> None:  # テスト観点 #18
    env = make_env()
    env.seed_source()
    env.seed_maintenance(False)

    assert isinstance(make_admission(env).accept_manual_crawl(SOURCE_ID), Accepted)


def test_the_judgement_order_is_source_then_maintenance_then_lock() -> None:
    env = make_env()
    env.seed_maintenance()
    env.seed_lock(JOB_ID)
    admission = make_admission(env)

    # 設定がなければ、メンテナンスフラグもロックも見ずに 404。
    assert admission.accept_manual_crawl(SOURCE_ID) == SourceConfigNotFound()

    # deleting は、メンテナンスより先に拒否される(クロールだけ)。
    env.seed_source(status=SourceStatus.DELETING)
    assert admission.accept_manual_crawl(SOURCE_ID) == SourceDeleting()
    assert admission.accept_source_delete(SOURCE_ID) == MaintenanceEnabled()

    # メンテナンスは、ロックより先に拒否される。
    env.seed_source()
    assert admission.accept_manual_crawl(SOURCE_ID) == MaintenanceEnabled()

    env.seed_maintenance(False)
    assert isinstance(admission.accept_manual_crawl(SOURCE_ID), LockAlreadyHeld)


def test_a_source_with_malformed_values_is_still_accepted_for_a_crawl() -> None:
    """値の欠落・型違いは、受付では検査しない。実行開始が `config_invalid` で `failed` にする。"""
    env = make_env()
    env.seed_malformed_source(status="active", ttl="not-an-integer")

    assert isinstance(make_admission(env).accept_manual_crawl(SOURCE_ID), Accepted)


def test_a_malformed_source_that_is_deleting_is_rejected_for_a_crawl() -> None:
    env = make_env()
    env.seed_malformed_source(status="deleting")

    assert make_admission(env).accept_manual_crawl(SOURCE_ID) == SourceDeleting()


# --- lock_held ---


def test_a_held_lock_rejects_with_the_existing_job() -> None:
    env = make_env()
    env.seed_source()
    env.seed_job(JOB_ID, status=JobStatus.QUEUED)
    env.seed_lock(JOB_ID)
    before = env.jobs_repository.body_of(LOCK_ID)

    result = make_admission(env).accept_manual_crawl(SOURCE_ID, force_delete=True)

    assert result == LockAlreadyHeld(
        ExistingJob(JOB_ID, JobType.CRAWL, JobStatus.QUEUED, JobTrigger.MANUAL, None)
    )
    assert env.jobs_repository.body_of(LOCK_ID) == before  # 既存のロックを変えない
    assert env.job_ids() == [JOB_ID]  # force_delete などを、既存のジョブに反映しない


def test_the_existing_job_of_a_running_job_carries_its_lease() -> None:
    env = make_env()
    env.seed_source()
    env.seed_job(JOB_ID, status=JobStatus.RUNNING, job_type=JobType.SOURCE_DELETE)
    lock = env.seed_lock(JOB_ID, lease_expires_at="2026-11-13T00:05:00.000Z")

    result = make_admission(env).accept_source_delete(SOURCE_ID)

    assert isinstance(result, LockAlreadyHeld)
    assert result.existing_job == ExistingJob(
        JOB_ID, JobType.SOURCE_DELETE, JobStatus.RUNNING, JobTrigger.MANUAL, lock.lease_expires_at
    )


def test_a_lock_without_a_job_record_reports_unknown_fields() -> None:
    env = make_env()
    env.seed_source()
    env.seed_lock(JOB_ID)

    result = make_admission(env).accept_scheduled_crawl(SOURCE_ID)

    assert result == LockAlreadyHeld(ExistingJob(JOB_ID, None, None, None, None))


@pytest.mark.parametrize("job_id", [None, 5, ""])
def test_a_lock_without_a_readable_job_id_rejects_without_failing(job_id: object) -> None:
    env = make_env()
    env.seed_source()
    env.seed_lock(JOB_ID)
    env.jobs_repository.seed(LOCK_ID, {**(env.lock_body() or {}), "job_id": job_id})

    result = make_admission(env).accept_manual_crawl(SOURCE_ID)

    assert result == LockAlreadyHeld(ExistingJob("", None, None, None, None))


def test_a_malformed_job_record_does_not_break_the_rejection() -> None:
    env = make_env()
    env.seed_source()
    env.seed_job(JOB_ID)
    env.jobs_repository.seed(JOB_ID, {**env.job_body(JOB_ID), "status": "unknown-status"})
    env.seed_lock(JOB_ID)

    result = make_admission(env).accept_manual_crawl(SOURCE_ID)

    assert isinstance(result, LockAlreadyHeld)
    assert result.existing_job.status is None
    assert result.existing_job.job_type is JobType.CRAWL


def test_a_lock_id_given_as_a_job_id_is_not_a_job() -> None:
    env = make_env()
    env.seed_source()
    env.seed_lock(LOCK_ID)  # ロックの `job_id` が、ロックの ID を指している

    result = make_admission(env).accept_manual_crawl(SOURCE_ID)

    assert result == LockAlreadyHeld(ExistingJob(LOCK_ID, None, None, None, None))


# --- 受付の巻き戻し(手順 4) ---


def before_lock_create(env: JobsEnv, action: Callable[[], None]) -> None:
    """手順 1〜3 の間に、別の操作(ソース削除の開始など)が入る。"""
    env.jobs_repository.behavior.before(ops.CREATE, action, key=LOCK_ID)


def test_a_crawl_rolls_back_the_lock_when_the_source_became_deleting() -> None:
    env = make_env()
    env.seed_source()
    before_lock_create(env, lambda: env.seed_source(status=SourceStatus.DELETING))

    result = make_admission(env).accept_manual_crawl(SOURCE_ID)

    assert result == SourceDeleting()
    assert env.lock_body() is None
    assert env.job_ids() == []
    assert env.wakeup.wait(0) is False


def test_a_crawl_rolls_back_the_lock_when_the_source_disappeared() -> None:
    env = make_env()
    env.seed_source()

    def delete_source() -> None:
        stored = env.sources_repository.fetch(SOURCE_ID)
        assert stored is not None
        env.sources_repository.delete_if_unchanged(
            SOURCE_ID, seq_no=stored.seq_no, primary_term=stored.primary_term
        )

    before_lock_create(env, delete_source)

    result = make_admission(env).accept_manual_crawl(SOURCE_ID)

    assert result == SourceConfigNotFound()
    assert env.lock_body() is None
    assert env.job_ids() == []


def test_a_source_delete_is_not_rejected_by_a_status_that_became_deleting() -> None:
    env = make_env()
    env.seed_source()
    before_lock_create(env, lambda: env.seed_source(status=SourceStatus.DELETING))

    result = make_admission(env).accept_source_delete(SOURCE_ID)

    assert isinstance(result, Accepted)
    assert env.lock_body() is not None


def test_the_rollback_rereads_and_retries_when_the_lock_version_moved() -> None:
    env = make_env()
    env.seed_source()
    before_lock_create(env, lambda: env.seed_source(status=SourceStatus.DELETING))

    def bump_lock_version() -> None:
        env.jobs_repository.seed(LOCK_ID, env.lock_body() or {})

    env.jobs_repository.behavior.before(ops.DELETE, bump_lock_version, key=LOCK_ID)

    result = make_admission(env).accept_manual_crawl(SOURCE_ID)

    assert result == SourceDeleting()
    assert env.lock_body() is None


def test_the_rollback_leaves_a_lock_that_another_job_took() -> None:
    env = make_env()
    env.seed_source()
    before_lock_create(env, lambda: env.seed_source(status=SourceStatus.DELETING))

    def another_job_takes_the_lock() -> None:
        # 自分のロックが消えて、別のジョブのロックになった(通常は起きない。保守側の確認)。
        env.seed_lock(OTHER_JOB_ID, owner=OTHER_OWNER)

    env.jobs_repository.behavior.before(ops.DELETE, another_job_takes_the_lock, key=LOCK_ID)

    result = make_admission(env).accept_manual_crawl(SOURCE_ID)

    assert result == SourceDeleting()
    lock = env.lock_body()
    assert lock is not None
    assert (lock["owner"], lock["job_id"]) == (OTHER_OWNER, OTHER_JOB_ID)


def test_a_failure_after_the_lock_rolls_it_back_and_raises_the_original_error() -> None:
    env = make_env()
    env.seed_source()
    env.jobs_repository.behavior.inject(
        ops.CREATE, StoreUnavailableError("create_failed"), key=ADMITTED_JOB_ID, times=None
    )

    with pytest.raises(StoreUnavailableError) as raised:
        make_admission(env).accept_manual_crawl(SOURCE_ID)

    assert raised.value.reason == "create_failed"
    assert env.lock_body() is None
    assert env.wakeup.wait(0) is False


def test_an_unexpected_error_after_the_lock_also_rolls_it_back() -> None:
    env = make_env()
    env.seed_source()

    class Boom(Exception):
        pass

    env.jobs_repository.behavior.inject(ops.CREATE, Boom(), key=ADMITTED_JOB_ID)

    with pytest.raises(Boom):
        make_admission(env).accept_manual_crawl(SOURCE_ID)

    assert env.lock_body() is None


def test_a_failed_rollback_keeps_the_original_error_and_leaves_an_orphan_lock(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = make_env()
    env.seed_source()
    behavior = env.jobs_repository.behavior
    behavior.inject(
        ops.CREATE, StoreUnavailableError("create_failed"), key=ADMITTED_JOB_ID, times=None
    )
    behavior.inject(ops.DELETE, StoreUnavailableError("delete_failed"), key=LOCK_ID, times=None)

    with caplog.at_level(logging.WARNING), pytest.raises(StoreUnavailableError) as raised:
        make_admission(env).accept_manual_crawl(SOURCE_ID)

    assert raised.value.reason == "create_failed"
    assert env.lock_body() is not None  # 孤児ロック(回復かロック解放で消す)
    assert "orphan lock remains" in caplog.text
    assert "delete_failed" not in caplog.text  # 例外の中身は出さず、種類だけ


def test_a_rollback_that_fails_after_a_rejection_raises_and_leaves_the_orphan_lock() -> None:
    """設定を読み直したら `deleting` だったが、巻き戻しも失敗した: 503 で、孤児ロックが残る。"""
    env = make_env()
    env.seed_source()
    before_lock_create(env, lambda: env.seed_source(status=SourceStatus.DELETING))
    env.jobs_repository.behavior.inject(
        ops.DELETE, StoreUnavailableError("delete_failed"), key=LOCK_ID, times=None
    )

    with pytest.raises(StoreUnavailableError) as raised:
        make_admission(env).accept_manual_crawl(SOURCE_ID)

    assert raised.value.reason == "delete_failed"
    assert env.lock_body() is not None  # 回復かロック解放が消す
    assert env.job_ids() == []
    assert env.wakeup.wait(0) is False


def test_a_job_id_collision_rolls_the_lock_back_and_asks_for_a_retry() -> None:
    env = make_env()
    env.seed_source()
    env.seed_job(ADMITTED_JOB_ID, source_id="another-source")  # 同じ ID の別のジョブ

    with pytest.raises(StoreUnavailableError) as raised:
        make_admission(env).accept_manual_crawl(SOURCE_ID)

    assert raised.value.reason == "job_id_collision"
    assert env.lock_body() is None


# --- Store 層のリトライ ---


def test_a_transient_store_error_is_retried() -> None:
    env = make_env()
    env.seed_source()
    env.jobs_repository.behavior.inject(ops.FETCH, StoreUnavailableError("timeout"), times=2)

    assert isinstance(make_admission(env).accept_manual_crawl(SOURCE_ID), Accepted)


def test_a_transient_source_read_error_is_retried_at_both_reads() -> None:
    env = make_env()
    env.seed_source()
    env.sources_repository.behavior.inject(
        ops.FETCH, StoreUnavailableError("timeout"), key=SOURCE_ID, times=2
    )
    # 2 回目の読み取り(手順 4 の再確認)の前にも、一時的な失敗が入る。
    env.jobs_repository.behavior.before(
        ops.CREATE,
        lambda: env.sources_repository.behavior.inject(
            ops.FETCH, StoreUnavailableError("timeout"), key=SOURCE_ID, times=2
        ),
        key=ADMITTED_JOB_ID,
    )

    assert isinstance(make_admission(env).accept_manual_crawl(SOURCE_ID), Accepted)


def test_a_source_read_that_keeps_failing_raises_before_any_write() -> None:
    env = make_env()
    env.seed_source()
    env.sources_repository.behavior.inject(ops.FETCH, StoreUnavailableError("timeout"), times=None)

    with pytest.raises(StoreUnavailableError):
        make_admission(env).accept_manual_crawl(SOURCE_ID)

    assert env.jobs_repository.write_calls() == []


def test_a_lost_lock_create_response_is_recognized_as_our_own_lock() -> None:
    repository = LostResponseRepository()
    env = make_env(repository)
    env.seed_source()
    repository.lose_response_of(ops.CREATE)

    result = make_admission(env).accept_manual_crawl(SOURCE_ID)

    assert isinstance(result, Accepted)
    assert env.job_ids() == [ADMITTED_JOB_ID]


def test_a_lost_job_create_response_is_recognized_as_our_own_record() -> None:
    repository = LostResponseRepository()
    env = make_env(repository)
    env.seed_source()
    repository.behavior.before(
        ops.CREATE, lambda: repository.lose_response_of(ops.CREATE), key=ADMITTED_JOB_ID
    )

    result = make_admission(env).accept_manual_crawl(SOURCE_ID)

    assert isinstance(result, Accepted)
    assert env.lock_body() is not None


# --- 同時実行(テスト観点 #13: `create` の原子性。fake の割り込みフックと、実スレッド) ---


def test_when_a_second_admission_wins_the_lock_create_the_first_is_rejected() -> None:
    env = make_env()
    env.seed_source()
    results: list[AdmissionResult] = []
    competing = make_admission(env, random_token=lambda: "0000beef")

    def compete() -> None:
        results.append(competing.accept_manual_crawl(SOURCE_ID))

    # 先の受付が `create` に入る直前に、後の受付が最後まで進む。
    before_lock_create(env, compete)

    first = make_admission(env).accept_manual_crawl(SOURCE_ID)

    [second] = results
    assert isinstance(second, Accepted)
    assert isinstance(first, LockAlreadyHeld)
    assert first.existing_job.job_id == second.job.job_id
    assert first.existing_job.status is JobStatus.QUEUED
    assert env.job_ids() == [second.job.job_id]  # ジョブ記録は 1 つだけ


def test_only_one_of_many_concurrent_admissions_succeeds() -> None:
    env = make_env()
    env.seed_source()
    count = 8
    barrier = threading.Barrier(count, timeout=WAIT_TIMEOUT_SECONDS)
    results: list[AdmissionResult] = []
    results_lock = threading.Lock()

    def admit(index: int) -> None:
        admission = make_admission(env, random_token=lambda: f"0000{index:04x}")
        barrier.wait()
        result = admission.accept_manual_crawl(SOURCE_ID)
        with results_lock:
            results.append(result)

    threads = [threading.Thread(target=admit, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=WAIT_TIMEOUT_SECONDS)
        assert not thread.is_alive()

    accepted = [result for result in results if isinstance(result, Accepted)]
    rejected = [result for result in results if isinstance(result, LockAlreadyHeld)]
    assert len(accepted) == 1
    assert len(rejected) == count - 1
    assert env.job_ids() == [accepted[0].job.job_id]
    lock = env.lock_body()
    assert lock is not None
    assert lock["job_id"] == accepted[0].job.job_id
