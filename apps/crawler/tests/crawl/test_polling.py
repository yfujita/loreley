"""削除結果のポーリングと確認結果の区分(architecture 7.6。テスト観点 #12)。

打ち切っても、ジョブの status は変えず、再確認しない。待ちは記録だけして実際には待たない
(`env.sleeps`。上限時間のテストだけ、待った秒数だけ固定時計を進める)。
"""

from typing import Any

import pytest

from loreley_crawler.crawl import CrawlSettings
from loreley_crawler.infrastructure.indexer_client import (
    MALFORMED_RESPONSE,
    CrawlStatus,
    IndexerRejected,
    IndexerUnavailable,
)
from tests.crawl.support import CrawlEnv, crawl_env, run_full
from tests.fakes.fake_indexer_client import GET_CRAWL_STATUS
from tests.jobs.support import JOB_ID, SOURCE_ID

RECEIVED_AT = "2026-11-13T00:00:00.000Z"


def running(**fields: Any) -> CrawlStatus:
    return CrawlStatus(JOB_ID, SOURCE_ID, "running", finish_received_at=RECEIVED_AT, **fields)


def terminal(status: str = "deleted") -> CrawlStatus:
    return CrawlStatus(
        JOB_ID, SOURCE_ID, status, finish_received_at=RECEIVED_AT, deleted_count=2, target_count=2
    )


def not_found() -> IndexerRejected:
    return IndexerRejected(404, "crawl_not_found")


def script(env: CrawlEnv, *replies: object) -> None:
    for reply in replies:
        env.indexer.behavior.inject(GET_CRAWL_STATUS, reply)


def polls(env: CrawlEnv) -> int:
    return len(env.indexer.calls_of(GET_CRAWL_STATUS))


def test_a_terminal_first_response_is_confirmed_without_waiting(env: CrawlEnv) -> None:
    body = run_full(env)

    assert body["confirmation"] == "confirmed"
    assert polls(env) == 1
    assert env.sleeps == []


def test_a_running_crawl_is_polled_at_the_interval_until_it_is_terminal(env: CrawlEnv) -> None:
    script(env, running(), running(waiting_for="job-earlier"), terminal())

    body = run_full(env)

    assert body["confirmation"] == "confirmed"
    assert polls(env) == 3
    assert env.sleeps == [5.0, 5.0]
    assert body["deletion_summary"]["deleted_count"] == 2


def test_only_404_until_the_failure_limit_is_unknown_and_does_not_fail_the_job(
    env: CrawlEnv,
) -> None:
    script(env, not_found(), not_found(), not_found())

    body = run_full(env)

    assert body["confirmation"] == "unknown"
    assert body["status"] == "succeeded"  # ジョブの status は変えない(CA-K-4)
    assert polls(env) == 3  # 打ち切った後は再確認しない
    assert "deletion_summary" not in body  # 一度も読めていない
    assert body["warnings"] == [{"code": "polling_aborted", "confirmation": "unknown"}]


@pytest.mark.parametrize(
    "mixed",
    [
        [
            IndexerUnavailable("timeout"),
            IndexerUnavailable("http_503"),
            IndexerUnavailable("http_500"),
        ],
        [not_found(), IndexerUnavailable("connection_error"), not_found()],
        [not_found(), not_found(), IndexerRejected(400, "invalid_request")],
        # 契約にない `status` の応答(パース時に契約違反になる)は、確認の根拠にならない失敗。
        [IndexerRejected(200, MALFORMED_RESPONSE)] * 3,
    ],
)
def test_a_streak_with_anything_but_404_is_unconfirmed(mixed: list[object], env: CrawlEnv) -> None:
    script(env, *mixed)

    body = run_full(env)

    assert body["confirmation"] == "unconfirmed"
    assert body["status"] == "succeeded"
    assert polls(env) == 3
    assert body["warnings"] == [{"code": "polling_aborted", "confirmation": "unconfirmed"}]


def test_a_success_in_between_resets_the_failure_count(env: CrawlEnv) -> None:
    script(
        env,
        IndexerUnavailable("timeout"),
        IndexerUnavailable("timeout"),
        running(),
        IndexerUnavailable("timeout"),
        IndexerUnavailable("timeout"),
        terminal(),
    )

    body = run_full(env)

    assert body["confirmation"] == "confirmed"
    assert polls(env) == 6


def test_the_time_limit_makes_the_confirmation_unconfirmed() -> None:
    settings = CrawlSettings(polling_interval_seconds=5.0, polling_timeout_seconds=20.0)
    with crawl_env(files={"a": b"1"}, settings=settings, advance_clock_on_sleep=True) as env:
        env.indexer.behavior.inject(GET_CRAWL_STATUS, running(), times=None)

        body = run_full(env)

        assert body["confirmation"] == "unconfirmed"
        assert body["status"] == "succeeded"
        assert polls(env) == 5  # 0・5・10・15・20 秒(20 秒で上限に達する)
        assert env.sleeps == [5.0] * 4
        assert body["warnings"] == [{"code": "polling_aborted", "confirmation": "unconfirmed"}]
        # 打ち切ったときは、最後に読めた応答の項目と読めた日時を写す。
        assert body["deletion_summary"]["status"] == "running"
        assert body["deletion_summary"]["observed_at"] == "2026-11-13T00:00:20.000Z"


def test_a_confirmed_summary_has_no_observation_time(env: CrawlEnv) -> None:
    assert "observed_at" not in run_full(env)["deletion_summary"]


def test_the_summary_keeps_only_the_fields_the_indexer_returned(env: CrawlEnv) -> None:
    script(
        env,
        CrawlStatus(
            JOB_ID,
            SOURCE_ID,
            "validation_failed",
            reason="id_limit_exceeded\nwith a newline",
            n_seen=1,
            e_missing=0,
            enumerated_count=1,
            finish_received_at=RECEIVED_AT,
        ),
    )

    summary = run_full(env)["deletion_summary"]

    assert summary == {
        "status": "validation_failed",
        "reason": "id_limit_exceeded\\nwith a newline",  # 制御文字はエスケープされる
        "enumerated_count": 1,
        "n_seen": 1,
        "e_missing": 0,
        "finish_received_at": RECEIVED_AT,
    }


def test_a_success_resets_which_failures_the_streak_contains(env: CrawlEnv) -> None:
    # 接続エラーの後に成功(running)が入れば、その後の 404 だけの連続は `unknown`。
    script(env, IndexerUnavailable("timeout"), running(), not_found(), not_found(), not_found())

    body = run_full(env)

    assert body["confirmation"] == "unknown"
