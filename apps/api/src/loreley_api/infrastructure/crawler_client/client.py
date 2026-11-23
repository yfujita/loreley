"""Crawler クライアントの入口(Protocol)と返り値の型(D 4.9。C 4章)。

入口は Crawler の 6 API に 1 対 1 の操作だけで、任意のパス・メソッドを受け取る汎用の入口は
持たない(C 2.3)。操作は例外を漏らさず、4 種類の返り値のどれかを返す。ブロッキングの呼び出しなので、
`services` は `BlockingRunner` の `crawler` の枠で呼ぶ(R9)。

返り値は、Crawler の応答の**解釈の結果**だけを持つ。Crawler の `message` は、`config_invalid`
以外では持たない(B 9.1。入力値を含みうるため)。
"""

from dataclasses import dataclass
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class CrawlerSourceSettings:
    """登録・更新で Crawler に送る、データソースの設定(Crawler の単位。B 9.2.4)。"""

    connector_config: dict[str, Any]
    ttl_seconds: int
    # 0〜1 の割合。Admin API が `ratio_threshold_percent` を十進数で換算した値(B 2.8)。
    ratio_threshold: float
    min_delete_count: int
    schedule_cron: str | None


@dataclass(frozen=True)
class CrawlerSucceeded:
    """期待どおりの 2xx。`body` は JSON のオブジェクト(DTO への変換は呼び出し側)。"""

    status: int
    body: dict[str, Any]


@dataclass(frozen=True)
class ConfigViolation:
    """`config_invalid` の `message` を分解した結果(B 2.5)。"""

    # Admin API のリクエストの項目名(`connector_config.root` など)。
    field: str
    # Connector が定める違反の種類の固定文。
    detail: str


@dataclass(frozen=True)
class ConfigInvalidMessage:
    """Crawler の `config_invalid`(400)の `message` と、その分解の結果。"""

    crawler_message: str
    # `None` は分解できなかった(形式が違う・切り詰めの疑い。B 2.5)。
    violation: ConfigViolation | None


@dataclass(frozen=True)
class CrawlerRejected:
    """Crawler が返したエラー(`{"error": {"code", ...}}` の形の 4xx・5xx)。

    どの `code` を想定内とするかは、呼び出し側(`crawler_mapping`)が API ごとに決める。
    """

    status: int
    code: str
    details: dict[str, Any] | None
    # `code=config_invalid` のときだけ。
    config_invalid: ConfigInvalidMessage | None


# `before_send`: 送る前の失敗(再試行してよい)。`after_send`: 送った後に応答が来ない(結果不明)。
TransportPhase = Literal["before_send", "after_send"]
TransportFailureReason = Literal[
    "name_resolution",
    "connection_failed",
    "connect_timeout",
    "tls_failure",
    "response_timeout",
    "connection_lost",
    "http_error",
]


@dataclass(frozen=True)
class CrawlerTransportFailed:
    phase: TransportPhase
    reason: TransportFailureReason


ContractViolationReason = Literal[
    "redirect",
    "unexpected_status",
    "body_too_large",
    "malformed_body",
    "malformed_error",
]


@dataclass(frozen=True)
class CrawlerContractViolation:
    """契約外の応答(502 の元)。操作は実行済みかもしれない。"""

    reason: ContractViolationReason
    status: int


type CrawlerReply = CrawlerSucceeded | CrawlerRejected | CrawlerContractViolation
type CrawlerResult = CrawlerReply | CrawlerTransportFailed


class CrawlerClient(Protocol):
    def register_source(
        self, source_id: str, connector_type: str, settings: CrawlerSourceSettings
    ) -> CrawlerResult: ...

    def update_source(self, source_id: str, settings: CrawlerSourceSettings) -> CrawlerResult: ...

    def start_delete_job(self, source_id: str) -> CrawlerResult: ...

    def start_crawl(
        self, source_id: str, *, force_delete: bool, rewrite_mode: bool
    ) -> CrawlerResult: ...

    def cancel_job(self, job_id: str) -> CrawlerResult: ...

    def release_lock(self, source_id: str) -> CrawlerResult: ...
