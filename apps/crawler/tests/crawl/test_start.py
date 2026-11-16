"""実行開始(architecture 4.5 の手順 6〜8・3.2。テスト観点 #35)。

`queued` -> `running`、設定の 1 回読み取り、設定スナップショット(6 項目)と
`settings_source_updated_at` の追記、メンテナンスの再確認、`validate_config`・`create`。
設定の読み取りの失敗(`config_invalid`)は、開始通知の前に `running` から `failed` になる。
"""

from typing import Any

import pytest

from loreley_crawler.common.errors import StoreUnexpectedResponseError
from loreley_crawler.common.timestamps import format_instant
from loreley_crawler.connectors.interface import ConnectorError, ErrorCategory
from loreley_crawler.crawl.executor import FailureRecorded, ReadyToFinish
from loreley_crawler.crawl.start import (
    CONNECTOR_TYPE_UNREGISTERED_DETAIL,
    SOURCE_DELETING_DETAIL,
    SOURCE_NOT_FOUND_DETAIL,
)
from loreley_crawler.jobs import (
    SETTINGS_SNAPSHOT_KEYS,
    JobNotStartable,
    JobStatus,
    MaintenanceDetected,
)
from loreley_crawler.sources import SourceSettingsInput, SourceStatus
from loreley_crawler.sources.records import build_body
from tests.crawl.support import CrawlEnv, crawl_env
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import DEFAULT_NOW
from tests.fakes.fake_connector import CREATE, VALIDATE_CONFIG
from tests.jobs.support import JOB_ID, SOURCE_ID


def assert_failed_before_start_notice(
    env: CrawlEnv, result: object, reason: str, detail: str | None = None
) -> dict[str, Any]:
    assert isinstance(result, FailureRecorded)
    assert result.recorded is True
    body = env.job_body()
    assert body["status"] == "failed"
    assert body["failure_reason"] == reason
    if detail is not None:
        assert body["failure_detail"] == detail
    assert env.indexer.calls == []  # 開始通知を送らない
    return body


def test_a_crawl_reaches_the_finish_notice_with_the_job_still_running(env: CrawlEnv) -> None:
    result = env.run()

    assert isinstance(result, ReadyToFinish)
    # 最終状態と終了通知は P6b。ここでは `running` のまま。
    assert env.job_body()["status"] == "running"


def test_the_snapshot_has_exactly_the_six_fields_and_the_source_updated_at(env: CrawlEnv) -> None:
    env.run()

    body = env.job_body()
    assert set(body["settings_snapshot"]) == SETTINGS_SNAPSHOT_KEYS
    assert body["settings_snapshot"] == {
        "crawl_started_at": format_instant(DEFAULT_NOW),
        "ttl": 2_592_000,
        "ratio_threshold": 0.3,
        "min_delete_count": 10,
        "force_delete": False,
        "rewrite_mode": False,
    }
    assert body["started_at"] == body["settings_snapshot"]["crawl_started_at"]
    # 読んだ設定の更新時刻は、snapshot の外の最上位項目(CA-P-51)。
    assert body["settings_source_updated_at"] == format_instant(DEFAULT_NOW)


@pytest.mark.parametrize(
    ("force_delete", "rewrite_mode"), [(True, False), (False, True), (True, True)]
)
def test_force_delete_and_rewrite_mode_come_from_the_job_record_without_being_swapped(
    force_delete: bool, rewrite_mode: bool
) -> None:
    fields = {"force_delete": force_delete, "rewrite_mode": rewrite_mode}
    with crawl_env(job_fields=fields) as env:
        env.run()

        snapshot = env.job_body()["settings_snapshot"]
        assert (snapshot["force_delete"], snapshot["rewrite_mode"]) == (force_delete, rewrite_mode)
        sent = env.indexer.calls_of("start_crawl")[0].arguments
        assert (sent["force_delete"], sent["rewrite_mode"]) == (force_delete, rewrite_mode)


