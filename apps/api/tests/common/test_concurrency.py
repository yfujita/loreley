"""`BlockingRunner`(C 8.1・11章 14)。実物のスレッドと `CapacityLimiter` で確かめる。

時間に頼る確認は、余裕を大きく取る(期限 0.2 秒に対し、遅い呼び出しは `Event` で止めておく)。
"""

import threading
import time
from collections.abc import Awaitable, Callable

import anyio
import pytest

from loreley_api.common.concurrency import (
    CATEGORY_CRAWLER,
    CATEGORY_OPENSEARCH,
    CATEGORY_PROBE,
    DEFAULT_CATEGORY_LIMITS,
    Abandoned,
    BlockingRunner,
)

DEADLINE_SECONDS = 0.2
# 期限で放棄した呼び出しが、期限よりずっと前に戻ることの確認に使う上限。
PROMPT_SECONDS = 1.0


def run_async[T](function: Callable[[], Awaitable[T]]) -> T:
    return anyio.run(function)


class ConcurrencyProbe:
    """同時に実行中の呼び出しの数と、その最大値を数える。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.running = 0
        self.max_running = 0

    def work(self, seconds: float = 0.05) -> None:
        with self._lock:
            self.running += 1
            self.max_running = max(self.max_running, self.running)
        time.sleep(seconds)
        with self._lock:
            self.running -= 1


def test_the_default_limits_are_16_4_and_8() -> None:
    assert dict(DEFAULT_CATEGORY_LIMITS) == {
        CATEGORY_OPENSEARCH: 16,
        CATEGORY_CRAWLER: 4,
        CATEGORY_PROBE: 8,
    }
    assert (CATEGORY_OPENSEARCH, CATEGORY_CRAWLER, CATEGORY_PROBE) == (
        "opensearch",
        "crawler",
        "probe",
    )


def test_run_returns_the_value_and_passes_the_arguments_in_another_thread() -> None:
    runner = BlockingRunner({"a": 1})

    async def scenario() -> tuple[str, int]:
        return await runner.run("a", lambda x, y: (threading.current_thread().name, x + y), 1, 2)

    thread_name, total = run_async(scenario)

    assert total == 3
    assert thread_name != threading.current_thread().name


def test_run_propagates_the_exception_of_the_call() -> None:
    runner = BlockingRunner({"a": 1})

    def fail() -> None:
        raise KeyError("boom")

    async def scenario() -> None:
        await runner.run("a", fail)

    with pytest.raises(KeyError):
        run_async(scenario)


def test_an_unknown_category_is_a_programming_error() -> None:
    runner = BlockingRunner({"a": 1})

    async def scenario() -> None:
        await runner.run("b", lambda: None)

    with pytest.raises(ValueError, match="unknown blocking category"):
        run_async(scenario)


def test_the_number_of_concurrent_calls_in_a_category_does_not_exceed_its_limit() -> None:
    runner = BlockingRunner({"a": 2})
    probe = ConcurrencyProbe()

    async def scenario() -> None:
        async with anyio.create_task_group() as task_group:
            for _ in range(8):
                task_group.start_soon(runner.run, "a", probe.work)

    run_async(scenario)

    assert probe.max_running == 2  # 上限まで並行し、超えない


def test_a_blocked_category_does_not_delay_another_category() -> None:
    """1 つの区分の遅延が、他の区分に波及しない(区分ごとに独立の枠)。"""
    runner = BlockingRunner({"slow": 1, "fast": 1})
    release_slow = threading.Event()

    async def scenario() -> float:
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(runner.run, "slow", release_slow.wait, 10)
            task_group.start_soon(runner.run, "slow", release_slow.wait, 10)  # 枠の空きを待つ
            await anyio.sleep(0.05)
            started = time.monotonic()
            await runner.run("fast", lambda: None)
            elapsed = time.monotonic() - started
            release_slow.set()
            return elapsed

    assert run_async(scenario) < PROMPT_SECONDS


def test_waiting_for_a_slot_does_not_block_the_event_loop() -> None:
    """待っている要求はイベントループの上で待つ。他のコルーチン(`/healthz` など)が動く。"""
    runner = BlockingRunner({"a": 1})
    release = threading.Event()

    async def scenario() -> int:
        ticks = 0
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(runner.run, "a", release.wait, 10)
            task_group.start_soon(runner.run, "a", release.wait, 10)
            for _ in range(20):
                await anyio.sleep(0.005)
                ticks += 1
            release.set()
        return ticks

    assert run_async(scenario) == 20


def test_run_does_not_abandon_a_cancelled_call_but_waits_for_the_thread() -> None:
    """`run` は既定(`abandon_on_cancel=False`)。キャンセルはスレッドの終了まで効かない(AAM-U-1)。"""
    runner = BlockingRunner({"a": 1})

    async def scenario() -> float:
        started = time.monotonic()
        with anyio.move_on_after(0.05):
            await runner.run("a", time.sleep, 0.4)
        return time.monotonic() - started

    assert run_async(scenario) >= 0.35


# --- run_all ---


def test_run_all_returns_the_results_in_the_order_of_the_calls() -> None:
    runner = BlockingRunner({"a": 4})
    # 後ろの呼び出しほど早く終わる。結果は呼び出しの順のまま。
    calls = [lambda delay=delay: (time.sleep(delay), delay)[1] for delay in (0.15, 0.1, 0.05, 0.0)]

    async def scenario() -> list[object]:
        return await runner.run_all("a", calls, deadline_seconds=PROMPT_SECONDS * 5)

    assert run_async(scenario) == [0.15, 0.1, 0.05, 0.0]


def test_run_all_runs_the_calls_concurrently() -> None:
    runner = BlockingRunner({"a": 4})
    probe = ConcurrencyProbe()

    async def scenario() -> None:
        await runner.run_all("a", [lambda: probe.work(0.1)] * 4, deadline_seconds=5)

    run_async(scenario)

    assert probe.max_running == 4


def test_run_all_with_no_calls_returns_an_empty_list() -> None:
    runner = BlockingRunner({"a": 1})

    async def scenario() -> list[object]:
        return await runner.run_all("a", [], deadline_seconds=1)

    assert run_async(scenario) == []


def test_run_all_abandons_a_call_that_passes_the_deadline_and_keeps_the_others() -> None:
    runner = BlockingRunner({"a": 4})
    release_slow = threading.Event()

    async def scenario() -> tuple[list[object], float]:
        started = time.monotonic()
        results = await runner.run_all(
            "a",
            [lambda: "fast", lambda: release_slow.wait(10), lambda: "also-fast"],
            deadline_seconds=DEADLINE_SECONDS,
        )
        return results, time.monotonic() - started

    results, elapsed = run_async(scenario)
    release_slow.set()

    assert results[0] == "fast"
    assert isinstance(results[1], Abandoned)
    assert results[2] == "also-fast"
    # 遅い呼び出し(最大 10 秒)の終了は待たず、期限の近くで戻る。
    assert DEADLINE_SECONDS <= elapsed < PROMPT_SECONDS


def test_an_abandoned_thread_keeps_running_and_its_token_is_returned_at_abandonment() -> None:
    """放棄したスレッドは中断できず走り続けるが、区分のトークンは放棄の時点で返る(AAM-P-27)。"""
    runner = BlockingRunner({"a": 1})
    release_slow = threading.Event()
    slow_finished = threading.Event()

    def slow() -> None:
        release_slow.wait(10)
        slow_finished.set()

    async def scenario() -> tuple[object, float, bool]:
        [result] = await runner.run_all("a", [slow], deadline_seconds=DEADLINE_SECONDS)
        started = time.monotonic()
        # 枠は 1 つ。放棄したスレッドがまだ走っていても、次の呼び出しが待たされない。
        await runner.run("a", lambda: None)
        return result, time.monotonic() - started, slow_finished.is_set()

    result, elapsed_to_next_call, finished_before_release = run_async(scenario)

    assert isinstance(result, Abandoned)
    assert elapsed_to_next_call < PROMPT_SECONDS
    assert finished_before_release is False  # スレッドは、放棄の後も走り続けている
    release_slow.set()
    assert slow_finished.wait(PROMPT_SECONDS)  # 自身の終了までは走る


def test_run_all_abandons_a_call_that_is_still_waiting_for_a_slot() -> None:
    """枠の空きを待っていた呼び出しは、期限で放棄され、始まらない。"""
    runner = BlockingRunner({"a": 1})
    release_first = threading.Event()
    second_started = threading.Event()

    def second() -> str:
        second_started.set()
        return "second"

    async def scenario() -> list[object]:
        return await runner.run_all(
            "a",
            [lambda: release_first.wait(10), second],
            deadline_seconds=DEADLINE_SECONDS,
        )

    results = run_async(scenario)
    release_first.set()

    assert all(isinstance(result, Abandoned) for result in results)
    assert not second_started.is_set()


def test_run_all_uses_the_limit_of_its_category() -> None:
    runner = BlockingRunner({"a": 2})
    probe = ConcurrencyProbe()

    async def scenario() -> None:
        await runner.run_all("a", [probe.work] * 6, deadline_seconds=5)

    run_async(scenario)

    assert probe.max_running == 2


def test_run_all_raises_the_first_exception_after_the_other_calls_finish() -> None:
    runner = BlockingRunner({"a": 4})
    finished: list[str] = []

    def fail() -> None:
        raise KeyError("boom")

    def work() -> None:
        time.sleep(0.05)
        finished.append("work")

    async def scenario() -> None:
        await runner.run_all("a", [fail, work], deadline_seconds=5)

    with pytest.raises(KeyError):
        run_async(scenario)
    assert finished == ["work"]  # 例外が他の呼び出しを巻き込まない(ExceptionGroup にならない)


def test_run_all_rejects_an_unknown_category() -> None:
    runner = BlockingRunner({"a": 1})

    async def scenario() -> None:
        await runner.run_all("b", [lambda: None], deadline_seconds=1)

    with pytest.raises(ValueError, match="unknown blocking category"):
        run_async(scenario)


def test_the_runner_can_be_created_outside_an_event_loop_and_used_in_several_loops() -> None:
    """`main` はループの外でランナーを作り、`TestClient` は要求ごとに別のループを使う。"""
    runner = BlockingRunner({"a": 2})

    async def scenario() -> int:
        return await runner.run("a", lambda: 1)

    assert [run_async(scenario) for _ in range(3)] == [1, 1, 1]
