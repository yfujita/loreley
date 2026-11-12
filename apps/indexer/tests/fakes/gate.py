import threading


class Gate:
    """別スレッドの処理を、テストが指定する時点で止めて再開するための道具。

    止めたい側が `pass_through()` を呼び、テスト側が `wait_until_arrived()` で到達を待ち、
    状態を差し込んでから `release()` する。待ち続けてテストが固まらないよう、
    タイムアウトで例外にする。
    """

    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self._timeout_seconds = timeout_seconds
        self._arrived = threading.Event()
        self._released = threading.Event()

    def pass_through(self) -> None:
        self._arrived.set()
        if not self._released.wait(self._timeout_seconds):
            raise TimeoutError("gate was not released")

    def wait_until_arrived(self) -> None:
        if not self._arrived.wait(self._timeout_seconds):
            raise TimeoutError("gate was not reached")

    def release(self) -> None:
        self._released.set()
