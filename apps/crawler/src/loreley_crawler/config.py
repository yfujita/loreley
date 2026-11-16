"""設定の読み込みと、起動時の整合性検査(module 3章。CM-P-17・CM-P-25)。

各モジュールは `config.py` に依存しない。値は `main.py` がここから取り出し、各モジュールが
定義する frozen な設定 dataclass に詰めて渡す。

- `Settings`: 環境変数(`LORELEY_CRAWLER_` 接頭辞)を読む pydantic-settings。環境変数名は
  フィールド名の大文字(例 `LORELEY_CRAWLER_OWNER`)。既定値は、各モジュールの設定 dataclass の
  既定値(architecture 11章の仮値)を使い、二重に持たない。
- `load_config()`: `Settings` を読み、各モジュールの設定 dataclass に詰めて `CrawlerConfig` にする。
  **起動順の先頭**(OpenSearch への接続・起動時の回復・スレッド・HTTP の前)で `main.py` が呼ぶ。
  設定の不備・整合性検査の違反は `ConfigError` で、`main.py` は捕捉せずに異常終了させる。
  `ConfigError` の文言は、環境変数名・項目名・固定文・数値だけで、値(秘密を含む)を載せない。
- 整合性検査(architecture 10章。CA-P-55): Crawler の仮値と Indexer の上限(`check_size_limits`)、
  ハートビートの停止の待ちとハートビート専用クライアントのタイムアウト(`check_heartbeat_timing`)。
  Indexer の上限が未設定のときの扱いは CM-U-9 の仮置き(a): 警告して、その項目の検査を省略する
  (`CrawlerConfig.unchecked_indexer_limits`。警告は `warn_about_unchecked_indexer_limits`)。
  Indexer の上限は `LORELEY_CRAWLER_INDEXER_` 接頭辞つきの名前で読む(Crawler 自身の
  `LORELEY_CRAWLER_MAX_RAW_BYTES` などと区別するため)。
"""

import dataclasses
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, tzinfo
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BeforeValidator, Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from loreley_crawler.common.retry import RetryPolicy
from loreley_crawler.connectors.registry import FileSystemSettings
from loreley_crawler.crawl import CrawlSettings
from loreley_crawler.documents import DocumentsSettings
from loreley_crawler.infrastructure.indexer_client import (
    ApiTimeouts,
    IndexerClientConfig,
)
from loreley_crawler.infrastructure.opensearch import (
    OpenSearchConnectionConfig,
    RepositorySettings,
)
from loreley_crawler.jobs import HeartbeatSettings, JobsSettings
from loreley_crawler.scheduler import SchedulerSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CrawlerSizeLimits:
    """検査に使う Crawler 自身の仮値(architecture 11章の項目)。チャンクの件数は対象外。"""

    max_raw_bytes: int
    batch_max_documents: int
    batch_max_raw_bytes: int
    # 1 回の `last-seen` の要請の `document_ids` の最大件数(チャンクの件数とは別の項目)。
    last_seen_max_ids: int
    # 終了通知の ID 一覧(`skipped_document_ids` + `oversize_document_ids`)の警告閾値。
    finish_id_list_warning_threshold: int


@dataclass(frozen=True)
class IndexerLimits:
    """Indexer の上限。項目名は Indexer の設定名(`LORELEY_INDEXER_` を除いた名前)の小文字。

    `None` は、Crawler に渡されていない(未設定)ことを表す。
    """

    max_raw_bytes: int | None = None
    max_batch_documents: int | None = None
    max_batch_bytes: int | None = None
    max_request_body_bytes: int | None = None
    max_last_seen_ids: int | None = None
    skip_oversize_id_limit: int | None = None


@dataclass(frozen=True)
class LimitViolation:
    """`item` の値 `value` が、`limit_name` の値 `limit_value` を超えている。

    すべて整数と固定の名前で、ログに出してよい(architecture 10章: 項目名・両方の値を出す)。
    """

    item: str
    value: int
    limit_name: str
    limit_value: int

    def describe(self) -> str:
        return f"{self.item}={self.value} exceeds {self.limit_name}={self.limit_value}"


