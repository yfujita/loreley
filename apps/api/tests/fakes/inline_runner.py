from collections.abc import Callable, Sequence

from loreley_api.common.concurrency import Abandoned


class InlineRunner:
    """`BlockingRunner` の偽物。スレッドを使わず、呼び出し元と同じスレッドで実行する。

    どの区分で呼ばれたかを `categories` に記録する(「ブロッキングの呼び出しは `runner` 経由」の
    確認用)。実際の上限・並行・期限は、`tests/common/test_concurrency.py` が実物で確かめる。
    """

    def __init__(self) -> None:
        self.categories: list[str] = []

    async def run[T](self, category: str, function: Callable[..., T], *args: object) -> T:
        self.categories.append(category)
        return function(*args)

    async def run_all[T](
        self, category: str, calls: Sequence[Callable[[], T]], deadline_seconds: float
    ) -> list[T | Abandoned]:
        self.categories.extend([category] * len(calls))
        return [call() for call in calls]
