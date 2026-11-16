"""開始通知と、Indexer へ送る値の固定(architecture 4.5 手順 9・7.4・7.8。観点 #3・#4・#11)。"""

import pytest

from loreley_crawler.common.timestamps import format_instant, parse_instant
from loreley_crawler.crawl.executor import FailureRecorded, ReadyToFinish
from loreley_crawler.infrastructure.indexer_client import (
    MALFORMED_RESPONSE,
    IndexerRejected,
    IndexerUnavailable,
    payloads,
)
from tests.crawl.support import EXPECTED_LOCK, CrawlEnv, crawl_env
from tests.fakes.fake_indexer_client import (
    FINISH_CRAWL,
    REGISTER_DOCUMENTS,
    REPORT_LAST_SEEN,
    START_CRAWL,
)
from tests.jobs.support import JOB_ID, SOURCE_ID


def test_the_start_notice_carries_the_job_id_as_the_crawl_id_and_the_snapshot(
    env: CrawlEnv,
) -> None:
    env.run()

    (call,) = env.indexer.calls_of(START_CRAWL)
    started_at = parse_instant(env.job_body()["started_at"])
    assert call.arguments == {
        "crawl_id": JOB_ID,
        "source_id": SOURCE_ID,
        "crawl_started_at": started_at,
        "ttl": 2_592_000,
        "ratio_threshold": 0.3,
        "min_delete_count": 10,
        "force_delete": False,
        "rewrite_mode": False,
    }


def test_the_values_are_sent_with_strict_types_and_rewrite_mode_is_never_omitted(
    env: CrawlEnv,
) -> None:  # 観点 #4
    env.run()

    arguments = env.indexer.calls_of(START_CRAWL)[0].arguments
    assert type(arguments["ttl"]) is int
    assert type(arguments["min_delete_count"]) is int
    assert type(arguments["ratio_threshold"]) is float
    assert arguments["force_delete"] is False
    assert arguments["rewrite_mode"] is False
    payload = payloads.start_payload(**arguments)  # 実クライアントが送る JSON の本文
    assert payload["rewrite_mode"] is False
    assert payload["force_delete"] is False


def test_the_crawl_started_at_is_the_same_string_in_every_request() -> None:  # 観点 #3
    with crawl_env(files={"a.txt": b"a"}) as env:
        env.run()

        body = env.job_body()
        expected = body["settings_snapshot"]["crawl_started_at"]
        assert body["started_at"] == expected
        calls = env.indexer.calls_of(START_CRAWL, REPORT_LAST_SEEN, REGISTER_DOCUMENTS)
        assert [call.operation for call in calls] == [
            START_CRAWL,
            REPORT_LAST_SEEN,
            REGISTER_DOCUMENTS,
        ]
        # 実クライアントは `format_instant` で文字列にして送る。
        assert {format_instant(call.arguments["crawl_started_at"]) for call in calls} == {expected}


def test_the_lock_sent_with_writes_is_the_owner_and_the_job_id() -> None:
    with crawl_env(files={"a.txt": b"a"}) as env:
        env.run()

        locks = [
            call.arguments["lock"]
            for call in env.indexer.calls_of(REPORT_LAST_SEEN, REGISTER_DOCUMENTS)
        ]
        assert locks == [EXPECTED_LOCK, EXPECTED_LOCK]


def test_a_lost_start_response_is_resent_with_the_same_values(env: CrawlEnv) -> None:  # 観点 #3
    env.indexer.behavior.inject(START_CRAWL, IndexerUnavailable("timeout"), times=1)

    result = env.run()

    assert isinstance(result, ReadyToFinish)
    first, second = (call.arguments for call in env.indexer.calls_of(START_CRAWL))
    assert first == second
    assert env.sleeps == [1.0]