@dataclass(frozen=True)
class LimitCheckResult:
    violations: tuple[LimitViolation, ...]
    # 未設定のため、検査を省略した Indexer の設定名(`MAX_RAW_BYTES` など)。
    unchecked_limits: tuple[str, ...]


def check_size_limits(crawler: CrawlerSizeLimits, indexer: IndexerLimits) -> LimitCheckResult:
    """Crawler の値が Indexer の上限(と自分の値どうしの関係)を超えていないか検査する。

    検査の内容は architecture 10章のとおり(Crawler の値 <= Indexer の上限)。
    - バッチの原本のバイト数は、base64 後(4/3 倍。切り上げ)も `MAX_REQUEST_BODY_BYTES` 以下。
    - `max_raw_bytes` <= バッチの原本のバイト数(原本 1 件がバッチに入らないと、上限内の文書が
      登録できないため。自分の値どうしの検査で、Indexer の値に依存しない)。
    """
    batch_raw_bytes_in_base64 = _ceil_div(crawler.batch_max_raw_bytes * 4, 3)
    checks = [
        ("max_raw_bytes", crawler.max_raw_bytes, "MAX_RAW_BYTES", indexer.max_raw_bytes),
        (
            "batch_max_documents",
            crawler.batch_max_documents,
            "MAX_BATCH_DOCUMENTS",
            indexer.max_batch_documents,
        ),
        (
            "batch_max_raw_bytes",
            crawler.batch_max_raw_bytes,
            "MAX_BATCH_BYTES",
            indexer.max_batch_bytes,
        ),
        (
            "batch_max_raw_bytes_in_base64",
            batch_raw_bytes_in_base64,
            "MAX_REQUEST_BODY_BYTES",
            indexer.max_request_body_bytes,
        ),
        (
            "last_seen_max_ids",
            crawler.last_seen_max_ids,
            "MAX_LAST_SEEN_IDS",
            indexer.max_last_seen_ids,
        ),
        (
            "finish_id_list_warning_threshold",
            crawler.finish_id_list_warning_threshold,
            "SKIP_OVERSIZE_ID_LIMIT",
            indexer.skip_oversize_id_limit,
        ),
        # 自分の値どうし。上限は Indexer ではなく Crawler の別の項目。
        (
            "max_raw_bytes",
            crawler.max_raw_bytes,
            "batch_max_raw_bytes",
            crawler.batch_max_raw_bytes,
        ),
    ]
    violations = tuple(
        LimitViolation(item, value, limit_name, limit_value)
        for item, value, limit_name, limit_value in checks
        if limit_value is not None and value > limit_value
    )
    return LimitCheckResult(violations, _unset_limit_names(indexer))


def _unset_limit_names(indexer: IndexerLimits) -> tuple[str, ...]:
    return tuple(
        field.name.upper()
        for field in dataclasses.fields(indexer)
        if getattr(indexer, field.name) is None
    )


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


# --- ハートビートの時間の整合性検査 ---

# 停止の待ちは「更新 1 回 + 読み直し 1 回」ぶんのタイムアウトに収まる長さにする(module 4.4)。
HEARTBEAT_STOP_TIMEOUT_FACTOR = 2


@dataclass(frozen=True)
class TimingViolation:
    """`item` の秒数 `value_seconds` が、`limit_name` の秒数 `limit_seconds` を下回っている。"""

    item: str
    value_seconds: float
    limit_name: str
    limit_seconds: float

    def describe(self) -> str:
        return f"{self.item}={self.value_seconds} is below {self.limit_name}={self.limit_seconds}"


def check_heartbeat_timing(
    heartbeat: HeartbeatSettings, heartbeat_request_timeout_seconds: float
) -> tuple[TimingViolation, ...]:
    """ハートビートの停止の待ち上限 >= ハートビート専用クライアントのタイムアウトの 2 倍。

    停止の待ちが短いと、進行中の更新(タイムアウトまで待つ)と読み直しが終わる前に待ちを打ち切り、
    正常な停止も「喪失」として扱ってロック文書を削除できなくなる(0010 §5)。
    関係式(再試行間隔 < 更新間隔 < リース)は `HeartbeatSettings` が構築時に検査する。
    """
    required_seconds = HEARTBEAT_STOP_TIMEOUT_FACTOR * heartbeat_request_timeout_seconds
    if heartbeat.stop_timeout_seconds >= required_seconds:
        return ()
    return (
        TimingViolation(
            "heartbeat_stop_timeout_seconds",
            heartbeat.stop_timeout_seconds,
            f"{HEARTBEAT_STOP_TIMEOUT_FACTOR} * os_heartbeat_request_timeout_seconds",
            required_seconds,
        ),
    )


