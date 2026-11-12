"""開始・終了通知、世代管理、起動時整理の設定(`config.py` が `Settings` から詰める。module 3章)。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LifecycleConfig:
    skip_oversize_id_limit: int  # スキップ・サイズ超過の両 ID 一覧の合算件数の上限(K34)
    write_conflict_max_rereads: int  # 受理の書き込みの 409 の読み直しの上限(R8)
    deletion_retention_count: int  # ソースごとに保持する終端状態の削除結果の件数 N(U-2)

    def __post_init__(self) -> None:
        positive_counts = {
            "skip_oversize_id_limit": self.skip_oversize_id_limit,
            "write_conflict_max_rereads": self.write_conflict_max_rereads,
            "deletion_retention_count": self.deletion_retention_count,
        }
        for name, value in positive_counts.items():
            if value < 1:
                raise ValueError(f"{name} must be at least 1")
