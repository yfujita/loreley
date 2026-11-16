"""Job Runner の起床通知(module 2.2 の共有状態 (5))。

受付が `queued` を保存したときに `notify` し、Job Runner は `wait` で、通知か走査間隔まで待つ。
`main.py` が 1 つ作り、受付と Job Runner に渡す。
"""

import threading


class RunnerWakeup:
    def __init__(self) -> None:
        self._notified = threading.Event()

    def notify(self) -> None:
        self._notified.set()

    def wait(self, timeout_seconds: float) -> bool:
        """通知か `timeout_seconds` まで待つ。通知で戻ったら True。

        戻る前に通知を消すので、次の通知は取りこぼさない。通知が消える前に届いた分は、戻った後の
        走査が、保存済みの `queued` を見つけるので失われない。
        """
        was_notified = self._notified.wait(timeout_seconds)
        self._notified.clear()
        return was_notified
