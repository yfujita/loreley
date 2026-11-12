"""削除の判定・実行・ソース削除の設定(`config.py` が `Settings` から詰める。module 3章)。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DeletionConfig:
    batch_size: int  # 削除のバッチ件数(U-2)
    max_deletion_targets: int  # 削除対象のID一覧をメモリに持つ件数の上限(K47)。超えたら削除しない
    search_after_page_size: int  # 削除対象の取り込みの1ページの件数(9.8)
    poll_interval_seconds: float  # 起床通知がなくても待ち行列を走査する間隔(案2)
    poll_backoff_max_seconds: float  # 処理が連続して失敗したときの、走査の間隔の上限
    delete_error_retry_attempts: int  # 削除エラーの試行回数の上限(最初の1回を含む。4.4)
    retry_backoff_initial_seconds: float
    retry_backoff_factor: float
    retry_backoff_max_seconds: float
    write_conflict_max_rereads: (
        int  # 409 の読み直しの上限(R8)。削除結果の書き込みと文書の削除に使う
    )
    discard_max_attempts: int  # ソース削除1(破棄)の読み直し・再試行の上限(案。P7)
    delete_by_query_max_reruns: int  # ソース削除2の `delete_by_query` の再実行の上限(K48)

    def __post_init__(self) -> None:
        positive_counts = {
            "batch_size": self.batch_size,
            "max_deletion_targets": self.max_deletion_targets,
            "search_after_page_size": self.search_after_page_size,
            "delete_error_retry_attempts": self.delete_error_retry_attempts,
            "write_conflict_max_rereads": self.write_conflict_max_rereads,
            "discard_max_attempts": self.discard_max_attempts,
            "delete_by_query_max_reruns": self.delete_by_query_max_reruns,
        }
        for name, value in positive_counts.items():
            if value < 1:
                raise ValueError(f"{name} must be at least 1")
        positive_durations = {
            "poll_interval_seconds": self.poll_interval_seconds,
            "poll_backoff_max_seconds": self.poll_backoff_max_seconds,
            "retry_backoff_initial_seconds": self.retry_backoff_initial_seconds,
            "retry_backoff_max_seconds": self.retry_backoff_max_seconds,
        }
        for name, value in positive_durations.items():
            if value <= 0:
                raise ValueError(f"{name} must be greater than 0")
        if self.poll_backoff_max_seconds < self.poll_interval_seconds:
            raise ValueError("poll_backoff_max_seconds must be at least poll_interval_seconds")
        if self.retry_backoff_factor < 1:
            raise ValueError("retry_backoff_factor must be at least 1")
