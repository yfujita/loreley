"""起動時の設定の読み込みエラーが、秘密値・入力値を出さないこと(R9)。

pydantic の `ValidationError` は、入力の環境変数の辞書(パスワードを含む)や不正な値をそのまま
表示する。`SecretStr` では防げないため、`main.load_settings` がフィールド名と検証の種別だけの
`StartupError` に変換する。実際の `python -m loreley_indexer.main` を子プロセスで起動し、
標準エラー出力も検査する(OpenSearch へ到達しない失敗経路と、閉じたローカルポートへの接続失敗だけ。
外部ネットワークには出ない)。

メッセージの検査は完全一致にする。部分一致だと、`msg`・`ctx`・`input` のように出してはいけない
情報が付け足されても通ってしまうため。
"""

import os
import socket
import subprocess
import sys
import traceback
from pathlib import Path

import pytest

import loreley_indexer.main as main_module
from loreley_indexer.main import (
    INVALID_CONNECTION_MESSAGE,
    StartupError,
    create_backends,
    load_settings,
)

SECRET_PASSWORD = "SENTINEL-SECRET-PW"
URL_PASSWORD = "SENTINEL-URLPW"
PREFIX = "LORELEY_INDEXER_"
SOURCE_DIRECTORY = Path(__file__).parents[1] / "src"


@pytest.fixture(autouse=True)
def clean_indexer_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [name for name in os.environ if name.startswith(PREFIX)]:
        monkeypatch.delenv(name)


