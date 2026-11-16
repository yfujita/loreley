import itertools
import random
from functools import partial

import pytest

from loreley_crawler.common.retry import (
    Retrier,
    RetryPolicy,
    run_with_retry,
    wait_with_checkpoint,
)

# architecture 11章の仮値(3 回、初回 1 秒、2 倍、上限 30 秒)。ジッタなしで、待ち時間を決定的にする。
POLICY = RetryPolicy(
    max_attempts=3,
    initial_backoff_seconds=1.0,
    backoff_multiplier=2.0,
    max_backoff_seconds=30.0,
    jitter_ratio=0.0,
)

# 1 回の待ちが 1 回の sleep になるよう、確認点を通す間隔を待ち時間より十分長くする。
retry = partial(run_with_retry, wait_slice_seconds=1_000)


class Sleeps:
    """待ちの記録。実際には待たない。"""

    def __init__(self) -> None:
        self.durations: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.durations.append(seconds)


class FlakyOperation:
    """指定した回数だけ結果(または例外)を順に返す操作。"""

    def __init__(self, *outcomes: object) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def __call__(self) -> object:
        outcome = self._outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class Transient(Exception):
    pass


class Permanent(Exception):
    pass


def is_transient(error: Exception) -> bool:
    return isinstance(error, Transient)


# --- バックオフの計算 ---


def test_backoff_doubles_up_to_the_maximum() -> None:
    policy = RetryPolicy(10, 1.0, 2.0, 30.0, 0.0)
    delays = [policy.backoff_seconds(n) for n in range(1, 8)]
    assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]


def test_backoff_does_not_overflow_for_a_large_retry_number() -> None:
    assert RetryPolicy(10, 1.0, 2.0, 30.0, 0.0).backoff_seconds(5_000) == 30.0


def test_jitter_shortens_the_delay_by_at_most_the_ratio_and_never_exceeds_the_cap() -> None:
    policy = RetryPolicy(10, 1.0, 2.0, 30.0, 0.5)
    assert policy.backoff_seconds(3, lambda: 0.0) == 4.0  # 乱数が最小なら、ジッタなしと同じ
    assert policy.backoff_seconds(3, lambda: 0.5) == 3.0
    assert policy.backoff_seconds(3, lambda: 0.999999) == pytest.approx(2.0, abs=1e-5)
    assert policy.backoff_seconds(8, lambda: 0.0) == 30.0


def test_jitter_ratio_one_can_shorten_the_delay_to_almost_zero() -> None:
    policy = RetryPolicy(3, 1.0, 2.0, 30.0, 1.0)
    assert policy.backoff_seconds(1, lambda: 0.999999) == pytest.approx(0.0, abs=1e-5)


def test_the_random_source_is_replaceable_and_seedable() -> None:
    policy = RetryPolicy(10, 4.0, 2.0, 30.0, 0.5)
    first = [policy.backoff_seconds(n, random.Random(7).random) for n in range(1, 5)]
    second = [policy.backoff_seconds(n, random.Random(7).random) for n in range(1, 5)]
    assert first == second
    assert all(0 < delay <= 30.0 for delay in first)


@pytest.mark.parametrize(
    "arguments",
    [
        (0, 1.0, 2.0, 30.0, 0.0),  # 試行回数が 1 未満
        (3, -1.0, 2.0, 30.0, 0.0),
        (3, 1.0, 0.5, 30.0, 0.0),  # 倍率が 1 未満(待ちが縮む)
        (3, 5.0, 2.0, 1.0, 0.0),  # 上限が初回より小さい
        (3, 1.0, 2.0, 30.0, -0.1),
        (3, 1.0, 2.0, 30.0, 1.1),
    ],
)
def test_invalid_policies_are_rejected(arguments: tuple[int, float, float, float, float]) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(*arguments)


def test_retry_number_must_be_positive() -> None:
    with pytest.raises(ValueError, match="retry_number"):
        POLICY.backoff_seconds(0)


# --- 中断できる待ち ---


def test_wait_sleeps_in_slices_and_calls_the_checkpoint_before_each_slice() -> None:
    sleeps = Sleeps()
    checkpoints: list[int] = []

    wait_with_checkpoint(
        2.5,
        checkpoint=lambda: checkpoints.append(len(sleeps.durations)),
        sleep=sleeps,
        slice_seconds=1.0,
    )

    assert sleeps.durations == [1.0, 1.0, 0.5]
    assert checkpoints == [0, 1, 2]


def test_wait_shorter_than_a_slice_sleeps_once() -> None:
    sleeps = Sleeps()
    wait_with_checkpoint(0.3, checkpoint=lambda: None, sleep=sleeps, slice_seconds=1.0)
    assert sleeps.durations == [0.3]


