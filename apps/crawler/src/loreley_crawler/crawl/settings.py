"""`crawl` の設定。値は仮値で、設定可能(`config.py` が詰める。architecture 11章)。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CrawlSettings:
    """既定値は architecture 11章の仮値。

    - `chunk_size`: `last-seen`・取得の単位(列挙を区切る件数。Indexer の上限に縛られない)
    - `last_seen_max_ids`: 1 回の `last-seen` の `document_ids` の最大件数(Indexer の
      `MAX_LAST_SEEN_IDS` 以下。`config.py` の整合性検査の対象)
    - `batch_max_documents`・`batch_max_raw_bytes`: バッチを閉じる条件(Indexer の
      `MAX_BATCH_DOCUMENTS`・`MAX_BATCH_BYTES` 以下。同上)。保持する原本はバッチ 1 つ分まで
    - `consecutive_skip_limit`: 連続スキップの打ち切り件数(取得段階・登録段階それぞれ)
    - `invalid_id_example_limit`: 識別子エラーの例として保持する件数の上限(`warnings` 用)
    - `finish_id_list_warning_threshold`: 終了通知の ID 一覧(`skipped_document_ids` +
      `oversize_document_ids`)の件数がこれを超えたら警告する(Indexer の `SKIP_OVERSIZE_ID_LIMIT`
      以下。同上。超えると Indexer は削除の判定を `validation_failed` にする)
    - `polling_interval_seconds`・`polling_timeout_seconds`・`polling_max_consecutive_failures`:
      削除結果のポーリング(Status API)の間隔・全体の上限時間・失敗の連続回数(architecture 11章)
    - `warnings_max_entries`: ジョブ記録の `warnings` に残す警告の件数の上限(11章)
    - `previous_crawl_lookup_jobs`: 0 件列挙の警告のために読む過去のジョブの件数(11章)
    """

    chunk_size: int = 500
    last_seen_max_ids: int = 500
    batch_max_documents: int = 20
    batch_max_raw_bytes: int = 32 * 1024 * 1024
    consecutive_skip_limit: int = 20
    invalid_id_example_limit: int = 20
    finish_id_list_warning_threshold: int = 8_000
    polling_interval_seconds: float = 5.0
    polling_timeout_seconds: float = 30 * 60.0
    polling_max_consecutive_failures: int = 3
    warnings_max_entries: int = 20
    previous_crawl_lookup_jobs: int = 10

    def __post_init__(self) -> None:
        for name in (
            "chunk_size",
            "last_seen_max_ids",
            "batch_max_documents",
            "batch_max_raw_bytes",
            "consecutive_skip_limit",
            "invalid_id_example_limit",
            "finish_id_list_warning_threshold",
            "polling_max_consecutive_failures",
            "warnings_max_entries",
            "previous_crawl_lookup_jobs",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be at least 1")
        for name in ("polling_interval_seconds", "polling_timeout_seconds"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
