import threading
from datetime import UTC, datetime

import pytest

from loreley_indexer.common.clock import SystemClock
from tests.fakes.behavior import FakeBehavior
from tests.fakes.clock import FixedClock
from tests.fakes.gate import Gate


def test_fixed_clock_only_moves_when_told() -> None:
    clock = FixedClock(datetime(2026, 11, 11, tzinfo=UTC))
    assert clock.now() == clock.now()
    clock.advance(seconds=90)
    assert clock.now() == datetime(2026, 11, 11, 0, 1, 30, tzinfo=UTC)
    clock.set(datetime(2027, 1, 1, tzinfo=UTC))
    assert clock.now().year == 2027


def test_gate_holds_a_worker_until_released() -> None:
    gate = Gate()
    finished = threading.Event()

    def worker() -> None:
        gate.pass_through()
        finished.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    gate.wait_until_arrived()
    assert not finished.is_set()  # 到達したが、解放されるまで先に進まない

    gate.release()
    thread.join(timeout=5)
    assert finished.is_set()


def test_gate_that_is_never_released_fails_instead_of_hanging() -> None:
    gate = Gate(timeout_seconds=0.05)
    with pytest.raises(TimeoutError):
        gate.pass_through()


def test_gate_that_is_never_reached_fails_instead_of_hanging() -> None:
    gate = Gate(timeout_seconds=0.05)
    with pytest.raises(TimeoutError):
        gate.wait_until_arrived()


def test_system_clock_returns_an_aware_utc_time() -> None:
    now = SystemClock().now()
    assert now.tzinfo is UTC


def test_hook_is_consumed_exactly_once_when_threads_enter_at_the_same_time() -> None:
    behavior = FakeBehavior()
    runs: list[str] = []
    behavior.before("op", lambda: runs.append("hook"))
    errors: list[BaseException] = []
    start = threading.Barrier(8, timeout=5)

    def enter() -> None:
        try:
            start.wait()
            behavior.enter("op", "k")
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=enter, daemon=True) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert errors == []
    assert runs == ["hook"]
    assert len(behavior.calls) == 8


def test_hook_runs_outside_the_internal_lock() -> None:
    """フックの中でブロックしても、別スレッドの `enter` は進める。"""
    behavior = FakeBehavior()
    gate = Gate()
    behavior.before("op", gate.pass_through)
    blocked = threading.Thread(target=lambda: behavior.enter("op"), daemon=True)
    blocked.start()
    gate.wait_until_arrived()

    # フックが解放されるのを待たずに完了することを要求する。
    # (Gate はタイムアウトでフックを抜けるため、後で通るだけでは退行を検出できない)
    other_done = threading.Event()

    def enter_other() -> None:
        behavior.enter("other")
        other_done.set()

    other = threading.Thread(target=enter_other, daemon=True)
    other.start()
    other_finished_while_hook_was_blocked = other_done.wait(timeout=1.0)

    gate.release()
    blocked.join(timeout=5)
    other.join(timeout=5)
    assert other_finished_while_hook_was_blocked


@pytest.mark.parametrize("times", [0, -1])
def test_inject_rejects_a_count_that_would_never_apply(times: int) -> None:
    with pytest.raises(ValueError):
        FakeBehavior().inject("op", "outcome", times=times)


@pytest.mark.parametrize("times", [1, 3, None])
def test_inject_applies_for_the_given_number_of_calls(times: int | None) -> None:
    behavior = FakeBehavior()
    behavior.inject("op", "outcome", times=times)

    num_calls = times if times is not None else 5
    for _ in range(num_calls):
        assert behavior.enter("op").value == "outcome"
    if times is not None:
        assert behavior.enter("op") is None  # 回数を使い切ったら、元の動作に戻る


def test_injected_exception_is_raised_as_a_fresh_instance_each_time() -> None:
    behavior = FakeBehavior()
    original = ConnectionError("down")
    behavior.inject("op", original, times=None)

    raised: list[BaseException] = []
    for _ in range(2):
        with pytest.raises(ConnectionError, match="down") as excinfo:
            behavior.enter("op")
        raised.append(excinfo.value)

    assert raised[0] is not raised[1]
    assert raised[0] is not original
    assert original.__traceback__ is None  # 送出したのは複製で、元の例外に traceback が溜まらない
