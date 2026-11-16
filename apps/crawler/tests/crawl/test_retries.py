"""リトライ・スキップ・エラー別の扱い(architecture 6.1・6.2・7.8。テスト観点 #9・#10・#11)。

最大 3 回、バックオフ(1 秒・2 秒)。待ちは記録だけして実際には待たない(`env.sleeps`)。
"""

import pytest

from loreley_crawler.connectors.interface import ConnectorError, ErrorCategory, ErrorScope
from loreley_crawler.crawl.executor import FailureRecorded, ReadyToFinish
from loreley_crawler.infrastructure.indexer_client import (
    MALFORMED_RESPONSE,
    BatchResults,
    Change,
    DocumentFailed,
    DocumentRegistered,
    FailureType,
    IndexerRejected,
    IndexerUnavailable,
    LastSeenEntry,
    LastSeenResult,
    LastSeenResults,
)
from loreley_crawler.jobs import OwnershipLost
from tests.crawl.support import CrawlEnv, crawl_env, document_id_of
from tests.fakes.fake_connector import FETCH
from tests.fakes.fake_indexer_client import REGISTER_DOCUMENTS, REPORT_LAST_SEEN


def fetch_error(category: ErrorCategory) -> ConnectorError:
    if category is ErrorCategory.CONNECTOR_INTERNAL_ERROR:
        return ConnectorError.of(category, "failure", scope=ErrorScope.DOCUMENT)
    return ConnectorError.of(category, "failure")


def registered_names(env: CrawlEnv) -> list[list[str]]:
    return [
        [d.external_id for d in call.arguments["documents"]]
        for call in env.indexer.calls_of(REGISTER_DOCUMENTS)
    ]


def assert_failed(env: CrawlEnv, result: object, reason: str) -> None:
    assert isinstance(result, FailureRecorded)
    assert env.job_body()["status"] == "failed"
    assert env.job_body()["failure_reason"] == reason


# --- 取得のリトライとスキップ ---


@pytest.mark.parametrize(
    "category", [ErrorCategory.FETCH_TRANSIENT, ErrorCategory.CONNECTOR_INTERNAL_ERROR]
)
def test_a_transient_or_unknown_fetch_failure_is_retried_until_it_succeeds(
    category: ErrorCategory,
) -> None:
    with crawl_env(files={"a": b"x"}) as env:
        env.connector.behavior.inject(FETCH, fetch_error(category), key="a", times=2)

        result = env.run()

        assert isinstance(result, ReadyToFinish)
        assert len(env.connector.fetch_calls) == 3
        assert env.sleeps == [1.0, 2.0]
        assert env.skip_record_ids() == []


@pytest.mark.parametrize(
    "category", [ErrorCategory.FETCH_TRANSIENT, ErrorCategory.CONNECTOR_INTERNAL_ERROR]
)
def test_a_fetch_failure_that_persists_skips_the_document_after_three_attempts(
    category: ErrorCategory,
) -> None:  # 観点 #9
    with crawl_env(files={"a": b"x"}) as env:
        env.connector.behavior.inject(FETCH, fetch_error(category), key="a", times=None)

        result = env.run()

        assert isinstance(result, ReadyToFinish)
        assert len(env.connector.fetch_calls) == 3
        assert env.sleeps == [1.0, 2.0]
        (record_id,) = env.skip_record_ids()
        record = env.jobs.jobs_repository.body_of(record_id)
        assert record is not None
        assert record["stage"] == "fetch"
        assert record["attempts"] == 3
        assert record["reason"].startswith(category.value)
        assert record["consecutive_skips"] == 1
        assert result.run.tally.skipped_document_ids == (document_id_of("a"),)


@pytest.mark.parametrize(
    "category", [ErrorCategory.FETCH_NOT_FOUND, ErrorCategory.FETCH_PERMISSION_DENIED]
)
def test_a_permanent_fetch_failure_is_skipped_without_retry(category: ErrorCategory) -> None:
    with crawl_env(files={"a": b"x"}) as env:
        env.connector.behavior.inject(FETCH, fetch_error(category), key="a", times=None)

        result = env.run()

        assert isinstance(result, ReadyToFinish)
        assert len(env.connector.fetch_calls) == 1
        assert env.sleeps == []
        assert len(env.skip_record_ids()) == 1
        assert (
            env.indexer.calls_of(REGISTER_DOCUMENTS) == []
        )  # 取得に失敗した文書はバッチに入らない


def test_a_skipped_document_does_not_stop_the_others() -> None:
    with crawl_env(files={"a": b"1", "b": b"2", "c": b"3"}) as env:
        env.connector.behavior.inject(
            FETCH, fetch_error(ErrorCategory.FETCH_NOT_FOUND), key="b", times=None
        )

        env.run()

        assert registered_names(env) == [["a", "c"]]


def test_an_oversize_failure_from_fetch_is_not_retried() -> None:
    with crawl_env(files={"a": b"x"}) as env:
        env.connector.behavior.inject(
            FETCH, fetch_error(ErrorCategory.OVERSIZE), key="a", times=None
        )

        result = env.run()

        assert isinstance(result, ReadyToFinish)
        assert len(env.connector.fetch_calls) == 1
        assert env.skip_record_ids() == []
        assert len(env.oversize_record_ids()) == 1


