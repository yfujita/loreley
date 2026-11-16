"""Repository の設定。値は仮値で、設定可能(`config.py` が詰める。architecture 11章)。"""

from dataclasses import dataclass

from loreley_crawler.infrastructure.opensearch.repository import LIST_MAX_SIZE


@dataclass(frozen=True)
class RepositorySettings:
    """全件走査とバルク削除の値。既定値は architecture 11章の仮値。

    - `scan_page_size`: 全件走査の 1 ページの件数(`LIST_MAX_SIZE` = OpenSearch の
      `max_result_window` 以下)
    - `scan_pit_keep_alive_seconds`: PIT の保持時間(1 ページを処理する間、保持できる長さ)
    - `scan_request_timeout_seconds`: 全件走査の検索 1 回のタイムアウト。通常の読み書きより
      長くしてよい(architecture 11章では空欄の仮値。module CM-U-6)
    - `bulk_delete_batch_size`: ID のバルク削除 1 回の件数
    """

    scan_page_size: int = 1_000
    scan_pit_keep_alive_seconds: int = 60
    scan_request_timeout_seconds: float = 60.0
    bulk_delete_batch_size: int = 1_000

    def __post_init__(self) -> None:
        if not 1 <= self.scan_page_size <= LIST_MAX_SIZE:
            raise ValueError(f"scan_page_size must be between 1 and {LIST_MAX_SIZE}")
        if self.scan_pit_keep_alive_seconds < 1:
            raise ValueError("scan_pit_keep_alive_seconds must be at least 1")
        if self.scan_request_timeout_seconds <= 0:
            raise ValueError("scan_request_timeout_seconds must be positive")
        if self.bulk_delete_batch_size < 1:
            raise ValueError("bulk_delete_batch_size must be at least 1")
