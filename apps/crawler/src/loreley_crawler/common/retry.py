"""リトライの汎用機構(module 4.11。CM-P-12。architecture 6.1)。

最大試行回数・指数バックオフ・ジッタに従って操作を繰り返し、待ちを確認点で中断できる。
何をリトライするか(例外・結果の判断)と、確認点(所有・取り消し・メンテナンス)は呼び出し側が
渡す。この機構は値(回数・間隔)も、業務上の判断も持たない。

- 確認点は、各試行の前(最初の試行を含む)と、待ちの途中で呼ぶ(R8)。確認点が例外を送出すれば、
  リトライを中断してその例外が伝わる。
- 待ちと乱数の元は引数で差し替えられる(テストは待たずに、決定的に確かめる)。
"""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass

Checkpoint = Callable[[], None]
Sleep = Callable[[float], None]
RandomSource = Callable[[], float]

# 確認点を通す間隔。取り消しなどを、待ちの途中でもこの間隔で検知できる。
DEFAULT_WAIT_SLICE_SECONDS = 1.0


@dataclass(frozen=True)
class RetryPolicy:
    """リトライの設定。無制限のリトライにならないよう、試行回数は必ず有限にする。

    `max_attempts` は最初の 1 回を含む(3 なら、最初の 1 回 + リトライ 2 回)。
    `jitter_ratio` は、待ち時間を最大でこの割合だけ短くする幅(0 でジッタなし、1 で 0 秒まで)。
    ジッタは短くする向きだけで、`max_backoff_seconds` を超えない。
    """

    max_attempts: int
    initial_backoff_seconds: float
    backoff_multiplier: float
    max_backoff_seconds: float
    jitter_ratio: float

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.initial_backoff_seconds < 0:
            raise ValueError("initial_backoff_seconds must not be negative")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be at least 1")
        if self.max_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError("max_backoff_seconds must be at least initial_backoff_seconds")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")

    def backoff_seconds(
        self, retry_number: int, random_source: RandomSource = random.random
    ) -> float:
        """`retry_number` 回目のリトライ(1 から数える)の前に待つ秒数。"""
        if retry_number < 1:
            raise ValueError("retry_number must be at least 1")
        # 累乗を使わず、1 段ずつ上限で抑える(大きな回数でも桁あふれしない)。
        delay_seconds = self.initial_backoff_seconds
        for _ in range(retry_number - 1):
            delay_seconds = min(delay_seconds * self.backoff_multiplier, self.max_backoff_seconds)
        return delay_seconds * (1 - self.jitter_ratio * random_source())


def wait_with_checkpoint(
    seconds: float,
    *,
    checkpoint: Checkpoint,
    sleep: Sleep = time.sleep,
    slice_seconds: float = DEFAULT_WAIT_SLICE_SECONDS,
) -> None:
    """`seconds` 待つ。`slice_seconds` ごとに、待つ前に確認点を呼ぶ。

    確認点が例外を送出すれば、そこで待ちを打ち切ってその例外が伝わる(取り消しなどの検知)。
    """
    if slice_seconds <= 0:
        raise ValueError("slice_seconds must be positive")
    remaining_seconds = seconds
    while remaining_seconds > 0:
        checkpoint()
        step_seconds = min(slice_seconds, remaining_seconds)
        sleep(step_seconds)
        remaining_seconds -= step_seconds


def run_with_retry[T](
    operation: Callable[[], T],
    *,
    policy: RetryPolicy,
    is_retryable_error: Callable[[Exception], bool] = lambda _error: False,
    is_retryable_result: Callable[[T], bool] = lambda _result: False,
    checkpoint: Checkpoint = lambda: None,
    sleep: Sleep = time.sleep,
    wait_slice_seconds: float = DEFAULT_WAIT_SLICE_SECONDS,
    random_source: RandomSource = random.random,
) -> T:
    """`operation` を、成功するか試行回数を尽くすまで繰り返す。

    - 例外: `is_retryable_error` が真ならリトライする。偽、または試行を尽くしたときは、
      その例外をそのまま送出する(最後の試行の例外)。
    - 結果: `is_retryable_result` が真ならリトライする。試行を尽くしたときは、最後の結果を
      返す(呼び出し側が失敗として扱う。型付きの結果を返す操作のため)。
    - `Exception` だけを捕捉する(`KeyboardInterrupt` などはリトライしない)。
    """
    for retry_number in range(1, policy.max_attempts):
        checkpoint()
        try:
            result = operation()
        except Exception as error:
            if not is_retryable_error(error):
                raise
        else:
            if not is_retryable_result(result):
                return result
        wait_with_checkpoint(
            policy.backoff_seconds(retry_number, random_source),
            checkpoint=checkpoint,
            sleep=sleep,
            slice_seconds=wait_slice_seconds,
        )
    checkpoint()
    return operation()


@dataclass(frozen=True)
class Retrier:
    """リトライの設定(`policy`)・確認点・待ち・乱数元を束ねた、`run_with_retry` の呼び出し口。

    呼び出し側が、何をリトライするか(例外・結果の判断)を `run` の引数で渡す。HTTP ハンドラや
    Job Runner など、使うスレッドごとに確認点を替えて作る(R8)。
    """

    policy: RetryPolicy
    checkpoint: Checkpoint = lambda: None
    sleep: Sleep = time.sleep
    wait_slice_seconds: float = DEFAULT_WAIT_SLICE_SECONDS
    random_source: RandomSource = random.random

    def run[T](
        self,
        operation: Callable[[], T],
        *,
        is_retryable_error: Callable[[Exception], bool] = lambda _error: False,
        is_retryable_result: Callable[[T], bool] = lambda _result: False,
    ) -> T:
        return run_with_retry(
            operation,
            policy=self.policy,
            is_retryable_error=is_retryable_error,
            is_retryable_result=is_retryable_result,
            checkpoint=self.checkpoint,
            sleep=self.sleep,
            wait_slice_seconds=self.wait_slice_seconds,
            random_source=self.random_source,
        )