@pytest.mark.parametrize("reason", ["http_500", "http_503", "connection_error", "timeout"])
def test_an_unavailable_indexer_is_retried_and_then_the_job_fails(
    env: CrawlEnv, reason: str
) -> None:  # 観点 #11
    env.indexer.behavior.inject(START_CRAWL, IndexerUnavailable(reason), times=None)

    result = env.run()

    assert isinstance(result, FailureRecorded)
    assert len(env.indexer.calls_of(START_CRAWL)) == 3
    assert env.sleeps == [1.0, 2.0]
    body = env.job_body()
    assert body["status"] == "failed"
    assert body["failure_reason"] == "indexer_unavailable"
    assert reason in body["failure_detail"]
    assert env.indexer.operations() == [START_CRAWL] * 3  # 以降の要請を送らない


@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [
        (400, "invalid_request"),
        (409, "crawl_already_finished"),
        (409, "stale_crawl_started_at"),
        (409, "crawl_start_conflict"),
        (404, "not_found"),
        (405, "method_not_allowed"),
        (502, None),
        (200, MALFORMED_RESPONSE),
    ],
)
def test_a_rejection_is_not_retried_and_fails_the_job(
    env: CrawlEnv, status_code: int, error_code: str | None
) -> None:  # 観点 #11
    env.indexer.behavior.inject(START_CRAWL, IndexerRejected(status_code, error_code))

    result = env.run()

    assert isinstance(result, FailureRecorded)
    assert len(env.indexer.calls_of(START_CRAWL)) == 1
    assert env.sleeps == []
    body = env.job_body()
    assert body["failure_reason"] == "indexer_rejected"
    assert str(status_code) in body["failure_detail"]


def test_a_failed_start_notice_leaves_the_run_marked_as_not_started(env: CrawlEnv) -> None:
    env.indexer.behavior.inject(START_CRAWL, IndexerRejected(400, "invalid_request"))

    result = env.run()

    assert isinstance(result, FailureRecorded)
    assert result.run is not None
    assert result.run.start_notice_sent is False


def test_a_failure_after_the_start_notice_marks_the_run_as_started() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.inject(REPORT_LAST_SEEN, IndexerRejected(400, "invalid_request"))

        result = env.run()

        assert isinstance(result, FailureRecorded)
        assert result.run is not None
        assert result.run.start_notice_sent is True


def test_a_failure_before_the_run_exists_carries_no_run() -> None:
    with crawl_env(seed_source=False) as env:
        result = env.run()

        assert isinstance(result, FailureRecorded)
        assert result.run is None


@pytest.mark.parametrize("ending", ["succeeded", "failed_notice", "cancelled_notice"])
def test_every_request_carries_the_job_id_as_the_crawl_id(ending: str) -> None:
    with crawl_env(files={"a": b"1"}) as env:
        if ending == "failed_notice":
            env.indexer.behavior.inject(REGISTER_DOCUMENTS, IndexerRejected(400, "x"))
        if ending == "cancelled_notice":
            env.indexer.behavior.before(
                REPORT_LAST_SEEN, lambda: env.jobs.cancel_requests.request(JOB_ID)
            )

        env.executor(env.record, env.context)

        calls = env.indexer.calls
        assert {call.operation for call in calls} >= {START_CRAWL, REPORT_LAST_SEEN}
        assert {call.arguments["crawl_id"] for call in calls if "crawl_id" in call.arguments} == {
            JOB_ID
        }
        assert all("crawl_id" in call.arguments for call in calls)
        if ending != "succeeded":
            assert env.indexer.calls_of(FINISH_CRAWL)  # 通知の `crawl_id` も確かめられている


def test_the_start_notice_resend_is_identical_even_when_the_clock_moves_on() -> None:
    with crawl_env(advance_clock_on_sleep=True) as env:
        env.indexer.behavior.inject(START_CRAWL, IndexerUnavailable("timeout"), times=2)

        result = env.run()

        assert isinstance(result, ReadyToFinish)
        first, second, third = (call.arguments for call in env.indexer.calls_of(START_CRAWL))
        assert first == second == third
        assert env.sleeps == [1.0, 2.0]