@pytest.mark.parametrize("seconds", [0.0, -1.0])
def test_wait_of_no_time_does_nothing(seconds: float) -> None:
    sleeps = Sleeps()
    checkpoints: list[None] = []
    wait_with_checkpoint(seconds, checkpoint=lambda: checkpoints.append(None), sleep=sleeps)
    assert sleeps.durations == []
    assert checkpoints == []


def test_the_total_slept_time_equals_the_requested_time_without_float_drift() -> None:
    sleeps = Sleeps()
    wait_with_checkpoint(0.3, checkpoint=lambda: None, sleep=sleeps, slice_seconds=0.1)
    assert sum(sleeps.durations) == pytest.approx(0.3)
    assert len(sleeps.durations) <= 4


def test_a_checkpoint_exception_interrupts_the_wait() -> None:
    sleeps = Sleeps()
    cancelled = RuntimeError("cancelled")

    def checkpoint() -> None:
        if len(sleeps.durations) == 2:
            raise cancelled

    with pytest.raises(RuntimeError) as raised:
        wait_with_checkpoint(10.0, checkpoint=checkpoint, sleep=sleeps, slice_seconds=1.0)

    assert raised.value is cancelled
    assert sleeps.durations == [1.0, 1.0]


def test_the_slice_must_be_positive() -> None:
    with pytest.raises(ValueError, match="slice_seconds"):
        wait_with_checkpoint(1.0, checkpoint=lambda: None, slice_seconds=0)


# --- リトライの本体 ---


def test_success_on_the_first_attempt_does_not_wait() -> None:
    operation = FlakyOperation("ok")
    sleeps = Sleeps()

    assert retry(operation, policy=POLICY, sleep=sleeps) == "ok"

    assert operation.calls == 1
    assert sleeps.durations == []


def test_a_retryable_error_is_retried_with_backoff_until_success() -> None:
    operation = FlakyOperation(Transient(), Transient(), "ok")
    sleeps = Sleeps()

    result = retry(operation, policy=POLICY, is_retryable_error=is_transient, sleep=sleeps)

    assert result == "ok"
    assert operation.calls == 3
    assert sleeps.durations == [1.0, 2.0]


def test_the_last_error_is_raised_when_the_attempts_are_exhausted() -> None:
    last_error = Transient("last")
    operation = FlakyOperation(Transient("first"), Transient("second"), last_error)
    sleeps = Sleeps()

    with pytest.raises(Transient) as raised:
        retry(operation, policy=POLICY, is_retryable_error=is_transient, sleep=sleeps)

    assert raised.value is last_error
    assert operation.calls == 3  # 最大試行回数(最初の 1 回 + リトライ 2 回)で止まる
    assert sleeps.durations == [1.0, 2.0]  # 最後の失敗の後には待たない


def test_a_non_retryable_error_is_raised_at_once() -> None:
    operation = FlakyOperation(Permanent(), "ok")
    sleeps = Sleeps()

    with pytest.raises(Permanent):
        retry(operation, policy=POLICY, is_retryable_error=is_transient, sleep=sleeps)

    assert operation.calls == 1
    assert sleeps.durations == []


def test_errors_are_not_retried_unless_the_caller_says_so() -> None:
    operation = FlakyOperation(Transient(), "ok")

    with pytest.raises(Transient):
        retry(operation, policy=POLICY, sleep=Sleeps())

    assert operation.calls == 1


def test_a_retryable_result_is_retried_and_the_last_result_is_returned_when_exhausted() -> None:
    operation = FlakyOperation("unavailable-1", "unavailable-2", "unavailable-3", "never")
    sleeps = Sleeps()

    result = retry(
        operation,
        policy=POLICY,
        is_retryable_result=lambda value: str(value).startswith("unavailable"),
        sleep=sleeps,
    )

    assert result == "unavailable-3"
    assert operation.calls == 3
    assert sleeps.durations == [1.0, 2.0]


def test_a_non_retryable_result_is_returned_at_once() -> None:
    operation = FlakyOperation("rejected", "never")

    result = retry(
        operation,
        policy=POLICY,
        is_retryable_result=lambda value: value == "unavailable",
        sleep=Sleeps(),
    )

    assert result == "rejected"
    assert operation.calls == 1


def test_a_single_attempt_policy_never_retries_or_waits() -> None:
    policy = RetryPolicy(1, 1.0, 2.0, 30.0, 0.0)
    operation = FlakyOperation(Transient("only"))
    sleeps = Sleeps()

    with pytest.raises(Transient):
        retry(operation, policy=policy, is_retryable_error=is_transient, sleep=sleeps)

    assert operation.calls == 1
    assert sleeps.durations == []