@pytest.mark.parametrize("field", ["force_delete", "rewrite_mode"])
@pytest.mark.parametrize("value", ["true", 1, None])
def test_a_malformed_flag_in_the_job_record_is_an_unexpected_response(
    field: str, value: object
) -> None:
    with crawl_env(job_fields={field: value}) as env, pytest.raises(StoreUnexpectedResponseError):
        env.run()


def test_the_connector_config_is_never_written_to_the_job_record() -> None:
    with crawl_env() as env:
        env.jobs.sources_repository.seed(
            SOURCE_ID,
            build_body(
                SOURCE_ID,
                "file_system",
                SourceSettingsInput({"root": "SENTINEL_CONFIG_VALUE"}, 100, 0.5, 3, None),
                status=SourceStatus.ACTIVE,
                updated_at=DEFAULT_NOW,
            ),
        )

        env.run()

        assert "SENTINEL_CONFIG_VALUE" not in repr(env.job_body())
        assert env.connector_type.created == [(SOURCE_ID, {"root": "SENTINEL_CONFIG_VALUE"})]
        assert "connector_config" not in env.job_body()


def test_settings_are_read_once_and_later_updates_do_not_reach_the_job() -> None:  # 観点 #35
    with crawl_env() as env:
        updated_body = build_body(
            SOURCE_ID,
            "file_system",
            SourceSettingsInput({"root": "/changed"}, 999, 0.9, 99, None),
            status=SourceStatus.ACTIVE,
            updated_at=DEFAULT_NOW,
        )
        # 設定の読み取りより後・`create` の前に、別の書き手が設定を更新する。
        env.connector_type.behavior.before(
            CREATE, lambda: env.jobs.sources_repository.seed(SOURCE_ID, updated_body)
        )

        result = env.run()

        assert isinstance(result, ReadyToFinish)
        assert env.connector_type.created == [(SOURCE_ID, {"root": "/data"})]
        assert env.indexer.calls_of("start_crawl")[0].arguments["ttl"] == 2_592_000
        assert env.job_body()["settings_snapshot"]["ttl"] == 2_592_000
        reads = [
            call
            for call in env.jobs.sources_repository.behavior.calls_of(ops.FETCH)
            if call.key == SOURCE_ID
        ]
        assert len(reads) == 1


def test_a_missing_source_fails_with_config_invalid_before_the_start_notice() -> None:
    with crawl_env(seed_source=False) as env:
        body = assert_failed_before_start_notice(
            env, env.run(), "config_invalid", SOURCE_NOT_FOUND_DETAIL
        )

        assert "settings_snapshot" not in body
        assert env.connector_type.created == []


def test_a_deleting_source_fails_with_config_invalid() -> None:
    with crawl_env(seed_source=False) as env:
        env.jobs.seed_source(status=SourceStatus.DELETING)

        assert_failed_before_start_notice(env, env.run(), "config_invalid", SOURCE_DELETING_DETAIL)


def test_a_malformed_deleting_source_is_reported_as_deleting() -> None:
    with crawl_env(seed_source=False) as env:
        env.jobs.seed_malformed_source(status="deleting")

        assert_failed_before_start_notice(env, env.run(), "config_invalid", SOURCE_DELETING_DETAIL)


@pytest.mark.parametrize(
    "body",
    [
        {"status": "active"},  # 値の欠落
        {"status": "active", "connector_type": "file_system", "ttl": "100"},  # 型違い
    ],
)
def test_a_malformed_source_fails_with_config_invalid_naming_only_the_fields(
    body: dict[str, Any],
) -> None:
    with crawl_env(seed_source=False) as env:
        env.jobs.seed_malformed_source(**body)

        failure = assert_failed_before_start_notice(env, env.run(), "config_invalid")

        assert failure["failure_detail"].startswith("データソースの設定の値が欠けている")
        assert "ttl" in failure["failure_detail"]
        assert "100" not in failure["failure_detail"]