# --- 設定の読み込み ---

ENV_PREFIX = "LORELEY_CRAWLER_"
MAX_REPORTED_SETTING_ERRORS = 10
INVALID_OPENSEARCH_MESSAGE = "invalid OpenSearch settings"
SAME_INDEX_NAME_MESSAGE = "sources_index_name and jobs_index_name must differ"


class ConfigError(Exception):
    """起動を続けられない設定の不備・整合性検査の違反。

    メッセージは、環境変数名・項目名・固定文・数値だけ(値は載せない。秘密を含むため)。
    """


def _normalize_log_level(value: object) -> object:
    """`info` のような小文字も受け付ける(環境変数の書き方の違いで起動に失敗させない)。"""
    return value.upper() if isinstance(value, str) else value


LogLevel = Annotated[
    Literal["DEBUG", "INFO", "WARNING", "ERROR"], BeforeValidator(_normalize_log_level)
]


class Settings(BaseSettings):
    """環境変数 `LORELEY_CRAWLER_<フィールド名の大文字>`。

    値の範囲は、各モジュールの設定 dataclass が検査する(`build_config`)。
    """

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, extra="ignore", frozen=True)

    # --- HTTP の待ち受けとログ(設計書に規定がなく、運用上の既定) ---
    # 既定は手元の確認用の 127.0.0.1。コンテナでは、Admin API から届くよう 0.0.0.0 を指定する。
    http_host: str = "127.0.0.1"
    http_port: int = Field(8001, ge=1, le=65_535)
    log_level: LogLevel = "INFO"

    # --- owner(CA-P-3。必須。再起動の前後で同じ値の、Crawler の安定した ID) ---
    owner: str

    # --- OpenSearch(Store 層)。索引は `opensearch-init` が作る ---
    opensearch_url: str
    opensearch_username: str | None = None
    opensearch_password: SecretStr | None = None
    opensearch_verify_certs: bool = True
    opensearch_ca_certs_path: str | None = None
    os_store_request_timeout_seconds: float = (
        OpenSearchConnectionConfig.store_request_timeout_seconds
    )
    os_heartbeat_request_timeout_seconds: float = (
        OpenSearchConnectionConfig.heartbeat_request_timeout_seconds
    )
    # `loreley-jobs` の索引名は、Indexer の `LORELEY_INDEXER_JOBS_INDEX_NAME` と同じ値にする。
    sources_index_name: str = Field("loreley-sources", min_length=1)
    jobs_index_name: str = Field("loreley-jobs", min_length=1)
    # Repository(全件走査・バルク削除)
    scan_page_size: int = RepositorySettings.scan_page_size
    scan_pit_keep_alive_seconds: int = RepositorySettings.scan_pit_keep_alive_seconds
    scan_request_timeout_seconds: float = RepositorySettings.scan_request_timeout_seconds
    bulk_delete_batch_size: int = RepositorySettings.bulk_delete_batch_size

    # --- Indexer の URL とタイムアウト(architecture 11章) ---
    indexer_url: str
    indexer_connect_timeout_seconds: float = IndexerClientConfig.connect_timeout_seconds
    indexer_start_timeout_seconds: float = ApiTimeouts.start
    indexer_finish_timeout_seconds: float = ApiTimeouts.finish
    indexer_status_timeout_seconds: float = ApiTimeouts.status
    indexer_last_seen_timeout_seconds: float = ApiTimeouts.last_seen
    indexer_register_batch_timeout_seconds: float = ApiTimeouts.register_batch
    indexer_discard_deletions_timeout_seconds: float = ApiTimeouts.discard_deletions
    indexer_delete_documents_timeout_seconds: float = ApiTimeouts.delete_documents
    indexer_delete_deletion_records_timeout_seconds: float = ApiTimeouts.delete_deletion_records

    # --- Indexer の上限(起動時の整合性検査用。CM-U-9 の仮置き(a))---
    # Indexer の設定名(`LORELEY_INDEXER_` を除いた名前)に対応する。compose で Indexer と同じ値を
    # 渡す。未設定の項目は、警告して検査を省略する。
    indexer_max_raw_bytes: int | None = None
    indexer_max_batch_documents: int | None = None
    indexer_max_batch_bytes: int | None = None
    indexer_max_request_body_bytes: int | None = None
    indexer_max_last_seen_ids: int | None = None
    indexer_skip_oversize_id_limit: int | None = None

    # --- リトライ(architecture 11章。ジッタの割合は実装者の仮値) ---
    retry_max_attempts: int = 3
    retry_initial_backoff_seconds: float = 1.0
    retry_backoff_multiplier: float = 2.0
    retry_max_backoff_seconds: float = 30.0
    retry_jitter_ratio: float = 0.2

    # --- jobs・ハートビート・Scheduler ---
    runner_scan_interval_seconds: float = JobsSettings.runner_scan_interval_seconds
    admitting_lock_grace_seconds: float = JobsSettings.admitting_lock_grace_seconds
    heartbeat_lease_seconds: float = HeartbeatSettings.lease_seconds
    heartbeat_interval_seconds: float = HeartbeatSettings.interval_seconds
    heartbeat_retry_interval_seconds: float = HeartbeatSettings.retry_interval_seconds
    heartbeat_stop_timeout_seconds: float = HeartbeatSettings.stop_timeout_seconds
    scheduler_check_interval_seconds: float = SchedulerSettings.check_interval_seconds
    # `schedule_cron` を解釈するタイムゾーン(IANA 名。全ソース共通。未設定は UTC)。
    timezone: str = "UTC"

    # --- crawl ---
    chunk_size: int = CrawlSettings.chunk_size
    last_seen_max_ids: int = CrawlSettings.last_seen_max_ids
    batch_max_documents: int = CrawlSettings.batch_max_documents
    batch_max_raw_bytes: int = CrawlSettings.batch_max_raw_bytes
    consecutive_skip_limit: int = CrawlSettings.consecutive_skip_limit
    invalid_id_example_limit: int = CrawlSettings.invalid_id_example_limit
    finish_id_list_warning_threshold: int = CrawlSettings.finish_id_list_warning_threshold
    polling_interval_seconds: float = CrawlSettings.polling_interval_seconds
    polling_timeout_seconds: float = CrawlSettings.polling_timeout_seconds
    polling_max_consecutive_failures: int = CrawlSettings.polling_max_consecutive_failures
    warnings_max_entries: int = CrawlSettings.warnings_max_entries
    previous_crawl_lookup_jobs: int = CrawlSettings.previous_crawl_lookup_jobs

    # --- documents・FS Connector ---
    max_raw_bytes: int = DocumentsSettings.max_raw_bytes
    max_enumerated_documents: int = DocumentsSettings.max_enumerated_documents
    display_max_chars: int = DocumentsSettings.display_max_chars
    fs_max_patterns: int = FileSystemSettings.max_patterns
    fs_max_pattern_bytes: int = FileSystemSettings.max_pattern_bytes
    fs_read_chunk_bytes: int = FileSystemSettings.read_chunk_bytes
    fs_message_path_max_chars: int = FileSystemSettings.message_path_max_chars