def set_environment(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for name, value in values.items():
        monkeypatch.setenv(PREFIX + name.upper(), value)


def startup_error_of(monkeypatch: pytest.MonkeyPatch, **values: str) -> StartupError:
    set_environment(monkeypatch, **values)
    with pytest.raises(StartupError) as error_info:
        load_settings()
    return error_info.value


def everything_shown_of(error: BaseException) -> str:
    """利用者が目にしうる、例外の表現すべて。"""
    return "\n".join(
        [
            str(error),
            repr(error),
            "".join(traceback.format_exception(error)),
            repr(error.__context__),
            repr(error.__cause__),
        ]
    )


# --- 必須の項目がない(メインが実コンテナで再現した形) ---


def test_a_missing_url_reports_the_field_and_the_kind_without_the_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = startup_error_of(
        monkeypatch, opensearch_username="admin", opensearch_password=SECRET_PASSWORD
    )

    assert SECRET_PASSWORD not in everything_shown_of(error)
    assert str(error) == "invalid settings: opensearch_url: missing"
    assert error.__context__ is None  # 入力値を持つ元の例外を連鎖させない


# --- 不正な値 ---


@pytest.mark.parametrize(
    ("name", "value", "kind"),
    [
        ("http_port", "99999", "less_than_equal"),
        ("http_port", "-12345", "greater_than_equal"),
        ("http_port", "SENTINEL-PORT", "int_parsing"),
        ("os_request_timeout_seconds", "-7654.5", "greater_than"),
        ("log_level", "SENTINEL-LEVEL", "literal_error"),
        ("opensearch_verify_certs", "SENTINEL-BOOL", "bool_parsing"),
    ],
)
def test_an_invalid_value_reports_the_field_and_the_kind_only(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str, kind: str
) -> None:
    """完全一致なので、`input`(値)・`ctx`(上限値)・`msg`(本文)を付け足すと失敗する。"""
    error = startup_error_of(
        monkeypatch,
        opensearch_url="http://opensearch:9200",
        opensearch_password=SECRET_PASSWORD,
        **{name: value},
    )

    shown = everything_shown_of(error)
    assert value not in shown
    assert SECRET_PASSWORD not in shown
    assert str(error) == f"invalid settings: {name}: {kind}"


def test_every_error_is_reported_up_to_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    error = startup_error_of(monkeypatch, http_port="0", max_batch_documents="0")

    assert str(error) == (
        "invalid settings: http_port: greater_than_equal; opensearch_url: missing; "
        "max_batch_documents: greater_than_equal"
    )


def test_the_number_of_reported_errors_is_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    names = [
        "http_port",
        "max_raw_bytes",
        "max_batch_documents",
        "max_batch_bytes",
        "max_request_body_bytes",
        "max_content_bytes",
        "max_last_seen_ids",
        "write_conflict_max_rereads",
        "delete_by_query_max_reruns",
        "skip_oversize_id_limit",
        "deletion_batch_size",
    ]
    error = startup_error_of(monkeypatch, **dict.fromkeys(names, "0"))  # 12 件(URL の欠落を含む)

    assert main_module.MAX_REPORTED_SETTING_ERRORS == 10  # 下の期待値の件数と対応する
    assert str(error) == (
        "invalid settings: "
        "http_port: greater_than_equal; "
        "opensearch_url: missing; "
        "max_raw_bytes: greater_than_equal; "
        "max_batch_documents: greater_than_equal; "
        "max_batch_bytes: greater_than_equal; "
        "max_request_body_bytes: greater_than_equal; "
        "max_content_bytes: greater_than_equal; "
        "max_last_seen_ids: greater_than_equal; "
        "write_conflict_max_rereads: greater_than_equal; "
        "delete_by_query_max_reruns: greater_than_equal; "
        "... and 2 more"
    )


# --- 設定どうしの整合 ---
# 検証名(`type`)がメッセージの一部になる。名前を変えると運用者が見る文言が変わるため、固定する。
# 1 件だけが違反する値にする(最初の違反で検証が止まるため、ほかの検証には届かない)。

INCONSISTENT_SETTINGS = [
    pytest.param(
        {"summary_rescan_max_interval_seconds": "7.25"},  # 下限(既定 60)未満
        "rescan_max_interval_below_min",
        id="rescan_max_interval_below_min",
    ),
    pytest.param(
        {"max_raw_bytes": "7654321", "max_batch_bytes": "1234567"},
        "raw_bytes_above_batch_bytes",
        id="raw_bytes_above_batch_bytes",
    ),
    pytest.param(
        {"max_request_body_bytes": "7654321"},  # バッチ上限(既定 64 MiB)の 4/3 倍に届かない
        "batch_bytes_above_request_body_bytes",
        id="batch_bytes_above_request_body_bytes",
    ),
    pytest.param(
        {"deletion_poll_backoff_max_seconds": "1.25"},  # 間隔(既定 2 秒)未満
        "poll_backoff_max_below_interval",
        id="poll_backoff_max_below_interval",
    ),
]


@pytest.mark.parametrize(("values", "check_name"), INCONSISTENT_SETTINGS)
def test_an_inconsistent_setting_reports_the_check_name_without_the_values(
    monkeypatch: pytest.MonkeyPatch, values: dict[str, str], check_name: str
) -> None:
    error = startup_error_of(monkeypatch, opensearch_url="http://opensearch:9200", **values)

    assert str(error) == f"invalid settings: settings: {check_name}"
    assert all(value not in everything_shown_of(error) for value in values.values())


# --- OpenSearch の接続設定(URL)が不正 ---
# URL を解釈できないと、標準ライブラリ・opensearch-py の `ValueError` は URL の一部(認証情報を含む
# netloc、ポートの値)をメッセージに入れる。`create_backends` が固定文の `StartupError` にする。

UNPARSABLE_URLS = [
    pytest.param(f"http://user:{URL_PASSWORD}@host\u2100:9200", URL_PASSWORD, id="invalid-netloc"),
    pytest.param("http://host:SENTINEL-PORT", "SENTINEL-PORT", id="invalid-port"),
    pytest.param("http://host:99999999", "99999999", id="port-out-of-range"),
    pytest.param("http://[SENTINEL-HOST", "SENTINEL-HOST", id="invalid-ipv6"),
    pytest.param(f"http://user:{URL_PASSWORD}@host:9200", URL_PASSWORD, id="embedded-credentials"),
]


@pytest.mark.parametrize(("url", "sentinel"), UNPARSABLE_URLS)
def test_an_invalid_connection_url_is_a_fixed_startup_error(
    monkeypatch: pytest.MonkeyPatch, url: str, sentinel: str
) -> None:
    set_environment(monkeypatch, opensearch_url=url, opensearch_password=SECRET_PASSWORD)

    with pytest.raises(StartupError) as error_info:
        create_backends(load_settings())

    error = error_info.value
    assert str(error) == INVALID_CONNECTION_MESSAGE
    assert sentinel not in everything_shown_of(error)
    assert SECRET_PASSWORD not in everything_shown_of(error)
    assert error.__context__ is None  # 値を持つ元の `ValueError` を連鎖させない
    assert error.__cause__ is None


# --- 実際のプロセス ---


def run_indexer(**values: str) -> subprocess.CompletedProcess[str]:
    environment = {PREFIX + name.upper(): value for name, value in values.items()}
    environment["PYTHONPATH"] = str(SOURCE_DIRECTORY)  # インストールされていなくても import できる
    # `timeout` を超えると `run` が子プロセスを kill する(ハングしても、テストは止まる)。
    return subprocess.run(
        [sys.executable, "-m", "loreley_indexer.main"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def last_line_of(output: str) -> str:
    """トレースバックの最後の行(例外の種別とメッセージ)。"""
    return output.strip().splitlines()[-1]


def closed_local_port() -> int:
    """だれも待ち受けていないローカルのポート(bind してすぐ閉じる)。外部には出ない。"""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_the_process_with_a_missing_url_fails_without_showing_the_password() -> None:
    result = run_indexer(opensearch_username="admin", opensearch_password=SECRET_PASSWORD)

    assert result.returncode != 0
    assert SECRET_PASSWORD not in result.stdout + result.stderr
    assert last_line_of(result.stderr) == "StartupError: invalid settings: opensearch_url: missing"


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"http_port": "99999"}, "invalid settings: http_port: less_than_equal"),
        (
            {"os_request_timeout_seconds": "-7654.5"},
            "invalid settings: os_request_timeout_seconds: greater_than",
        ),
        (
            {"max_raw_bytes": "7654321", "max_batch_bytes": "1234567"},
            "invalid settings: settings: raw_bytes_above_batch_bytes",
        ),
        (
            {"deletion_poll_backoff_max_seconds": "1.25"},
            "invalid settings: settings: poll_backoff_max_below_interval",
        ),
    ],
)
def test_the_process_with_an_invalid_value_fails_without_showing_the_value(
    values: dict[str, str], message: str
) -> None:
    result = run_indexer(
        opensearch_url="http://opensearch:9200", opensearch_password=SECRET_PASSWORD, **values
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert SECRET_PASSWORD not in output
    assert all(value not in output for value in values.values())
    assert last_line_of(result.stderr) == f"StartupError: {message}"


@pytest.mark.parametrize(("url", "sentinel"), UNPARSABLE_URLS)
def test_the_process_with_an_invalid_connection_url_fails_without_showing_the_url(
    url: str, sentinel: str
) -> None:
    """URL を解釈できない、または認証情報を含む場合。接続はしない。"""
    result = run_indexer(opensearch_url=url, opensearch_password=SECRET_PASSWORD)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert sentinel not in output
    assert SECRET_PASSWORD not in output
    assert last_line_of(result.stderr) == f"StartupError: {INVALID_CONNECTION_MESSAGE}"
    assert "During handling of the above exception" not in output  # 元の例外が連鎖していない


def test_the_process_that_cannot_reach_opensearch_fails_without_showing_the_password() -> None:
    """起動時の整理(OpenSearch への最初の呼び出し)で接続に失敗する経路。閉じたローカルポートへ。"""
    result = run_indexer(
        opensearch_url=f"http://127.0.0.1:{closed_local_port()}",
        opensearch_username="admin",
        opensearch_password=SECRET_PASSWORD,
        http_port=str(closed_local_port()),
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert SECRET_PASSWORD not in output
    assert "Application startup failed" in result.stderr
    # 種別名だけで、接続先の詳細・認証情報は出ない。
    assert "OpenSearchUnavailableError: connection_error" in result.stderr
