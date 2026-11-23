"""ブロッキング処理のスレッドへの受け渡し(C 8.1。AAA-P-33)。

ハンドラ(`async def`)は、ブロッキングの I/O(OpenSearch・Crawler・プローブ)を、区分ごとの
上限つきでスレッドに渡す。待っている要求はイベントループの上で待ち(スレッドを占有しない)、
1 つの区分の遅延が他の区分に波及しない。**`anyio` を直接 import してよい唯一の場所**(D R5)。

- `run`: 1 回の呼び出し。終わるまで待つ(キャンセルされてもスレッドの終了を待つ。既定)。
- `run_all`: 複数の呼び出しを並行に実行し、全体の期限で打ち切る(EP-13)。期限を過ぎた呼び出しは
  `abandon_on_cancel=True` で放棄して戻る(anyio 4.16.0 の既定 `False` では、キャンセルがスレッドの
  終了まで効かず、期限で応答できないため。AAM-P-27)。放棄してもスレッドは中断できず、自身の
  タイムアウトまで走り続ける。放棄の時点で区分のトークンは返るので、そのスレッドは区分の上限の
  外に残りうる。
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import anyio
from anyio import CapacityLimiter, to_thread

# 同時実行の上限(仮値。設定にしない。C 8.1)。
CATEGORY_OPENSEARCH = "opensearch"
CATEGORY_CRAWLER = "crawler"
CATEGORY_PROBE = "probe"
DEFAULT_CATEGORY_LIMITS: Mapping[str, int] = {
    CATEGORY_OPENSEARCH: 16,
    CATEGORY_CRAWLER: 4,
    CATEGORY_PROBE: 8,
}


@dataclass(frozen=True)
class Abandoned:
    """`run_all` の期限までに終わらなかった呼び出し。呼び出し側が `timeout` などとして扱う。"""


class BlockingRunner:
    """区分ごとの `CapacityLimiter` で、ブロッキングの呼び出しをスレッドに渡す。"""

    def __init__(self, category_limits: Mapping[str, int] = DEFAULT_CATEGORY_LIMITS) -> None:
        self._limiters = {
            category: CapacityLimiter(limit) for category, limit in category_limits.items()
        }

    async def run[T](self, category: str, function: Callable[..., T], *args: object) -> T:
        """`function(*args)` を `category` の枠でスレッドに渡し、終わるまで待つ。"""
        return await to_thread.run_sync(function, *args, limiter=self._limiter_of(category))

    async def run_all[T](
        self, category: str, calls: Sequence[Callable[[], T]], deadline_seconds: float
    ) -> list[T | Abandoned]:
        """`calls` を並行に実行し、`calls` と同じ順の結果を返す。

        `deadline_seconds` までに終わらなかった呼び出し(枠の空きを待っていたものを含む)は
        `Abandoned`。呼び出しが例外を出したときは、他の呼び出しが終わった(または期限が来た)後に、
        最初の例外をそのまま送出する(Reader・プローブは例外を漏らさない前提で、想定外の扱い)。
        """
        limiter = self._limiter_of(category)
        results: list[T | Abandoned] = [Abandoned()] * len(calls)
        errors: list[Exception] = []

        async def run_one(index: int, call: Callable[[], T]) -> None:
            try:
                results[index] = await to_thread.run_sync(
                    call, abandon_on_cancel=True, limiter=limiter
                )
            except Exception as error:
                errors.append(error)

        with anyio.move_on_after(deadline_seconds):
            async with anyio.create_task_group() as task_group:
                for index, call in enumerate(calls):
                    task_group.start_soon(run_one, index, call)
        if errors:
            raise errors[0]
        return results

    def _limiter_of(self, category: str) -> CapacityLimiter:
        limiter = self._limiters.get(category)
        if limiter is None:
            raise ValueError(f"unknown blocking category: {category}")
        return limiter
