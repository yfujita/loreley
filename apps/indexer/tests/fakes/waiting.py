import time
from collections.abc import Callable

DEFAULT_WAIT_SECONDS = 5.0


def wait_until(
    condition: Callable[[], object], timeout_seconds: float = DEFAULT_WAIT_SECONDS
) -> bool:
    """別スレッドの処理が `condition` を満たすのを待つ。満たさないまま時間切れなら False。"""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return bool(condition())
