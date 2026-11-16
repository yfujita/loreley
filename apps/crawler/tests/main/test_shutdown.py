"""停止順(CM-U-4。module 5.7)。

停止は Scheduler → Job Runner の順に要求し、join にはタイムアウトを付ける。実行中のジョブの完了は
待たず、終了処理(最終状態の記録・ロックの解放)もしない。次回の起動時の回復が
`failed`(`crawler_restart`)にする。
"""

import threading
import time
from datetime import timedelta

import pytest

from loreley_crawler import main as main_module
from loreley_crawler.jobs import Accepted, JobStatus
from loreley_crawler.main import Components
from loreley_crawler.sources import SourceSettingsInput, SourceStatus
from loreley_crawler.sources.records import build_body
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.fake_connector import CREATE, FakeConnectorType
from tests.fakes.fake_indexer_client import DISCARD_DELETIONS
from tests.main.support import (
    WAIT_TIMEOUT_SECONDS,
    Fakes,
    make_components,
    record_calls,
    started_threads,
)

SOURCE_ID = "docs"
# 止まっているスレッド(Job Runner)を待つ上限。Scheduler など、止まるスレッドが十分に間に合う長さ。
STOP_JOIN_SECONDS = 1.0


def stop(components: Components) -> tuple[str, ...]:
    return main_module.stop_components(components, join_timeout_seconds=STOP_JOIN_SECONDS)


def seed_source(fakes: Fakes) -> None:
    settings = SourceSettingsInput(
        connector_config={"root": "/data"},
        ttl=2_592_000,
        ratio_threshold=0.3,
        min_delete_count=10,
        schedule_cron=None,
    )
    body = build_body(
        SOURCE_ID, "file_system", settings, status=SourceStatus.ACTIVE, updated_at=DEFAULT_NOW
    )
    fakes.sources.seed(SOURCE_ID, body)


class RunningJob:
    """実行対象を、列挙の手前(`running` になった後)で止めておく。"""

    def __init__(self) -> None:
        self.inside_job = threading.Event()
        self.release = threading.Event()
        self.connector_type = FakeConnectorType()
        self.connector_type.behavior.before(CREATE, self._block)

    def _block(self) -> None:
        self.inside_job.set()
        assert self.release.wait(WAIT_TIMEOUT_SECONDS)


def start_a_running_job(job: RunningJob, fakes: Fakes):
    seed_source(fakes)
    components, _ = make_components(fakes, connector_type=job.connector_type)
    main_module.start_components(components)
    accepted = components.api_dependencies.job_admission.accept_manual_crawl(SOURCE_ID)
    assert isinstance(accepted, Accepted)
    assert job.inside_job.wait(WAIT_TIMEOUT_SECONDS)
    return components, accepted.job.job_id


def test_stopping_does_not_wait_for_the_running_job_and_does_not_finish_it() -> None:
    fakes = Fakes()
    job = RunningJob()
    components, job_id = start_a_running_job(job, fakes)
    try:
        started_at = time.monotonic()
        not_stopped = main_module.stop_components(
            components, join_timeout_seconds=STOP_JOIN_SECONDS
        )
        elapsed_seconds = time.monotonic() - started_at

        # join はタイムアウトで戻り、止まっていないスレッドが分かる。
        assert not_stopped == ("job-runner",)
        assert elapsed_seconds < WAIT_TIMEOUT_SECONDS / 2  # ジョブの完了(ゲートの解放)を待たない
        # 終了処理をしていない: ジョブは `running` のまま、ロックも残り、終了通知もない。
        assert fakes.jobs.body_of(job_id)["status"] == JobStatus.RUNNING.value
        assert "finished_at" not in fakes.jobs.body_of(job_id)
        assert fakes.jobs.body_of(f"lock-{SOURCE_ID}") is not None
        assert fakes.jobs.body_of(f"lock-{SOURCE_ID}")["job_id"] == job_id
        assert not [event for event in fakes.indexer.events if event.startswith("finish")]
    finally:
        job.release.set()
        components.runner.join(WAIT_TIMEOUT_SECONDS)


