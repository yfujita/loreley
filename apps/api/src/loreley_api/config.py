"""設定の読み込み(環境変数 `LORELEY_API_*`)。

各モジュールは `config.py` に依存しない。値は `main.py` がこのクラスから取り出して渡す
(module 4.1)。基盤の設定は待ち受けとログ水準だけ。機能パッケージの設定は、その機能を
実装するときに足す。
"""

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

MAX_REPORTED_SETTING_ERRORS = 10


class ConfigError(Exception):
    """起動を続けられない設定の違反。メッセージは固定文と、フィールド名・検証の種別だけ(値なし)。"""


def _normalize_log_level(value: object) -> object:
    """`info` のような小文字も受け付ける(環境変数の書き方の違いで起動に失敗させない)。"""
    return value.upper() if isinstance(value, str) else value


LogLevel = Annotated[
    Literal["DEBUG", "INFO", "WARNING", "ERROR"], BeforeValidator(_normalize_log_level)
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LORELEY_API_", extra="ignore", frozen=True)

    # 既定は手元の確認用の 127.0.0.1。コンテナでは、外から届くよう 0.0.0.0 を指定する。
    host: str = "127.0.0.1"
    port: int = Field(8080, ge=1, le=65_535)
    log_level: LogLevel = "INFO"


def describe_settings_errors(error: ValidationError) -> str:
    """設定の検証エラーを、フィールド名と検証の種別(`type`)だけで表す。

    pydantic の表示(`str(error)`)は、入力の環境変数の辞書や不正な値(`input_value`)を
    そのまま出す。`input`・`ctx`・本文(`msg`)は使わない。
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
