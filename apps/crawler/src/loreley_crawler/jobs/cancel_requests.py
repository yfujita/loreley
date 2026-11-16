"""`running` のジョブへの取り消し要求の、メモリ上のレジストリ(architecture 4.7。CA-P-44。CM-P-15)。

HTTP ハンドラのスレッド(取り消し)が書き、Job Runner のスレッド(確認点)が読むので、排他で守る。
`main.py` が 1 つ作り、`JobCancellation` と Job Runner に渡す(同じプロセスで動くことが前提)。
同じ要求が重なっても 1 つ(集合)で、結果は 1 回と同じ。Crawler が再起動すると消えるが、
`running` のジョブは起動時の回復で `failed`(`crawler_restart`)になるので整合する。
"""

import threading


class CancelRequestRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._job_ids: set[str] = set()

    def request(self, job_id: str) -> None:
        with self._lock:
            self._job_ids.add(job_id)

    def is_requested(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._job_ids

    def clear(self, job_id: str) -> None:
        """ジョブが終端になったら消す。要求がなくても何もしない。"""
        with self._lock:
            self._job_ids.discard(job_id)
