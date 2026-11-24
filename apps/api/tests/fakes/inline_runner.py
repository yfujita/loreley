from collections.abc import Callable, Collection, Sequence

from loreley_api.common.concurrency import Abandoned


class InlineRunner:
    """`BlockingRunner` の偽物。スレッドを使わず、呼び出し元と同じスレッドで実行する。

    どの区分で呼ばれたかを `categories` に記録する(「ブロッキングの呼び出しは `runner` 経由」の
    確認用)。実際の上限・並行・期限は、`tests/common/test_concurrency.py` が実物で確かめる。

    `run_all` は、期限を無視して全部を順に実行する(`Abandoned` は返さない)。期限を過ぎた確認の
    扱いを確かめるときは、`abandoned_indexes`(`calls` の何番目か。0 起点)を指定する。その呼び出しは
    実行せずに `Abandoned` を返す。渡された期限は `run_all_deadlines` に記録する。
    """

    def __init__(self, *, abandoned_indexes: Collection[int] = ()) -> None:
        self.categories: list[str] = []
        self.abandoned_indexes = set(abandoned_indexes)
        self.run_all_deadlines: list[float] = []

    async def run[T](self, category: str, function: Callable[..., T], *args: object) -> T:
        self.categories.append(category)
        return function(*args)

    async def run_all[T](
        self, category: str, calls: Sequence[Callable[[], T]], deadline_seconds: float
    ) -> list[T | Abandoned]:
        self.categories.extend([category] * len(calls))
        self.run_all_deadlines.append(deadline_seconds)
        return [
            Abandoned() if index in self.abandoned_indexes else call()
            for index, call in enumerate(calls)
        ]
