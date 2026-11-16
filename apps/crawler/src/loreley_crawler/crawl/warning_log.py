"""ジョブ記録の `warnings`(architecture 3.3.1・7.5〜7.7)。

警告は、固定のコード(`code`)と、固定の項目(件数・上限・前回のジョブ ID など)で表す。
文書の本文・認証情報・Indexer の応答の文字列は載せない(R11)。識別子エラーの例は、
共通処理が表示用に整形した `external_id` を載せる(architecture 7.7)。
件数に上限を置き、超えた分は捨てる(`warnings_max_entries`)。

警告は観測のためだけで、ジョブの status・終了通知・削除の挙動を変えない。
"""

from typing import Any

# 警告のコード(固定。名称は案)。
INVALID_EXTERNAL_ID = "invalid_external_id"
ENUMERATED_ZERO_AFTER_NONZERO = "enumerated_zero_after_nonzero"
FINISH_ID_LIST_OVER_THRESHOLD = "finish_id_list_over_threshold"
FINISH_NOT_ACKNOWLEDGED = "finish_not_acknowledged"
POLLING_ABORTED = "polling_aborted"


class WarningLog:
    def __init__(self, max_entries: int) -> None:
        self._max_entries = max_entries
        self._entries: list[dict[str, Any]] = []

    def add(self, code: str, **details: Any) -> None:
        """同じコードの警告は 1 つだけ残す(2 回目以降は何もしない)。"""
        if len(self._entries) >= self._max_entries:
            return
        if any(entry["code"] == code for entry in self._entries):
            return
        self._entries.append({"code": code, **details})

    def to_record(self) -> list[dict[str, Any]]:
        """ジョブ記録の `warnings`(JSON の型)。"""
        return [dict(entry) for entry in self._entries]
