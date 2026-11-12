import threading
import time
from collections.abc import Callable
from typing import Any

# 待たされていることの確認に使う、ごく短い待ち。成功の判定には使わない(ブロックされていなければ
# スレッドはすぐに終わるので、この間に終わらないことだけを確認する)。
BLOCKED_PROBE_SECONDS = 0.2
JOIN_TIMEOUT_SECONDS = 5.0


class SlowReadDict(dict):
    """読んだ直後に待つ。ロックがなければ、確認と書き込みの間に別スレッドが割り込める。

    fake が内部で使う辞書(`_documents`、`_records`)をこれに差し替えて使う。
    fake の内部名への依存はここに集約する(名前を変えたらこのクラスの使用箇所だけ直せばよい)。
    `in`(create の存在確認)と `get`(版の確認)の両方を遅くする。
    """

    def __contains__(self, key: object) -> bool:
        found = super().__contains__(key)
        time.sleep(0.05)
        return found

    def get(self, key: Any, default: Any = None) -> Any:
        value = super().get(key, default)
        time.sleep(0.05)
        return value


class Background[T]:
    """別スレッドで呼び出しを実行し、完了・戻り値・例外を記録する。"""

    def __init__(self, call: Callable[[], T]) -> None:
        self.done = threading.Event()
        self.value: T | None = None
        self.error: BaseException | None = None
        self._call = call
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            self.value = self._call()
        except BaseException as error:  # テストが結果として検査する
            self.error = error
        finally:
            self.done.set()

    def is_blocked(self) -> bool:
        return not self.done.wait(BLOCKED_PROBE_SECONDS)

    def join(self) -> None:
        assert self.done.wait(JOIN_TIMEOUT_SECONDS), "the call did not finish"
        self._thread.join(JOIN_TIMEOUT_SECONDS)


def run_concurrently[T](calls: list[Callable[[], T]]) -> list[T]:
    """各呼び出しを別スレッドで実行し、結果を(完了順ではなく)渡した順で返す。"""
    results: dict[int, T] = {}

    def run(index: int, call: Callable[[], T]) -> None:
        results[index] = call()

    threads = [
        threading.Thread(target=run, args=(index, call), daemon=True)
        for index, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert len(results) == len(calls), "a concurrent call did not finish"
    return [results[index] for index in range(len(calls))]
