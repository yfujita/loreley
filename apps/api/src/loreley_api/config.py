"""設定の読み込みと起動時の検証(環境変数 `LORELEY_API_*`。C 7章。module 4.1)。

各モジュールは `config.py` に依存しない。`config.py` は、設定型を持つモジュールの入口
(`admin`・`infrastructure.*`)だけを import し、検証済みの値を各モジュールの設定 dataclass に
詰めて `ApiConfig` にする。`main.py` がそれを取り出して各モジュールに渡す。

- `Settings`: 環境変数を読む pydantic-settings。環境変数名はフィールド名の大文字
  (例 `LORELEY_API_OPENSEARCH_URL`)。範囲・URL・IANA 名などの検証は、ここのバリデーターで行う。
- `load_config()`: `Settings` を読んで検証し、`ApiConfig` にする。**起動順の先頭**で `main.py` が
  呼ぶ。違反は `ConfigError` で、`main.py` は捕捉せずに異常終了させる。起動時に外部へは接続しない。

違反の表示は、フィールド名と検証の種別(pydantic の `type`。URL の違反は `url_scheme` など)だけで、
値は出さない(秘密を含みうる。`describe_settings_errors`)。
"""

from dataclasses import dataclass
from typing import Annotated, Literal, Self
from urllib.parse import SplitResult
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BeforeValidator,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict

from loreley_api.admin import AdminSettings
from loreley_api.common.urls import InvalidUrlError, check_url
from loreley_api.infrastructure.crawler_client import CrawlerClientConfig
from loreley_api.infrastructure.opensearch import IndexNames, OpenSearchConnectionConfig
from loreley_api.infrastructure.probes import HttpProbeConfig

MAX_REPORTED_SETTING_ERRORS = 10

HTTP_AND_HTTPS = frozenset({"http", "https"})
# Crawler・Indexer は内部ネットワーク前提で、TLS の検証設定(CA)を持たないので `http` だけ
# (AAA-P-41)。
HTTP_ONLY = frozenset({"http"})


class ConfigError(Exception):
    """起動を続けられない設定の違反。メッセージは固定文と、フィールド名・検証の種別だけ(値なし)。"""


def _normalize_log_level(value: object) -> object:
    """`info` のような小文字も受け付ける(環境変数の書き方の違いで起動に失敗させない)。"""
    return value.upper() if isinstance(value, str) else value


def _empty_to_none(value: object) -> object:
    """空文字は未設定として扱う(compose の `${VAR:-}` が空文字を渡すため)。"""
    return None if value == "" else value


LogLevel = Annotated[
    Literal["DEBUG", "INFO", "WARNING", "ERROR"], BeforeValidator(_normalize_log_level)
]
OptionalText = Annotated[str | None, BeforeValidator(_empty_to_none)]


def _invalid(error_type: str) -> PydanticCustomError:
    """検証エラーの種別だけを持つ例外。メッセージに値を含めない。"""
    return PydanticCustomError(error_type, "invalid setting")


