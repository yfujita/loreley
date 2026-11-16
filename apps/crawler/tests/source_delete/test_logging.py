"""ログ・ジョブ記録・例外に、`connector_config`・認証情報・秘密が出ないこと(R11。完了条件 8)。

センチネル文字列を、設定の `connector_config`(認証情報の参照名)・想定外の例外のメッセージに置き、
成功・失敗のさまざまな経路を実行して、全ログ・ジョブ記録(`loreley-jobs` の全記録)・例外を検査する。
"""

import json
import logging
from collections.abc import Callable

import pytest

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.infrastructure.indexer_client import IndexerRejected, IndexerUnavailable
from loreley_crawler.sources import SourceSettingsInput, SourceStatus
from loreley_crawler.sources.records import build_body
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import DEFAULT_NOW
from tests.fakes.fake_indexer_client import DELETE_DOCUMENTS, DISCARD_DELETIONS
from tests.jobs.support import SOURCE_ID
from tests.source_delete.support import SourceDeleteEnv, source_delete_env

CONFIG = "SENTINEL_CONFIG_REF_9f8e"
SECRET = "SENTINEL_SECRET_77aa"
BODY = "SENTINEL_BODY_c1d2e3"
SENTINELS = (CONFIG, SECRET, BODY)


def use_sentinel_config(env: SourceDeleteEnv) -> None:
    env.jobs.sources_repository.seed(
        SOURCE_ID,
        build_body(
            SOURCE_ID,
            "file_system",
            SourceSettingsInput(
                {"root": "/data", "credentials_ref": CONFIG, "password": SECRET}, 100, 0.5, 3, None
            ),
            status=SourceStatus.ACTIVE,
            updated_at=DEFAULT_NOW,
        ),
    )


def dump_job_store(env: SourceDeleteEnv) -> str:
    repository = env.jobs.jobs_repository
    return json.dumps({i: repository.body_of(i) for i in repository.record_ids()})


def scenario_success(env: SourceDeleteEnv) -> None:
    pass


def scenario_unavailable(env: SourceDeleteEnv) -> None:
    env.indexer.behavior.inject(DELETE_DOCUMENTS, IndexerUnavailable("timeout"), times=None)


def scenario_rejected(env: SourceDeleteEnv) -> None:
    env.indexer.behavior.inject(DISCARD_DELETIONS, IndexerRejected(400, "invalid_request"))


def scenario_lock_not_owned(env: SourceDeleteEnv) -> None:
    env.indexer.behavior.inject(DELETE_DOCUMENTS, IndexerRejected(409, "lock_not_owned"))


def scenario_unexpected_client_error(env: SourceDeleteEnv) -> None:
    env.indexer.behavior.inject(DELETE_DOCUMENTS, RuntimeError(f"cannot read {BODY} {SECRET}"))


def scenario_unexpected_store_response(env: SourceDeleteEnv) -> None:
    env.jobs.jobs_repository.behavior.inject(
        ops.SCAN, StoreUnexpectedResponseError("http_400"), times=None
    )


def scenario_store_unavailable(env: SourceDeleteEnv) -> None:
    env.jobs.sources_repository.behavior.inject(
        ops.DELETE, StoreUnavailableError("timeout"), times=None
    )


def scenario_lock_lost(env: SourceDeleteEnv) -> None:
    env.indexer.behavior.before(
        DISCARD_DELETIONS, lambda: env.heartbeat.record_loss("lock_missing")
    )


def scenario_maintenance(env: SourceDeleteEnv) -> None:
    env.indexer.behavior.before(DISCARD_DELETIONS, lambda: env.jobs.seed_maintenance(True))


def scenario_finished_by_another_writer(env: SourceDeleteEnv) -> None:
    def release() -> None:
        env.jobs.jobs_repository.seed(
            env.record.job_id,
            {**env.jobs.job_body(), "status": "failed", "failure_reason": "lock_released"},
        )

    env.indexer.behavior.before(DISCARD_DELETIONS, release)


@pytest.mark.parametrize(
    "scenario",
    [
        scenario_success,
        scenario_unavailable,
        scenario_rejected,
        scenario_lock_not_owned,
        scenario_unexpected_client_error,
        scenario_unexpected_store_response,
        scenario_store_unavailable,
        scenario_lock_lost,
        scenario_maintenance,
        scenario_finished_by_another_writer,
    ],
)
def test_no_log_job_record_or_exception_contains_a_sentinel(
    scenario: Callable[[SourceDeleteEnv], None], caplog: pytest.LogCaptureFixture
) -> None:
    with source_delete_env() as env:
        use_sentinel_config(env)
        scenario(env)

        with caplog.at_level(logging.DEBUG):
            try:
                env.run()
            except Exception as error:
                assert not any(s in f"{error!s}{error!r}" for s in SENTINELS)

        logs = "\n".join(f"{record.getMessage()} {record.exc_text}" for record in caplog.records)
        assert caplog.records  # 開始・終了の記録がある(検査が空振りでない)
        for sentinel in SENTINELS:
            assert sentinel not in logs
            assert sentinel not in dump_job_store(env)
            assert sentinel not in repr(env.record) + repr(env.context.record)
