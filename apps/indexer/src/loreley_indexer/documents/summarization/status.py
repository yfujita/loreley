"""要約の状態値(`search-index-v0.9.md` 2.3)。"""

from enum import StrEnum


class SummaryStatus(StrEnum):
    """`summary_status`。`failed` は、遷移させる場面が未決(U-9)のため定義しない(plan 案12)。"""

    DISABLED = "disabled"  # 要約が無効、または `extract_failed` で本文がない
    PENDING = "pending"
    GENERATED = "generated"


class SummaryOutcome(StrEnum):
    """1 件の生成依頼の処理結果。"""

    WRITTEN = "written"
    DISCARDED = "discarded"  # 文書なし・`pending` でない・ハッシュ不一致
    LEFT_PENDING = "left_pending"  # LLM・書き戻しの失敗。`pending` のまま再走査に委ねる
    PAUSED_BY_MAINTENANCE = "paused_by_maintenance"
    DISABLED = "disabled"

    @property
    def needs_rescan(self) -> bool:
        return self in {SummaryOutcome.LEFT_PENDING, SummaryOutcome.PAUSED_BY_MAINTENANCE}
