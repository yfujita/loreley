"""api 層の設定(`config.py` の `Settings.api_config()` が詰める。module 3章)。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ApiConfig:
    max_request_body_bytes: int  # リクエストボディ(base64 のまま)の上限。超過は 400(案22)
    max_batch_documents: int  # バッチ登録 1 リクエストの文書数の上限
    max_batch_bytes: int  # バッチ登録の原本サイズ(デコード後)の合計の上限
    max_raw_bytes: int  # 原本 1 件のサイズ(デコード後)の上限。超えた文書は、デコードせずに渡す
    max_last_seen_ids: int  # `last-seen` 1 リクエストの文書 ID の件数の上限

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if value < 1:
                raise ValueError(f"{name} must be at least 1")