def test_the_next_startup_recovery_fails_the_interrupted_job_and_releases_its_lock() -> None:
    fakes = Fakes()
    job = RunningJob()
    components, job_id = start_a_running_job(job, fakes)
    try:
        stop(components)

        # 別のプロセスとしての再起動(同じ owner・同じ Store)。
        restarted, _ = make_components(fakes)
        report = restarted.recovery.run()

        assert report.failed_job_ids == (job_id,)
        assert fakes.jobs.body_of(job_id)["status"] == JobStatus.FAILED.value
        assert fakes.jobs.body_of(job_id)["failure_reason"] == "crawler_restart"
        assert fakes.jobs.body_of(f"lock-{SOURCE_ID}") is None
    finally:
        job.release.set()
        components.runner.join(WAIT_TIMEOUT_SECONDS)


def test_the_threads_exit_by_themselves_once_the_running_job_returns() -> None:
    fakes = Fakes()
    job = RunningJob()
    components, _ = start_a_running_job(job, fakes)
    stop(components)

    job.release.set()

    assert components.runner.join(WAIT_TIMEOUT_SECONDS) is True
    assert not {"job-runner", "scheduler"} & started_threads()


def test_an_idle_stop_returns_at_once_with_nothing_left_running() -> None:
    components, _ = make_components()
    main_module.start_components(components)

    assert main_module.stop_components(components, join_timeout_seconds=WAIT_TIMEOUT_SECONDS) == ()

    assert not {"job-runner", "scheduler"} & started_threads()


def test_stopping_components_that_were_never_started_is_harmless() -> None:
    components, _ = make_components()

    assert main_module.stop_components(components) == ()


def test_the_scheduler_is_asked_to_stop_before_the_job_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    record_calls(monkeypatch, main_module.Scheduler, "request_stop", events, "scheduler")
    record_calls(monkeypatch, main_module.JobRunner, "request_stop", events, "runner")
    components, _ = make_components()

    main_module.stop_components(components)

    assert events == ["scheduler", "runner"]


def test_a_thread_that_did_not_stop_is_warned_about_without_a_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fakes = Fakes()
    job = RunningJob()
    components, _ = start_a_running_job(job, fakes)
    try:
        with caplog.at_level("WARNING", logger=main_module.__name__):
            stop(components)
    finally:
        job.release.set()
        components.runner.join(WAIT_TIMEOUT_SECONDS)

    assert [record.getMessage() for record in caplog.records] == [
        "a thread did not stop in time and is left to the process exit: name=job-runner"
    ]


def test_an_interrupted_source_delete_is_recovered_and_then_completed_by_a_new_delete() -> None:
    """`running` の `source_delete` を残して停止 → 回復(`crawler_restart`)→ 再度の受付で完了。"""
    fakes = Fakes()
    seed_source(fakes)
    inside_job, release = threading.Event(), threading.Event()

    def block() -> None:
        inside_job.set()
        assert release.wait(WAIT_TIMEOUT_SECONDS)

    fakes.indexer.behavior.before(DISCARD_DELETIONS, block)  # 最初の 1 回だけ止める
    components, _ = make_components(fakes)
    main_module.start_components(components)
    accepted = components.api_dependencies.job_admission.accept_source_delete(SOURCE_ID)
    assert isinstance(accepted, Accepted)
    assert inside_job.wait(WAIT_TIMEOUT_SECONDS)
    try:
        assert stop(components) == ("job-runner",)
        interrupted_id = accepted.job.job_id
        assert fakes.jobs.body_of(interrupted_id)["status"] == JobStatus.RUNNING.value

        # 再起動(別の組み立て)。回復が `failed(crawler_restart)` にしてロックを消す。
        clock = FixedClock(DEFAULT_NOW + timedelta(seconds=60))
        restarted, _ = make_components(fakes, clock=clock)
        assert restarted.recovery.run().failed_job_ids == (interrupted_id,)
        assert fakes.jobs.body_of(interrupted_id)["failure_reason"] == "crawler_restart"
        # `deleting` のソースにも、ソース削除を受け付けられる。
        second = restarted.api_dependencies.job_admission.accept_source_delete(SOURCE_ID)
        assert isinstance(second, Accepted)
        assert restarted.runner.run_next() is True

        assert fakes.jobs.body_of(second.job.job_id)["status"] == JobStatus.SUCCEEDED.value
        assert fakes.sources.body_of(SOURCE_ID) is None
        assert fakes.jobs.body_of(f"lock-{SOURCE_ID}") is None
    finally:
        release.set()
        components.runner.join(WAIT_TIMEOUT_SECONDS)