@dataclass(frozen=True)
class CrawlerConfig:
    """検証済みの設定。`main.py` が各モジュールの組み立てに渡す(module 3章)。

    秘密(OpenSearch のパスワード)は `opensearch.password`(`repr` に出ない)と `log_secrets`
    (`repr` に出ない。`configure_logging` の `secrets` に渡す)だけが持つ。
    """

    http_host: str
    http_port: int
    log_level: str
    log_secrets: tuple[str, ...] = field(repr=False)
    opensearch: OpenSearchConnectionConfig
    sources_index_name: str
    jobs_index_name: str
    repository: RepositorySettings
    indexer: IndexerClientConfig
    retry_policy: RetryPolicy
    jobs: JobsSettings
    scheduler: SchedulerSettings
    crawl: CrawlSettings
    documents: DocumentsSettings
    file_system: FileSystemSettings
    # 未設定のため、整合性検査を省略した Indexer の設定名(`MAX_RAW_BYTES` など)。
    unchecked_indexer_limits: tuple[str, ...]


def load_config() -> CrawlerConfig:
    """環境変数を読み、検証する。不備は、値を含まない `ConfigError` で起動に失敗する。"""
    try:
        settings = Settings()  # 必須の項目は環境変数から読む(足りなければ起動に失敗する)
    except ValidationError as error:
        description = describe_settings_errors(error)
    else:
        return build_config(settings)
    # `except` の外で送出し、元の例外(入力値を持つ)を `__context__` に連鎖させない。
    raise ConfigError(f"invalid settings: {description}")