def _split_url(value: str, *, allowed_schemes: frozenset[str]) -> SplitResult:
    try:
        return check_url(value, allowed_schemes=allowed_schemes)
    except InvalidUrlError as error:
        raise _invalid(f"url_{error.reason}") from None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LORELEY_API_", extra="ignore", frozen=True)

    # --- 待ち受けとログ ---
    # 既定は手元の確認用の 127.0.0.1。コンテナでは、外から届くよう 0.0.0.0 を指定する。
    host: str = "127.0.0.1"
    port: int = Field(8080, ge=1, le=65_535)
    log_level: LogLevel = "INFO"

    # --- OpenSearch ---
    opensearch_url: str
    opensearch_username: str | None = None
    opensearch_password: SecretStr | None = None
    opensearch_verify_certs: bool = True
    opensearch_ca_certs_path: str | None = None
    opensearch_request_timeout_seconds: float = Field(10.0, gt=0, le=120)
    opensearch_max_retries: int = Field(2, ge=0, le=5)
    sources_index_name: str = Field("loreley-sources", min_length=1)
    jobs_index_name: str = Field("loreley-jobs", min_length=1)
    deletions_index_name: str = Field("loreley-deletions", min_length=1)
    # 検索インデックスの**エイリアス**(opensearch-init の実体名の変数とは別物。I-90)。
    search_index_name: str = Field("loreley-documents", min_length=1)

    # --- Crawler・Indexer・死活確認 ---
    crawler_url: str
    indexer_url: str
    web_url: str
    crawler_connect_timeout_seconds: float = Field(3.0, gt=0, le=60)
    crawler_response_timeout_seconds: float = Field(60.0, gt=0, le=600)
    health_probe_timeout_seconds: float = Field(3.0, gt=0, le=30)
    dashboards_health_url: OptionalText = None
    embedding_health_url: OptionalText = None
    llm_health_url: OptionalText = None

    # --- Admin API 固有 ---
    dashboards_url: OptionalText = None
    cron_timezone: OptionalText = None
    admitting_lock_grace_seconds: float = Field(60.0, gt=0, le=3600)
    openapi_enabled: bool = False

    @field_validator(
        "opensearch_url",
        "dashboards_health_url",
        "embedding_health_url",
        "llm_health_url",
        "dashboards_url",
    )
    @classmethod
    def _validate_full_url(cls, value: str | None) -> str | None:
        # `DASHBOARDS_URL` はブラウザへ返してリンクにするので、scheme は `http`・`https` だけ。
        if value is not None:
            _split_url(value, allowed_schemes=HTTP_AND_HTTPS)
        return value

    @field_validator("crawler_url", "indexer_url", "web_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        """固定のパスを足して使うので、パス・クエリを持たない形に限る。末尾の `/` は取り除く。"""
        parts = _split_url(value, allowed_schemes=HTTP_ONLY)
        if parts.path not in ("", "/") or "?" in value:
            raise _invalid("url_path")
        return f"{parts.scheme}://{parts.netloc}"

    @field_validator("cron_timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            # `ZoneInfo` の例外は名前(不正なパスの文字列そのもの)を含むので、固定の種別にする。
            raise _invalid("timezone_invalid") from None
        return value

    @model_validator(mode="after")
    def _validate_combinations(self) -> Self:
        index_names = [
            self.sources_index_name,
            self.jobs_index_name,
            self.deletions_index_name,
            self.search_index_name,
        ]
        if len(set(index_names)) != len(index_names):
            raise _invalid("index_names_not_distinct")
        if (self.opensearch_username is None) != (self.opensearch_password is None):
            raise _invalid("opensearch_credentials_incomplete")
        return self


def describe_settings_errors(error: ValidationError) -> str:
    """設定の検証エラーを、フィールド名と検証の種別(`type`)だけで表す。

    pydantic の表示(`str(error)`)は、入力の環境変数の辞書や不正な値(`input_value`)を
    そのまま出す。`SecretStr` でも防げないため、`input`・`ctx`・本文(`msg`)は使わない。
    """
    errors = error.errors(include_url=False, include_context=False, include_input=False)
    reported = [
        f"{'.'.join(str(part) for part in item['loc']) or 'settings'}: {item['type']}"
        for item in errors[:MAX_REPORTED_SETTING_ERRORS]
    ]
    omitted_count = len(errors) - len(reported)
    if omitted_count > 0:
        reported.append(f"... and {omitted_count} more")
    return "; ".join(reported)


def load_settings() -> Settings:
    """環境変数から設定を読む。不正なら、値を含まない `ConfigError` で起動に失敗する。"""
    try:
        return Settings()
    except ValidationError as error:
        description = describe_settings_errors(error)
    # `except` の外で送出し、元の例外(入力値を持つ)を `__context__` に連鎖させない。
    raise ConfigError(f"invalid settings: {description}")


@dataclass(frozen=True)
class ApiConfig:
    """検証済みの設定。`main.py` が各モジュールの組み立てに渡す。"""

    host: str
    port: int
    log_level: str
    opensearch: OpenSearchConnectionConfig
    index_names: IndexNames
    crawler_client: CrawlerClientConfig
    http_probe: HttpProbeConfig
    admin: AdminSettings


def build_config(settings: Settings) -> ApiConfig:
    password = settings.opensearch_password
    return ApiConfig(
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        opensearch=OpenSearchConnectionConfig(
            url=settings.opensearch_url,
            username=settings.opensearch_username,
            password=password.get_secret_value() if password is not None else None,
            verify_certs=settings.opensearch_verify_certs,
            ca_certs_path=settings.opensearch_ca_certs_path,
            request_timeout_seconds=settings.opensearch_request_timeout_seconds,
            max_retries=settings.opensearch_max_retries,
            probe_timeout_seconds=settings.health_probe_timeout_seconds,
        ),
        index_names=IndexNames(
            sources=settings.sources_index_name,
            jobs=settings.jobs_index_name,
            deletions=settings.deletions_index_name,
            search=settings.search_index_name,
        ),
        crawler_client=CrawlerClientConfig(
            base_url=settings.crawler_url,
            connect_timeout_seconds=settings.crawler_connect_timeout_seconds,
            response_timeout_seconds=settings.crawler_response_timeout_seconds,
        ),
        http_probe=HttpProbeConfig(timeout_seconds=settings.health_probe_timeout_seconds),
        admin=AdminSettings(
            crawler_url=settings.crawler_url,
            indexer_url=settings.indexer_url,
            web_url=settings.web_url,
            dashboards_health_url=settings.dashboards_health_url,
            embedding_health_url=settings.embedding_health_url,
            llm_health_url=settings.llm_health_url,
            probe_timeout_seconds=settings.health_probe_timeout_seconds,
            cron_timezone=settings.cron_timezone,
            dashboards_url=settings.dashboards_url,
            admitting_lock_grace_seconds=settings.admitting_lock_grace_seconds,
            openapi_enabled=settings.openapi_enabled,
        ),
    )


def load_config() -> ApiConfig:
    """環境変数を読み、検証して、各モジュールの設定にする。違反は `ConfigError`。"""
    return build_config(load_settings())