def test_waits_use_the_injected_random_source_and_are_capped() -> None:
    policy = RetryPolicy(4, 10.0, 10.0, 30.0, 0.5)
    operation = FlakyOperation(Transient(), Transient(), Transient(), "ok")
    sleeps = Sleeps()

    retry(
        operation,
        policy=policy,
        is_retryable_error=is_transient,
        sleep=sleeps,
        random_source=lambda: 0.5,
    )

    assert sleeps.durations == [7.5, 22.5, 22.5]  # 10、30(上限)、30 を、それぞれ 25% 短くした値


def test_the_checkpoint_runs_before_every_attempt_and_during_the_waits() -> None:
    events: list[str] = []
    operation = FlakyOperation(Transient(), Transient(), "ok")

    def sleep(seconds: float) -> None:
        events.append(f"sleep {seconds:g}")

    def checkpoint() -> None:
        events.append("checkpoint")

    def recording_operation() -> object:
        events.append("attempt")
        return operation()

    retry(
        recording_operation,
        policy=POLICY,
        is_retryable_error=is_transient,
        checkpoint=checkpoint,
        sleep=sleep,
    )

    assert events == [
        "checkpoint",
        "attempt",
        "checkpoint",  # 待ちの前
        "sleep 1",
        "checkpoint",
        "attempt",
        "checkpoint",
        "sleep 2",
        "checkpoint",
        "attempt",
    ]


def test_a_checkpoint_exception_stops_the_retries_before_the_next_attempt() -> None:
    operation = FlakyOperation(Transient(), "ok")
    sleeps = Sleeps()
    attempts_checked = itertools.count(1)
    cancelled = RuntimeError("cancelled")

    def checkpoint() -> None:
        # 最初の試行の前は通し、2 回目の試行の前の待ちの中で取り消される。
        if next(attempts_checked) == 2:
            raise cancelled

    with pytest.raises(RuntimeError) as raised:
        retry(
            operation,
            policy=POLICY,
            is_retryable_error=is_transient,
            checkpoint=checkpoint,
            sleep=sleeps,
        )

    assert raised.value is cancelled
    assert operation.calls == 1
    assert sleeps.durations == []


def test_a_checkpoint_exception_before_the_first_attempt_runs_nothing() -> None:
    operation = FlakyOperation("ok")

    def checkpoint() -> None:
        raise RuntimeError("lost ownership")

    with pytest.raises(RuntimeError):
        retry(operation, policy=POLICY, checkpoint=checkpoint, sleep=Sleeps())

    assert operation.calls == 0


def test_base_exceptions_are_not_retried() -> None:
    class Stop(BaseException):
        pass

    operation = FlakyOperation(Stop(), "ok")

    def retry_everything(_: Exception) -> bool:
        return True

    with pytest.raises(Stop):
        retry(operation, policy=POLICY, is_retryable_error=retry_everything)

    assert operation.calls == 1


# --- Retrier(設定の束ね) ---


def test_retrier_passes_its_settings_and_the_callers_judgement_to_run_with_retry() -> None:
    sleeps = Sleeps()
    checkpoints: list[int] = []
    retrier = Retrier(
        POLICY,
        checkpoint=lambda: checkpoints.append(len(sleeps.durations)),
        sleep=sleeps,
        wait_slice_seconds=1_000,
    )
    operation = FlakyOperation(Transient(), "unfinished", "done")

    result = retrier.run(
        operation,
        is_retryable_error=is_transient,
        is_retryable_result=lambda value: value == "unfinished",
    )

    assert result == "done"
    assert operation.calls == 3
    assert sleeps.durations == [1.0, 2.0]
    # 確認点は、各試行の前と待ちの前(1 回の待ち = 1 つのスライス)に呼ばれる。
    assert checkpoints == [0, 0, 1, 1, 2]


def test_retrier_does_not_retry_unless_the_caller_says_so() -> None:
    operation = FlakyOperation(Transient())
    with pytest.raises(Transient):
        Retrier(POLICY, sleep=Sleeps()).run(operation)
    assert operation.calls == 1


def test_retrier_uses_its_random_source_for_the_jitter() -> None:
    sleeps = Sleeps()
    policy = RetryPolicy(2, 4.0, 2.0, 30.0, 0.5)
    retrier = Retrier(policy, sleep=sleeps, wait_slice_seconds=1_000, random_source=lambda: 0.5)

    retrier.run(FlakyOperation(Transient(), "ok"), is_retryable_error=is_transient)

    assert sleeps.durations == [3.0]