def describe_settings_errors(error: ValidationError) -> str:
    """設定の検証エラーを、環境変数名と検証の種別(`type`)だけで表す(R11)。

    pydantic の表示(`str(error)`)は、入力の環境変数の辞書(`OPENSEARCH_PASSWORD` を含む)や
    不正な値(`input_value`)をそのまま出す。`SecretStr` でも防げないため、`input`・`ctx`・
    本文(`msg`)は使わない。
    """
    errors = error.errors(include_url=False, include_context=False, include_input=False)
    reported = [
        f"{_env_name(item['loc'])}: {item['type']}" for item in errors[:MAX_REPORTED_SETTING_ERRORS]
    ]
    omitted_count = len(errors) - len(reported)
    if omitted_count > 0:
        reported.append(f"... and {omitted_count} more")
    return "; ".join(reported)


def _env_name(location: tuple[int | str, ...]) -> str:
    return f"{ENV_PREFIX}{str(location[0]).upper()}" if location else "settings"


def build_config(settings: Settings) -> CrawlerConfig:
    """各モジュールの設定 dataclass に詰め、整合性検査を行う。不備・違反は `ConfigError`。"""
    heartbeat = _construct("heartbeat", lambda: _pick(settings, HeartbeatSettings, "heartbeat_{}"))
    documents = _construct("documents", lambda: _pick(settings, DocumentsSettings, "{}"))
    crawl = _construct("crawl", lambda: _pick(settings, CrawlSettings, "{}"))
    opensearch = _construct("OpenSearch", lambda: _opensearch_connection(settings))
    limit_check = check_size_limits(
        _crawler_size_limits(documents, crawl), _pick(settings, IndexerLimits, "indexer_{}")
    )
    config = CrawlerConfig(
        http_host=settings.http_host,
        http_port=settings.http_port,
        log_level=settings.log_level,
        log_secrets=_secrets_of(settings),
        opensearch=opensearch,
        sources_index_name=settings.sources_index_name,
        jobs_index_name=settings.jobs_index_name,
        repository=_construct("repository", lambda: _pick(settings, RepositorySettings, "{}")),
        indexer=_construct("Indexer", lambda: _indexer_client_config(settings)),
        retry_policy=_construct("retry", lambda: _pick(settings, RetryPolicy, "retry_{}")),
        jobs=_construct(
            "jobs",
            lambda: JobsSettings(
                owner=settings.owner,
                heartbeat=heartbeat,
                runner_scan_interval_seconds=settings.runner_scan_interval_seconds,
                admitting_lock_grace_seconds=settings.admitting_lock_grace_seconds,
            ),
        ),
        scheduler=_construct(
            "scheduler",
            lambda: SchedulerSettings(
                check_interval_seconds=settings.scheduler_check_interval_seconds,
                timezone=_load_timezone(settings.timezone),
            ),
        ),
        crawl=crawl,
        documents=documents,
        file_system=_construct("file system", lambda: _pick(settings, FileSystemSettings, "fs_{}")),
        unchecked_indexer_limits=limit_check.unchecked_limits,
    )
    violations = [
        *(violation.describe() for violation in limit_check.violations),
        *(
            violation.describe()
            for violation in check_heartbeat_timing(
                heartbeat, opensearch.heartbeat_request_timeout_seconds
            )
        ),
    ]
    if settings.sources_index_name == settings.jobs_index_name:
        violations.append(SAME_INDEX_NAME_MESSAGE)
    if violations:
        raise ConfigError(f"startup consistency check failed: {'; '.join(violations)}")
    return config


