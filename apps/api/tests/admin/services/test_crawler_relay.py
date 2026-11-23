"""Crawler への中継の共通手順(C 4.2・4.6)。送信の枠・1 回だけ送ること・`lock_state` の読み取り。"""

import logging
from collections.abc import Awaitable

import pytest

from loreley_api.admin.base.codes import LockState
from loreley_api.admin.base.errors import AdminApiError
from loreley_api.admin.crawler_mapping import CrawlerOperation, RequestedOptions
from loreley_api.admin.services.crawler_relay import CrawlerRelay
from loreley_api.admin.services.lock_view import LockViewService
from loreley_api.infrastructure.crawler_client import (
    CrawlerContractViolation,
    CrawlerRejected,
    CrawlerResult,
    CrawlerSucceeded,
    CrawlerTransportFailed,
)
from tests.admin.factories import SENTINEL, at
from tests.admin.write_requests import seed_lock
from tests.fakes.clock import FixedClock
from tests.fakes.fake_crawler_client import FakeCrawlerClient
from tests.fakes.in_memory_readers import STORE_TIMEOUT, STORE_UNAVAILABLE, InMemoryReaders
from tests.fakes.inline_runner import InlineRunner
from tests.secret_assertions import assert_secret_absent

pytestmark = pytest.mark.anyio

EXISTING_JOB = {"job_id": "job-existing", "job_type": "crawl", "status": "running"}
START_CRAWL = CrawlerOperation.START_CRAWL


@pytest.fixture
def relay(
    readers: InMemoryReaders, fixed_clock: FixedClock, inline_runner: InlineRunner
) -> CrawlerRelay:
    lock_view = LockViewService(
        jobs=readers.jobs,
        runner=inline_runner,  # type: ignore[arg-type]
        grace_seconds=60.0,
    )
    return CrawlerRelay(
        runner=inline_runner,  # type: ignore[arg-type]
        lock_view=lock_view,
        clock=fixed_clock,
    )


def send_crawl(relay: CrawlerRelay, crawler: FakeCrawlerClient) -> Awaitable[CrawlerSucceeded]:
    return relay.send(
        START_CRAWL,
        lambda: crawler.start_crawl("docs", force_delete=True, rewrite_mode=False),
        lock_source_id="docs",
        requested=RequestedOptions(force_delete=True, rewrite_mode=False),
    )


async def test_a_success_is_returned_after_one_call_in_the_crawler_category(
    relay: CrawlerRelay,
    crawler: FakeCrawlerClient,
    readers: InMemoryReaders,
    inline_runner: InlineRunner,
) -> None:
    succeeded = await send_crawl(relay, crawler)

    assert isinstance(succeeded, CrawlerSucceeded)
    assert succeeded.status == 202
    assert len(crawler.requests) == 1
    assert inline_runner.categories == ["crawler"]
    assert readers.behavior.calls == []


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (CrawlerTransportFailed("before_send", "connection_failed"), "crawler_unreachable"),
        (CrawlerTransportFailed("after_send", "response_timeout"), "crawler_response_lost"),
    ],
)
async def test_a_transport_failure_is_raised_once_without_a_second_call(
    relay: CrawlerRelay, crawler: FakeCrawlerClient, failure: object, code: str
) -> None:
    crawler.behavior.inject("start_crawl", failure, times=None)

    with pytest.raises(AdminApiError) as raised:
        await send_crawl(relay, crawler)

    assert raised.value.code == code
    assert len(crawler.requests) == 1


async def test_a_conflict_reads_the_lock_state_after_the_call(
    relay: CrawlerRelay, crawler: FakeCrawlerClient, readers: InMemoryReaders
) -> None:
    crawler.behavior.inject(
        "start_crawl", CrawlerRejected(409, "lock_held", {"existing_job": EXISTING_JOB}, None)
    )
    crawler.behavior.before("start_crawl", lambda: seed_lock(readers, "held_delete"))

    with pytest.raises(AdminApiError) as raised:
        await send_crawl(relay, crawler)

    assert raised.value.status_code == 409
    assert raised.value.details is not None
    assert raised.value.details["lock_state"] == LockState.HELD_DELETE.value


@pytest.mark.parametrize("failure", [STORE_UNAVAILABLE, STORE_TIMEOUT])
@pytest.mark.parametrize("failing_read", ["jobs.get_locks", "jobs.get_jobs"])
async def test_a_failed_lock_read_makes_the_state_unknown_and_keeps_the_conflict(
    relay: CrawlerRelay,
    crawler: FakeCrawlerClient,
    readers: InMemoryReaders,
    failing_read: str,
    failure: object,
) -> None:
    seed_lock(readers, "held_crawl")
    readers.behavior.inject(failing_read, failure, times=None)
    crawler.behavior.inject(
        "start_crawl", CrawlerRejected(409, "lock_held", {"existing_job": EXISTING_JOB}, None)
    )

    with pytest.raises(AdminApiError) as raised:
        await send_crawl(relay, crawler)

    assert (raised.value.status_code, raised.value.code) == (409, "lock_held")
    assert raised.value.details is not None
    assert raised.value.details["lock_state"] == "unknown"
    assert raised.value.details["existing_job"]["job_id"] == "job-existing"
    assert raised.value.details["existing_job"]["job_type"] == "crawl"


