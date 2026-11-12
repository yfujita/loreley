"""設定の読み込み(環境変数 `LORELEY_INDEXER_*`)。

各モジュールは `config.py` に依存しない。値は `main.py` がこのクラスから取り出し、
各モジュールが定義する frozen な設定 dataclass に詰めて渡す(module 3章)。
モジュールごとの設定 dataclass とその変換メソッドは、そのモジュールを実装するフェーズで追加する。

整合の検証(設定どうしの大小関係)は、`PydanticCustomError` で検証名(`type`)を付けて送出する。
起動時のエラー表示(`main.py`)は、値を含みうる本文を出さず、フィールド名と `type` だけを出すため。

数値は設計書で未決のため仮値(arch K39、15.7)。無制限のリトライ・メモリ使用にならないよう、
すべて上限(`le`)で検証する。値の根拠は plan 0002 §4。
"""

from typing import Annotated, Literal, Self

from pydantic import BeforeValidator, Field, SecretStr, model_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict

from loreley_indexer.api import ApiConfig
from loreley_indexer.crawl_runs import DeletionConfig, LifecycleConfig
from loreley_indexer.documents import RegistrationConfig, SummarizationConfig
from loreley_indexer.documents.extraction import ExtractionConfig
from loreley_indexer.infrastructure.opensearch.connection import (
    DEFAULT_DELETE_BY_QUERY_TIMEOUT_SECONDS,
    DEFAULT_DELETIONS_INDEX_NAME,
    DEFAULT_JOBS_INDEX_NAME,
    DEFAULT_SEARCH_INDEX_NAME,
    IndexNames,
    OpenSearchConnectionConfig,
)

MIB = 1024 * 1024


def _normalize_log_level(value: object) -> object:
    """`info` のような小文字も受け付ける(環境変数の書き方の違いで起動に失敗させない)。"""
    return value.upper() if isinstance(value, str) else value