@pytest.mark.parametrize(
    "category", [ErrorCategory.SOURCE_UNREACHABLE, ErrorCategory.EXTERNAL_ID_COLLISION]
)
def test_a_category_that_fetch_must_not_return_fails_the_job(category: ErrorCategory) -> None:
    with crawl_env(files={"a": b"x"}) as env:
        env.connector.behavior.inject(FETCH, fetch_error(category), key="a", times=None)

        assert_failed(env, env.run(), "internal_error")
        assert len(env.connector.fetch_calls) == 1  # 契約違反はリトライしない


# --- リクエスト全体の失敗(観点 #11) ---


@pytest.mark.parametrize("reason", ["http_500", "http_503", "connection_error", "timeout"])
def test_an_unavailable_indexer_on_a_batch_is_retried_with_the_same_batch(reason: str) -> None:
    with crawl_env(files={"a": b"1", "b": b"2"}) as env:
        env.indexer.behavior.inject(REGISTER_DOCUMENTS, IndexerUnavailable(reason), times=2)

        result = env.run()

        assert isinstance(result, ReadyToFinish)
        assert registered_names(env) == [["a", "b"]] * 3
        assert env.sleeps == [1.0, 2.0]
        assert env.job_body()["registration"]["created_count"] == 2


@pytest.mark.parametrize("reason", ["http_500", "http_503", "connection_error", "timeout"])
def test_an_indexer_that_stays_unavailable_fails_the_job_instead_of_skipping(reason: str) -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(REGISTER_DOCUMENTS, IndexerUnavailable(reason), times=None)

        assert_failed(env, env.run(), "indexer_unavailable")

        assert len(registered_names(env)) == 3
        assert env.skip_record_ids() == []


@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [
        (400, "invalid_request"),
        (409, "crawl_not_started"),
        (409, "crawl_source_mismatch"),
        (409, "crawl_started_at_mismatch"),
        (409, "crawl_already_closed"),
        (409, "crawl_finished"),
        (404, "not_found"),
        (200, MALFORMED_RESPONSE),
    ],
)
@pytest.mark.parametrize("operation", [REPORT_LAST_SEEN, REGISTER_DOCUMENTS])
def test_a_rejected_request_is_not_retried_and_fails_the_job(
    operation: str, status_code: int, error_code: str
) -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(operation, IndexerRejected(status_code, error_code))

        assert_failed(env, env.run(), "indexer_rejected")

        assert len(env.indexer.calls_of(operation)) == 1
        assert env.sleeps == []
        assert len(env.indexer.calls_of("start_crawl")) == 1  # 開始通知は送り直さない


def test_last_seen_that_stays_unavailable_fails_the_job() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(REPORT_LAST_SEEN, IndexerUnavailable("http_503"), times=None)

        assert_failed(env, env.run(), "indexer_unavailable")

        assert len(env.indexer.calls_of(REPORT_LAST_SEEN)) == 3
        assert env.connector.fetch_calls == []  # last-seen は取得より前


# --- 文書単位の失敗 ---


def test_a_rejected_document_alone_is_resent_and_skipped_after_three_attempts() -> None:  # 観点 #9
    with crawl_env(files={"a": b"1", "b": b"2", "c": b"3"}) as env:
        env.indexer.registration_failures["b"] = FailureType.DOCUMENT_REJECTED

        result = env.run()

        assert isinstance(result, ReadyToFinish)
        assert registered_names(env) == [["a", "b", "c"], ["b"], ["b"]]
        assert env.sleeps == [1.0, 2.0]
        (record_id,) = env.skip_record_ids()
        record = env.jobs.jobs_repository.body_of(record_id)
        assert record is not None
        assert (record["stage"], record["attempts"]) == ("index", 3)
        assert record["reason"].startswith("document_rejected")
        assert result.run.tally.skipped_document_ids == (document_id_of("b"),)
        registration = env.job_body()["registration"]
        assert (registration["created_count"], registration["skipped_count"]) == (2, 1)


def test_a_rejected_document_that_is_accepted_on_resend_is_not_skipped() -> None:
    with crawl_env(files={"a": b"1", "b": b"2"}) as env:
        env.indexer.behavior.inject(
            REGISTER_DOCUMENTS,
            BatchResults(
                (
                    DocumentRegistered("a", document_id_of("a"), Change.CREATED, False),
                    DocumentFailed("b", document_id_of("b"), FailureType.DOCUMENT_REJECTED),
                )
            ),
        )

        result = env.run()

        assert isinstance(result, ReadyToFinish)
        assert registered_names(env) == [["a", "b"], ["b"]]
        assert env.skip_record_ids() == []
        assert env.job_body()["registration"]["created_count"] == 2


