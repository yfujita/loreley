"""連続スキップの計数(architecture 6.3。CA-P-20)。

取得段階と登録段階を別々に数える。取得段階は取得の成功、登録段階は Indexer が `status: ok` を
返したことでリセットする。`oversize` と識別子エラーは、ここを呼ばない(計数もリセットもしない)。
"""

from loreley_crawler.jobs import SkipStage


class ConsecutiveSkipCounter:
    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        self._limit = limit
        self._consecutive_skips = {stage: 0 for stage in SkipStage}

    @property
    def limit(self) -> int:
        return self._limit

    def record_skip(self, stage: SkipStage) -> bool:
        """`stage` のスキップを数え、連続が規定の件数に達したら True を返す。"""
        self._consecutive_skips[stage] += 1
        return self._consecutive_skips[stage] >= self._limit

    def record_success(self, stage: SkipStage) -> None:
        self._consecutive_skips[stage] = 0