def warn_about_unchecked_indexer_limits(config: CrawlerConfig) -> None:
    """未設定の Indexer の上限(検査を省略した項目)を警告する。ログの設定の後に呼ぶ。"""
    if not config.unchecked_indexer_limits:
        return
    logger.warning(
        "the consistency check was skipped for the Indexer limits that are not set "
        "(set %sINDEXER_<NAME> to the same values as the Indexer): %s",
        ENV_PREFIX,
        ", ".join(config.unchecked_indexer_limits),
    )


def _pick[T](settings: Settings, dataclass_type: type[T], template: str) -> T:
    """設定 dataclass の項目名(`template` に当てはめた名前)の `Settings` の値を集めて作る。

    `Settings` の項目と dataclass の項目の対応を、名前の規則 1 つで表す(項目を足したときに、
    片方だけの更新に気づけるよう、対応は `tests/test_config_loading.py` が検査する)。
    """
    values = {
        item.name: getattr(settings, template.format(item.name))
        for item in dataclasses.fields(dataclass_type)
    }
    return dataclass_type(**values)


def _construct[T](section: str, build: Callable[[], T]) -> T:
    """設定 dataclass の検査(`ValueError`)を、固定文の `ConfigError` にする。

    各 dataclass のメッセージは値を含めない作りだが、ライブラリの例外は値を含みうるので、
    `UnicodeError`(孤立サロゲートなど)は型名だけにする。
    """
    try:
        return build()
    except ValueError as error:
        reason = type(error).__name__ if isinstance(error, UnicodeError) else str(error)
    # `except` の外で送出し、元の例外を `__context__` に連鎖させない。
    raise ConfigError(f"invalid {section} settings: {reason}")


def _load_timezone(name: str) -> tzinfo:
    """IANA 名からタイムゾーンを得る。不正な名前は、値を載せない `ValueError`(`_construct` が変換)。

    `UTC`(既定)は OS のタイムゾーンデータ(tzdata)を使わず、標準ライブラリの `UTC` を返す。

    `ZoneInfo` の例外は名前を含む(`ValueError` は不正なパスの文字列そのもの)ので、固定文にする。
    """
    if name == "UTC":
        return UTC
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        pass
    # `except` の外で送出し、元の例外(名前を持つ)を `__context__` に連鎖させない。
    raise ValueError("timezone must be an IANA time zone name")


def _opensearch_connection(settings: Settings) -> OpenSearchConnectionConfig:
    password = settings.opensearch_password
    return OpenSearchConnectionConfig(
        url=settings.opensearch_url,
        username=settings.opensearch_username,
        password=password.get_secret_value() if password is not None else None,
        verify_certs=settings.opensearch_verify_certs,
        ca_certs_path=settings.opensearch_ca_certs_path,
        store_request_timeout_seconds=settings.os_store_request_timeout_seconds,
        heartbeat_request_timeout_seconds=settings.os_heartbeat_request_timeout_seconds,
    )


def _indexer_client_config(settings: Settings) -> IndexerClientConfig:
    return IndexerClientConfig(
        base_url=settings.indexer_url,
        timeouts=_pick(settings, ApiTimeouts, "indexer_{}_timeout_seconds"),
        connect_timeout_seconds=settings.indexer_connect_timeout_seconds,
    )


def _crawler_size_limits(documents: DocumentsSettings, crawl: CrawlSettings) -> CrawlerSizeLimits:
    return CrawlerSizeLimits(
        max_raw_bytes=documents.max_raw_bytes,
        batch_max_documents=crawl.batch_max_documents,
        batch_max_raw_bytes=crawl.batch_max_raw_bytes,
        last_seen_max_ids=crawl.last_seen_max_ids,
        finish_id_list_warning_threshold=crawl.finish_id_list_warning_threshold,
    )


def _secrets_of(settings: Settings) -> tuple[str, ...]:
    password = settings.opensearch_password
    return (password.get_secret_value(),) if password is not None else ()