LogLevel = Annotated[
    Literal["DEBUG", "INFO", "WARNING", "ERROR"], BeforeValidator(_normalize_log_level)
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LORELEY_INDEXER_", extra="ignore", frozen=True)

    # --- HTTP の待ち受けとログ(P5。値は設計書に規定がなく、運用上の既定) ---
    # 既定は手元の確認用の 127.0.0.1。コンテナでは、Crawler から届くよう 0.0.0.0 を指定する。
    http_host: str = "127.0.0.1"
    http_port: int = Field(8000, ge=1, le=65_535)
    log_level: LogLevel = "INFO"

    # --- OpenSearch 接続 ---
    opensearch_url: str
    opensearch_username: str | None = None
    opensearch_password: SecretStr | None = None
    opensearch_verify_certs: bool = True
    opensearch_ca_certs_path: str | None = None
    os_request_timeout_seconds: float = Field(30.0, gt=0, le=300)
    os_transport_max_retries: int = Field(2, ge=0, le=5)
    # `delete_by_query` 専用のタイムアウト(通常のリクエストより長い。P4)。
    os_delete_by_query_timeout_seconds: float = Field(
        DEFAULT_DELETE_BY_QUERY_TIMEOUT_SECONDS, gt=0, le=3_600
    )

    # --- 索引名(仮名。設計書で未決) ---
    search_index_name: str = DEFAULT_SEARCH_INDEX_NAME
    deletions_index_name: str = DEFAULT_DELETIONS_INDEX_NAME
    jobs_index_name: str = DEFAULT_JOBS_INDEX_NAME

    # --- 登録・抽出のサイズ上限 ---
    max_raw_bytes: int = Field(20 * MIB, ge=1, le=100 * MIB)
    max_batch_documents: int = Field(50, ge=1, le=500)
    max_batch_bytes: int = Field(64 * MIB, ge=1, le=256 * MIB)
    max_request_body_bytes: int = Field(100 * MIB, ge=1, le=512 * MIB)
    max_content_bytes: int = Field(5 * MIB, ge=1, le=50 * MIB)
    max_last_seen_ids: int = Field(1_000, ge=1, le=10_000)

    # --- 競合・再試行 ---
    write_conflict_max_rereads: int = Field(3, ge=1, le=10)
    update_retry_on_conflict: int = Field(3, ge=0, le=10)
    delete_by_query_max_reruns: int = Field(5, ge=1, le=20)
    retry_backoff_initial_seconds: float = Field(1.0, gt=0, le=60)
    retry_backoff_factor: float = Field(2.0, ge=1, le=10)
    retry_backoff_max_seconds: float = Field(30.0, gt=0, le=300)

    # --- 削除 ---
    skip_oversize_id_limit: int = Field(10_000, ge=1, le=100_000)
    deletion_batch_size: int = Field(100, ge=1, le=1_000)
    deletion_retention_count: int = Field(20, ge=1, le=1_000)
    max_deletion_targets: int = Field(200_000, ge=1, le=2_000_000)
    search_after_page_size: int = Field(1_000, ge=1, le=10_000)
    deletion_poll_interval_seconds: float = Field(2.0, gt=0, le=60)
    deletion_poll_backoff_max_seconds: float = Field(300.0, gt=0, le=3_600)
    delete_error_retry_attempts: int = Field(3, ge=1, le=10)
    discard_max_attempts: int = Field(20, ge=1, le=100)

    # --- 要約 ---
    summary_enabled: bool = False
    summary_concurrency: int = Field(1, ge=1, le=8)
    summary_max_attempts: int = Field(3, ge=1, le=10)
    summary_queue_size: int = Field(100, ge=1, le=10_000)
    summary_rescan_page_size: int = Field(100, ge=1, le=1_000)
    summary_rescan_min_interval_seconds: float = Field(60.0, gt=0, le=3_600)
    summary_rescan_max_interval_seconds: float = Field(3_600.0, gt=0, le=86_400)
    llm_timeout_seconds: float = Field(60.0, gt=0, le=600)
    summary_input_max_chars: int = Field(30_000, ge=1, le=1_000_000)

    @model_validator(mode="after")
    def _rescan_max_interval_is_not_below_the_min(self) -> Self:
        if self.summary_rescan_max_interval_seconds < self.summary_rescan_min_interval_seconds:
            raise PydanticCustomError(
                "rescan_max_interval_below_min",
                "summary_rescan_max_interval_seconds must be at least "
                "summary_rescan_min_interval_seconds",
            )
        return self

    @model_validator(mode="after")
    def _size_limits_are_consistent(self) -> Self:
        # 原本 1 件の上限は、バッチ合計の上限以下(超える上限は意味がない)。
        if self.max_raw_bytes > self.max_batch_bytes:
            raise PydanticCustomError(
                "raw_bytes_above_batch_bytes", "max_raw_bytes must not exceed max_batch_bytes"
            )
        # base64 は元の約 4/3 倍(約 33% 増)になる。バッチ合計の上限まで届くリクエストが、
        # ボディの上限で先に拒否されないように。
        if self.max_batch_bytes * 4 > self.max_request_body_bytes * 3:
            raise PydanticCustomError(
                "batch_bytes_above_request_body_bytes",
                "max_batch_bytes in base64 (4/3 times) must not exceed max_request_body_bytes",
            )
        return self

    @model_validator(mode="after")
    def _deletion_poll_backoff_max_is_not_below_the_interval(self) -> Self:
        if self.deletion_poll_backoff_max_seconds < self.deletion_poll_interval_seconds:
            raise PydanticCustomError(
                "poll_backoff_max_below_interval",
                "deletion_poll_backoff_max_seconds must be at least deletion_poll_interval_seconds",
            )
        return self

    def api_config(self) -> ApiConfig:
        return ApiConfig(
            max_request_body_bytes=self.max_request_body_bytes,
            max_batch_documents=self.max_batch_documents,
            max_batch_bytes=self.max_batch_bytes,
            max_raw_bytes=self.max_raw_bytes,
            max_last_seen_ids=self.max_last_seen_ids,
        )

    def opensearch_connection(self) -> OpenSearchConnectionConfig:
        password = self.opensearch_password
        return OpenSearchConnectionConfig(
            url=self.opensearch_url,
            username=self.opensearch_username,
            password=password.get_secret_value() if password is not None else None,
            verify_certs=self.opensearch_verify_certs,
            ca_certs_path=self.opensearch_ca_certs_path,
            request_timeout_seconds=self.os_request_timeout_seconds,
            transport_max_retries=self.os_transport_max_retries,
            delete_by_query_timeout_seconds=self.os_delete_by_query_timeout_seconds,
        )

    def index_names(self) -> IndexNames:
        return IndexNames(
            search_index=self.search_index_name,
            deletions=self.deletions_index_name,
            jobs=self.jobs_index_name,
        )

    def extraction_config(self) -> ExtractionConfig:
        return ExtractionConfig(max_content_bytes=self.max_content_bytes)

    def registration_config(self) -> RegistrationConfig:
        return RegistrationConfig(
            max_raw_bytes=self.max_raw_bytes,
            write_conflict_max_rereads=self.write_conflict_max_rereads,
            max_last_seen_ids=self.max_last_seen_ids,
            summary_enabled=self.summary_enabled,
        )

    def summarization_config(self) -> SummarizationConfig:
        return SummarizationConfig(
            enabled=self.summary_enabled,
            concurrency=self.summary_concurrency,
            max_attempts=self.summary_max_attempts,
            queue_size=self.summary_queue_size,
            rescan_page_size=self.summary_rescan_page_size,
            rescan_min_interval_seconds=self.summary_rescan_min_interval_seconds,
            rescan_max_interval_seconds=self.summary_rescan_max_interval_seconds,
            write_conflict_max_rereads=self.write_conflict_max_rereads,
            retry_backoff_initial_seconds=self.retry_backoff_initial_seconds,
            retry_backoff_factor=self.retry_backoff_factor,
            retry_backoff_max_seconds=self.retry_backoff_max_seconds,
            input_max_chars=self.summary_input_max_chars,
        )

    def lifecycle_config(self) -> LifecycleConfig:
        return LifecycleConfig(
            skip_oversize_id_limit=self.skip_oversize_id_limit,
            write_conflict_max_rereads=self.write_conflict_max_rereads,
            deletion_retention_count=self.deletion_retention_count,
        )

    def deletion_config(self) -> DeletionConfig:
        return DeletionConfig(
            batch_size=self.deletion_batch_size,
            max_deletion_targets=self.max_deletion_targets,
            search_after_page_size=self.search_after_page_size,
            poll_interval_seconds=self.deletion_poll_interval_seconds,
            poll_backoff_max_seconds=self.deletion_poll_backoff_max_seconds,
            delete_error_retry_attempts=self.delete_error_retry_attempts,
            retry_backoff_initial_seconds=self.retry_backoff_initial_seconds,
            retry_backoff_factor=self.retry_backoff_factor,
            retry_backoff_max_seconds=self.retry_backoff_max_seconds,
            write_conflict_max_rereads=self.write_conflict_max_rereads,
            discard_max_attempts=self.discard_max_attempts,
            delete_by_query_max_reruns=self.delete_by_query_max_reruns,
        )
