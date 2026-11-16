"""取り消し要求のレジストリ(スレッド間で共有する状態 (1)。architecture 4.7・CA-P-44)と起床通知。"""

import threading

from loreley_crawler.jobs import CancelRequestRegistry, RunnerWakeup
from tests.jobs.support import WAIT_TIMEOUT_SECONDS


def test_a_request_is_visible_until_it_is_cleared() -> None:
    registry = CancelRequestRegistry()

    assert registry.is_requested("job-1") is False
    registry.request("job-1")
    assert registry.is_requested("job-1") is True
    assert registry.is_requested("job-2") is False
    registry.clear("job-1")
    assert registry.is_requested("job-1") is False


def test_repeated_requests_are_one_request() -> None:
    registry = CancelRequestRegistry()

    registry.request("job-1")
    registry.request("job-1")
    registry.clear("job-1")

    assert registry.is_requested("job-1") is False


def test_clearing_without_a_request_does_nothing() -> None:
    registry = CancelRequestRegistry()

    registry.clear("job-1")
    registry.request("job-2")
    registry.clear("job-1")

    assert registry.is_requested("job-2") is True


def test_a_request_made_in_another_thread_is_seen_by_the_runner_thread() -> None:
    registry = CancelRequestRegistry()
    requested = threading.Event()

    def api_thread() -> None:
        registry.request("job-1")
        requested.set()

    thread = threading.Thread(target=api_thread)
    thread.start()
    assert requested.wait(WAIT_TIMEOUT_SECONDS)
    thread.join(timeout=WAIT_TIMEOUT_SECONDS)

    assert registry.is_requested("job-1") is True


def test_concurrent_requests_and_clears_keep_the_registry_consistent() -> None:
    registry = CancelRequestRegistry()
    barrier = threading.Barrier(8, timeout=WAIT_TIMEOUT_SECONDS)

    def worker(index: int) -> None:
        barrier.wait()
        for round_number in range(200):
            job_id = f"job-{index}-{round_number}"
            registry.request(job_id)
            assert registry.is_requested(job_id)
            registry.clear(job_id)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=WAIT_TIMEOUT_SECONDS)
        assert not thread.is_alive()

    assert not any(registry.is_requested(f"job-{i}-{r}") for i in range(8) for r in range(200))


# --- 起床通知 ---


def test_a_notification_makes_the_next_wait_return_immediately_once() -> None:
    wakeup = RunnerWakeup()

    wakeup.notify()
    wakeup.notify()  # 重ねても 1 回

    assert wakeup.wait(0) is True
    assert wakeup.wait(0) is False


def test_a_wait_without_a_notification_times_out() -> None:
    assert RunnerWakeup().wait(0) is False


def test_a_notification_from_another_thread_wakes_a_waiting_thread() -> None:
    wakeup = RunnerWakeup()
    woken: list[bool] = []
    waiting = threading.Event()

    def runner_thread() -> None:
        waiting.set()
        woken.append(wakeup.wait(WAIT_TIMEOUT_SECONDS))

    thread = threading.Thread(target=runner_thread)
    thread.start()
    assert waiting.wait(WAIT_TIMEOUT_SECONDS)
    wakeup.notify()
    thread.join(timeout=WAIT_TIMEOUT_SECONDS)

    assert woken == [True]