def test_an_oversize_failure_from_the_indexer_is_recorded_without_retry() -> None:
    with crawl_env(files={"a": b"abc"}) as env:
        env.indexer.registration_failures["a"] = FailureType.OVERSIZE

        result = env.run()

        assert isinstance(result, ReadyToFinish)
        assert len(registered_names(env)) == 1
        assert env.skip_record_ids() == []
        (record_id,) = env.oversize_record_ids()
        record = env.jobs.jobs_repository.body_of(record_id)
        assert record is not None
        assert (record["detected_by"], record["size"]) == ("indexer", 3)
        assert result.run.tally.oversize_document_ids == (document_id_of("a"),)
        assert result.run.tally.skipped_document_ids == ()


@pytest.mark.parametrize("failure_type", [FailureType.WRITE_CONFLICT, FailureType.UPDATE_CONFLICT])
def test_an_unresolved_conflict_fails_the_job_and_is_never_skipped(
    failure_type: FailureType,
) -> None:  # CA-K-10
    with crawl_env(files={"a": b"1", "b": b"2"}) as env:
        env.indexer.registration_failures["b"] = failure_type

        assert_failed(env, env.run(), "conflict_unresolved")

        assert registered_names(env) == [["a", "b"], ["b"], ["b"]]
        assert env.skip_record_ids() == []
        assert failure_type.value in env.job_body()["failure_detail"]


@pytest.mark.parametrize("failure_type", [FailureType.WRITE_CONFLICT, FailureType.UPDATE_CONFLICT])
def test_a_conflict_that_clears_on_resend_succeeds(failure_type: FailureType) -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(
            REGISTER_DOCUMENTS,
            BatchResults((DocumentFailed("a", document_id_of("a"), failure_type),)),
        )

        result = env.run()

        assert isinstance(result, ReadyToFinish)
        assert registered_names(env) == [["a"], ["a"]]
        assert env.sleeps == [1.0]


def test_a_document_level_lock_not_owned_is_recorded_as_a_loss_and_stops() -> None:
    with crawl_env(files={"a": b"1", "b": b"2"}) as env:
        env.indexer.registration_failures["b"] = FailureType.LOCK_NOT_OWNED

        with pytest.raises(OwnershipLost) as raised:
            env.run()

        assert raised.value.reason == "lock_not_owned"
        assert env.heartbeat.lost_reason == "lock_not_owned"
        assert len(registered_names(env)) == 1  # リトライもスキップもしない
        assert env.skip_record_ids() == []
        # 最終状態は、喪失の最終対応(P6b)。ここでは記録しない。
        assert env.job_body()["status"] == "running"


def test_a_last_seen_lock_not_owned_is_recorded_as_a_loss_and_stops() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(
            REPORT_LAST_SEEN,
            LastSeenResults((LastSeenEntry(document_id_of("a"), LastSeenResult.LOCK_NOT_OWNED),)),
        )

        with pytest.raises(OwnershipLost):
            env.run()

        assert env.heartbeat.lost_reason == "lock_not_owned"
        assert env.connector.fetch_calls == []


# --- last-seen の update_conflict ---


def conflicting(*names: str) -> LastSeenResults:
    return LastSeenResults(
        tuple(LastSeenEntry(document_id_of(n), LastSeenResult.UPDATE_CONFLICT) for n in names)
    )


def test_last_seen_update_conflicts_are_resent_for_the_conflicting_ids_only() -> None:
    with crawl_env(files={"a": b"1", "b": b"2", "c": b"3"}) as env:
        env.indexer.behavior.inject(REPORT_LAST_SEEN, conflicting("b"))

        result = env.run()

        assert isinstance(result, ReadyToFinish)
        sent = [call.arguments["document_ids"] for call in env.indexer.calls_of(REPORT_LAST_SEEN)]
        assert sent == [
            [document_id_of(n) for n in ["a", "b", "c"]],
            [document_id_of("b")],
        ]
        assert env.sleeps == [1.0]


def test_unresolved_last_seen_update_conflicts_fail_the_job() -> None:  # CA-K-10
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(REPORT_LAST_SEEN, conflicting("a"), times=None)

        assert_failed(env, env.run(), "conflict_unresolved")

        assert len(env.indexer.calls_of(REPORT_LAST_SEEN)) == 3
        assert env.sleeps == [1.0, 2.0]
        assert env.connector.fetch_calls == []
        assert env.skip_record_ids() == []


def test_a_document_id_mismatch_in_the_batch_response_fails_the_job() -> None:  # 観点 #1
    with crawl_env(files={"a": b"1", "b": b"2"}) as env:
        env.indexer.behavior.inject(
            REGISTER_DOCUMENTS,
            BatchResults(
                (
                    DocumentRegistered("a", document_id_of("a"), Change.CREATED, False),
                    DocumentRegistered("b", "f" * 64, Change.CREATED, False),
                )
            ),
        )

        assert_failed(env, env.run(), "document_id_mismatch")

        assert len(registered_names(env)) == 1  # 再送しない
        assert "f" * 64 in env.job_body()["failure_detail"]
        assert document_id_of("b") in env.job_body()["failure_detail"]
        # 照合の前に、応答の全体を適用しない。
        assert env.job_body()["registration"]["created_count"] == 0
