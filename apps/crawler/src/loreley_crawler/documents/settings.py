"""`documents` の設定。値は仮値で、設定可能(`config.py` が詰める。architecture 11章)。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentsSettings:
    """既定値は architecture 11章の仮値。

    - `max_raw_bytes`: 原本 1 件の上限(`fetch` の `max_bytes`。Indexer の `MAX_RAW_BYTES` 以下)
    - `max_enumerated_documents`: 重複除去・衝突検出のために保持する ID の件数の上限。超えたら
      列挙を失敗させる(保持できない規模は MVP では扱わない。CA-P-26)
    - `display_max_chars`: 説明文・`warnings` に入れる `external_id` の表示の長さの上限
    """

    max_raw_bytes: int = 20 * 1024 * 1024
    max_enumerated_documents: int = 500_000
    display_max_chars: int = 200

    def __post_init__(self) -> None:
        if self.max_raw_bytes < 0:
            raise ValueError("max_raw_bytes must not be negative")
        if self.max_enumerated_documents < 1:
            raise ValueError("max_enumerated_documents must be at least 1")
        if self.display_max_chars < 1:
            raise ValueError("display_max_chars must be at least 1")