def test_an_unregistered_connector_type_fails_with_config_invalid() -> None:
    with crawl_env(seed_source=False) as env:
        env.jobs.sources_repository.seed(
            SOURCE_ID,
            build_body(
                SOURCE_ID,
                "no_such_type",
                SourceSettingsInput({}, 100, 0.5, 3, None),
                status=SourceStatus.ACTIVE,
                updated_at=DEFAULT_NOW,
            ),
        )

        assert_failed_before_start_notice(
            env, env.run(), "config_invalid", CONNECTOR_TYPE_UNREGISTERED_DETAIL
        )


def test_a_failing_validate_config_fails_with_config_invalid(env: CrawlEnv) -> None:
    error = ConnectorError.of(ErrorCategory.CONFIG_INVALID, "root が不正")
    env.connector_type.behavior.inject(VALIDATE_CONFIG, error)

    assert_failed_before_start_notice(
        env, env.run(), "config_invalid", "config_invalid: root が不正"
    )
    assert env.connector_type.created == []


def test_a_permanent_create_failure_fails_with_enumeration_failed_without_retry(
    env: CrawlEnv,
) -> None:
    error = ConnectorError.of(ErrorCategory.SOURCE_ACCESS_DENIED, "権限がない")
    env.connector_type.behavior.inject(CREATE, error, times=None)

    assert_failed_before_start_notice(
        env, env.run(), "enumeration_failed", "source_access_denied: 権限がない"
    )
    assert len(env.connector_type.created) == 1
    assert env.sleeps == []


def test_a_transient_create_failure_is_retried(env: CrawlEnv) -> None:
    error = ConnectorError.of(ErrorCategory.SOURCE_UNREACHABLE, "届かない")
    env.connector_type.behavior.inject(CREATE, error, times=1)

    result = env.run()

    assert isinstance(result, ReadyToFinish)
    assert len(env.connector_type.created) == 2
    assert env.sleeps == [1.0]


def test_a_transient_create_failure_that_persists_fails_after_three_attempts(
    env: CrawlEnv,
) -> None:
    error = ConnectorError.of(ErrorCategory.SOURCE_UNREACHABLE, "届かない")
    env.connector_type.behavior.inject(CREATE, error, times=None)

    assert_failed_before_start_notice(
        env, env.run(), "enumeration_failed", "source_unreachable: 届かない"
    )
    assert len(env.connector_type.created) == 3
    assert env.sleeps == [1.0, 2.0]


def test_the_maintenance_flag_is_rechecked_after_the_snapshot_and_before_create(
    env: CrawlEnv,
) -> None:
    env.jobs.seed_maintenance(True)

    with pytest.raises(MaintenanceDetected):
        env.run()

    assert "settings_snapshot" in env.job_body()  # 手順 6 の追記の後に再確認する(手順 7)
    assert env.connector_type.created == []
    assert env.indexer.calls == []


def test_a_malformed_maintenance_flag_counts_as_raised(env: CrawlEnv) -> None:  # fail-closed
    env.jobs.seed_maintenance("yes")

    with pytest.raises(MaintenanceDetected):
        env.run()


def test_losing_the_start_race_to_a_cancellation_propagates_job_not_startable(
    env: CrawlEnv,
) -> None:
    env.jobs.seed_job(JOB_ID, status=JobStatus.CANCELLED)  # 取り消しが先に勝った

    with pytest.raises(JobNotStartable):
        env.run()

    assert env.indexer.calls == []
    assert env.connector_type.created == []


def test_the_maintenance_recheck_comes_before_the_connector_type_is_resolved() -> None:
    # 手順 7(メンテナンスの再確認)は、手順 8(`validate_config`・`create`)の前。
    with crawl_env(seed_source=False) as env:
        env.jobs.sources_repository.seed(
            SOURCE_ID,
            build_body(
                SOURCE_ID,
                "no_such_type",
                SourceSettingsInput({}, 100, 0.5, 3, None),
                status=SourceStatus.ACTIVE,
                updated_at=DEFAULT_NOW,
            ),
        )
        env.jobs.seed_maintenance(True)

        with pytest.raises(MaintenanceDetected):
            env.run()
