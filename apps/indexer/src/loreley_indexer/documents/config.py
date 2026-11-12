"""登録・`last-seen` の設定(`config.py` が `Settings` から詰める。module 3章)。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RegistrationConfig:
    max_raw_bytes: int  # 原本サイズの上限。超えたら抽出せず `oversize`(plan 案1)
    write_conflict_max_rereads: int  # 409 のときの読み直しの上限(R8)
    max_last_seen_ids: int  # `last-seen` 1 リクエストの ID の件数の上限
    summary_enabled: bool  # False なら新しい本文の文書は `summary_status=disabled` で書く

    def __post_init__(self) -> None:
        positive_counts = {
            "max_raw_bytes": self.max_raw_bytes,
            "write_conflict_max_rereads": self.write_conflict_max_rereads,
            "max_last_seen_ids": self.max_last_seen_ids,
        }
        for name, value in positive_counts.items():
            if value < 1:
                raise ValueError(f"{name} must be at least 1")
