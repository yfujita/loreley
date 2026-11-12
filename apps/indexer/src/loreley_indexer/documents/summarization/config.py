"""要約生成の設定(`config.py` が `Settings` から詰める。module 3章)。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SummarizationConfig:
    enabled: bool  # False なら LLM を呼ばず、要約ワーカーも動かさない(arch 7.1)
    concurrency: int  # 要約ワーカーのスレッド数(K49)
    max_attempts: int  # LLM 呼び出し・書き戻しそれぞれの試行回数の上限(arch 7.4)
    queue_size: int  # 生成依頼キューの上限。満杯なら `pending` のまま再走査に委ねる
    rescan_page_size: int
    rescan_min_interval_seconds: float  # 再走査どうしの間隔の下限(P15)
    rescan_max_interval_seconds: float  # 書き戻しに成功しない再走査が続いたときの間隔の上限
    write_conflict_max_rereads: int  # 書き戻しの 409 の読み直しの上限(R8)
    retry_backoff_initial_seconds: float
    retry_backoff_factor: float
    retry_backoff_max_seconds: float
    input_max_chars: int  # プロンプトに入れる本文の上限。LLM への入力を無制限にしない(K39)

    def __post_init__(self) -> None:
        positive_counts = {
            "concurrency": self.concurrency,
            "max_attempts": self.max_attempts,
            "queue_size": self.queue_size,
            "rescan_page_size": self.rescan_page_size,
            "write_conflict_max_rereads": self.write_conflict_max_rereads,
            "input_max_chars": self.input_max_chars,
        }
        for name, value in positive_counts.items():
            if value < 1:
                raise ValueError(f"{name} must be at least 1")
        if self.rescan_max_interval_seconds < self.rescan_min_interval_seconds:
            raise ValueError(
                "rescan_max_interval_seconds must be at least rescan_min_interval_seconds"
            )