async def test_a_conflict_without_a_source_to_read_the_lock_of_is_a_programming_error(
    relay: CrawlerRelay, crawler: FakeCrawlerClient
) -> None:
    crawler.behavior.inject(
        "start_crawl", CrawlerRejected(409, "lock_held", {"existing_job": EXISTING_JOB}, None)
    )

    with pytest.raises(ValueError):
        await relay.send(
            START_CRAWL, lambda: crawler.start_crawl("docs", force_delete=False, rewrite_mode=False)
        )


async def test_the_lock_state_is_derived_at_the_time_after_the_crawler_responded(
    relay: CrawlerRelay,
    crawler: FakeCrawlerClient,
    readers: InMemoryReaders,
    fixed_clock: FixedClock,
) -> None:
    """取得の 30 秒後に呼び出しを始め、応答が 40 秒かかる(猶予は 60 秒)。

    呼び出し前の時刻で判定すれば取得から 30 秒で `just_acquired` になるが、応答後の時刻
    (取得から 70 秒)では `orphan` になる。判定は後者(C 4.6)。
    """
    readers.put_lock("docs", job_id="no-such-job", acquired_at=at(-30))
    crawler.behavior.inject(
        "start_crawl", CrawlerRejected(409, "lock_held", {"existing_job": EXISTING_JOB}, None)
    )
    crawler.behavior.before("start_crawl", lambda: fixed_clock.advance(seconds=40))

    with pytest.raises(AdminApiError) as raised:
        await send_crawl(relay, crawler)

    assert raised.value.details is not None
    assert raised.value.details["lock_state"] == LockState.ORPHAN.value


# --- 失敗の理由のログ(既定の水準 INFO でも残す。固定語彙と整数だけ。R11) ---

LOGGED_FAILURES = [
    (
        CrawlerTransportFailed("before_send", "connection_failed"),
        "crawler call failed: operation=start_crawl error_code=crawler_unreachable "
        "crawler_status=None crawler_code=None reason=connection_failed",
    ),
    (
        CrawlerTransportFailed("after_send", "response_timeout"),
        "crawler call failed: operation=start_crawl error_code=crawler_response_lost "
        "crawler_status=None crawler_code=None reason=response_timeout",
    ),
    (
        CrawlerContractViolation("malformed_body", 202),
        "crawler call failed: operation=start_crawl error_code=crawler_error "
        "crawler_status=202 crawler_code=None reason=malformed_body",
    ),
    (
        CrawlerRejected(503, "unavailable", {"message": SENTINEL}, None),
        "crawler call failed: operation=start_crawl error_code=crawler_unavailable "
        "crawler_status=503 crawler_code=unavailable reason=None",
    ),
    (
        CrawlerRejected(500, "internal_error", {"message": SENTINEL}, None),
        "crawler call failed: operation=start_crawl error_code=crawler_error "
        "crawler_status=500 crawler_code=internal_error reason=None",
    ),
    (
        # 表にない code は Crawler の自由な文字列なので、値を出さない。
        CrawlerRejected(418, f"teapot-{SENTINEL}", {"message": SENTINEL}, None),
        "crawler call failed: operation=start_crawl error_code=crawler_error "
        "crawler_status=418 crawler_code=unexpected reason=None",
    ),
]


@pytest.mark.parametrize(("failure", "expected_message"), LOGGED_FAILURES)
async def test_an_unexpected_failure_of_the_crawler_is_logged_as_a_warning_with_fixed_words_only(
    relay: CrawlerRelay,
    crawler: FakeCrawlerClient,
    caplog: pytest.LogCaptureFixture,
    failure: CrawlerResult,
    expected_message: str,
) -> None:
    caplog.set_level(logging.INFO)
    crawler.behavior.inject("start_crawl", failure)

    with pytest.raises(AdminApiError):
        await relay.send(
            START_CRAWL,
            lambda: crawler.start_crawl(SENTINEL, force_delete=False, rewrite_mode=False),
            lock_source_id=SENTINEL,
        )

    [record] = [record for record in caplog.records if record.levelno >= logging.WARNING]
    assert record.levelno == logging.WARNING
    assert record.getMessage() == expected_message
    assert_secret_absent(SENTINEL, records=caplog.records)


@pytest.mark.parametrize(
    "expected_failure",
    [
        CrawlerRejected(404, "source_config_not_found", {"message": SENTINEL}, None),
        CrawlerRejected(409, "source_deleting", {"message": SENTINEL}, None),
        CrawlerRejected(409, "maintenance_enabled", {"message": SENTINEL}, None),
    ],
)
async def test_an_expected_rejection_of_the_crawler_is_not_logged_as_a_warning(
    relay: CrawlerRelay,
    crawler: FakeCrawlerClient,
    caplog: pytest.LogCaptureFixture,
    expected_failure: CrawlerRejected,
) -> None:
    caplog.set_level(logging.INFO)
    crawler.behavior.inject("start_crawl", expected_failure)

    with pytest.raises(AdminApiError) as raised:
        await send_crawl(relay, crawler)

    assert raised.value.status_code < 500
    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []


async def test_a_success_is_not_logged_as_a_warning(
    relay: CrawlerRelay, crawler: FakeCrawlerClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    await send_crawl(relay, crawler)

    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []
