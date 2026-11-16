"""Store 層の異常(順 0・3・5)の扱い(architecture 4.8・8.1。テスト観点 #33 の順 3・5)。

- `StoreUnavailableError`・`StoreWriteFailedError`: リトライを尽くして
  `failed`(`store_unavailable`)。後続の削除は行わない
- `StoreUnexpectedResponseError`: リトライせず `failed`(`internal_error`)
- 順 5 は `status=deleting` のときだけ設定を削除する
"""

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from tests.fakes import in_memory_repository as ops
from tests.jobs.support import SOURCE_ID
from tests.source_delete.support import SKIP_ID, source_delete_env

STEP_4 = "indexer:delete_deletion_records"


def test_a_persistent_failure_of_step_0_fails_before_any_deletion() -> None:
    with source_delete_env() as env:
        env.jobs.sources_repository.behavior.inject(
            ops.FETCH, StoreUnavailableError("timeout"), times=None
        )

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "store_unavailable")
        assert body["failure_detail"] == "Store 層の操作に失敗した(timeout)"
        assert env.destructive_events() == []


def test_an_unexpected_store_response_in_step_0_is_not_retried() -> None:
    with source_delete_env() as env:
        env.jobs.sources_repository.behavior.inject(
            ops.FETCH, StoreUnexpectedResponseError("http_400"), times=None
        )

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "internal_error")
        assert body["failure_detail"] == "Store 層の想定外の応答(http_400)"
        assert len(env.jobs.sources_repository.behavior.calls_of(ops.FETCH)) == 1
        assert env.destructive_events() == []


def test_a_transient_failure_of_the_scan_in_step_3_is_retried() -> None:
    with source_delete_env() as env:
        env.seed_document_records()
        env.jobs.jobs_repository.behavior.inject(ops.SCAN, StoreUnavailableError("t"), times=2)

        body = env.run()

        assert body["status"] == "succeeded"
        assert SKIP_ID not in env.jobs.jobs_repository.record_ids()


def test_a_persistent_failure_of_the_scan_in_step_3_stops_step_4_and_5() -> None:
    with source_delete_env() as env:
        env.seed_document_records()
        env.jobs.jobs_repository.behavior.inject(
            ops.SCAN, StoreUnavailableError("timeout"), times=None
        )

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "store_unavailable")
        assert STEP_4 not in env.events
        assert "sources:delete:docs" not in env.events
        source = env.source_body()
        assert source is not None and source["status"] == "deleting"


def test_a_partial_bulk_delete_failure_that_persists_fails_and_stops_later_steps() -> None:
    with source_delete_env() as env:
        env.seed_document_records()
        env.jobs.jobs_repository.fail_bulk_delete_of([SKIP_ID], times=None)

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "store_unavailable")
        assert body["failure_detail"] == "Store 層の操作に失敗した(bulk_delete_incomplete)"
        assert SKIP_ID in env.jobs.jobs_repository.record_ids()
        assert STEP_4 not in env.events
        assert "sources:delete:docs" not in env.events


def test_a_partial_bulk_delete_failure_is_resent_for_the_failed_ids_only() -> None:
    with source_delete_env() as env:
        env.seed_document_records()
        env.jobs.jobs_repository.fail_bulk_delete_of([SKIP_ID], times=1)

        body = env.run()

        assert body["status"] == "succeeded"
        assert SKIP_ID not in env.jobs.jobs_repository.record_ids()


def test_an_unexpected_store_response_in_step_3_is_not_retried() -> None:
    with source_delete_env() as env:
        env.seed_document_records()
        env.jobs.jobs_repository.behavior.inject(
            ops.SCAN, StoreUnexpectedResponseError("non_unique_sort"), times=None
        )

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "internal_error")
        assert len(env.jobs.jobs_repository.behavior.calls_of(ops.SCAN)) == 1
        assert STEP_4 not in env.events


def test_a_persistent_failure_of_step_5_leaves_the_config_deleting() -> None:
    with source_delete_env() as env:
        env.jobs.sources_repository.behavior.inject(
            ops.DELETE, StoreUnavailableError("timeout"), times=None
        )

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "store_unavailable")
        source = env.source_body()
        assert source is not None and source["status"] == "deleting"
        assert env.indexer_calls().count(STEP_4.removeprefix("indexer:")) == 1


def test_a_transient_failure_of_step_5_is_retried() -> None:
    with source_delete_env() as env:
        env.jobs.sources_repository.behavior.inject(
            ops.DELETE, StoreUnavailableError("timeout"), times=2
        )

        body = env.run()

        assert body["status"] == "succeeded"
        assert env.source_body() is None


def test_step_5_does_not_delete_a_config_that_is_not_deleting() -> None:
    """順 0 の後に設定が作り直された(`active`)。別の設定を消さず、`failed`(`internal_error`)。"""
    with source_delete_env() as env:
        env.seed_document_records()
        env.jobs.jobs_repository.behavior.before(ops.SCAN, env.jobs.seed_source)

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "internal_error")
        assert body["failure_detail"] == "設定が deleting でないため、設定を削除しなかった"
        assert "sources:delete:docs" not in env.events
        source = env.source_body()
        assert source is not None and source["status"] == "active"
        assert source["source_id"] == SOURCE_ID


def test_an_unexpected_store_response_in_step_5_is_not_retried() -> None:
    with source_delete_env() as env:
        env.jobs.sources_repository.behavior.inject(
            ops.DELETE, StoreUnexpectedResponseError("http_500"), times=None
        )

        body = env.run()

        assert (body["status"], body["failure_reason"]) == ("failed", "internal_error")
        assert len(env.jobs.sources_repository.behavior.calls_of(ops.DELETE)) == 1


def test_a_job_record_with_a_malformed_owner_fails_before_any_write() -> None:
    with source_delete_env() as env:
        env.jobs.jobs_repository.seed(env.record.job_id, {**env.jobs.job_body(), "owner": 5})
        record = env.jobs.job_store.fetch(env.record.job_id)
        assert record is not None

        env.executor(record, env.context)

        body = env.jobs.job_body()
        assert (body["status"], body["failure_reason"]) == ("failed", "internal_error")
        assert env.destructive_events() == []
