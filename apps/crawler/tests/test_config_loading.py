"""設定の読み込み(`LORELEY_CRAWLER_*`)と、起動時の整合性検査の呼び出し(CM-P-17・CM-P-25)。

整合性検査の関数そのものは `tests/test_config.py`。ここは、環境変数から各モジュールの設定への
詰め込み、必須項目、設定エラーの文言(値・秘密を含まない)、検査の違反での起動失敗を確かめる。
実 OpenSearch・実 Indexer には接続しない(設定を読むだけ)。
"""

import dataclasses
import logging
import os
from datetime import UTC
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from loreley_crawler import config as config_module
from loreley_crawler.config import (
    ConfigError,
    CrawlerConfig,
    Settings,
    TimingViolation,
    build_config,
    check_heartbeat_timing,
    load_config,
    warn_about_unchecked_indexer_limits,
)
from loreley_crawler.connectors.registry import FileSystemSettings
from loreley_crawler.crawl import CrawlSettings
from loreley_crawler.documents import DocumentsSettings
from loreley_crawler.infrastructure.indexer_client import ApiTimeouts, IndexerClientConfig
from loreley_crawler.infrastructure.opensearch import RepositorySettings
from loreley_crawler.jobs import HeartbeatSettings

PREFIX = "LORELEY_CRAWLER_"
MIB = 1024 * 1024
REQUIRED = {
    "OWNER": "crawler-1",
    "OPENSEARCH_URL": "http://opensearch:9200",
    "INDEXER_URL": "http://indexer:8000",
}
PASSWORD = "SENTINEL-opensearch-password"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """他の環境の `LORELEY_CRAWLER_*` に左右されない。"""
    for name in list(os.environ):
        if name.startswith(PREFIX):
            monkeypatch.delenv(name)


def set_env(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for name, value in {**REQUIRED, **values}.items():
        monkeypatch.setenv(PREFIX + name.upper(), value)


def load(monkeypatch: pytest.MonkeyPatch, **values: str) -> CrawlerConfig:
    set_env(monkeypatch, **values)
    return load_config()


def error_of(monkeypatch: pytest.MonkeyPatch, **values: str) -> ConfigError:
    set_env(monkeypatch, **values)
    with pytest.raises(ConfigError) as raised:
        load_config()
    return raised.value


# --- 既定値(architecture 11章の仮値) ---


def test_the_required_variables_alone_give_the_architecture_default_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load(monkeypatch)

    assert (config.http_host, config.http_port, config.log_level) == ("127.0.0.1", 8001, "INFO")
    assert config.opensearch.url == "http://opensearch:9200"
    assert config.opensearch.username is None and config.opensearch.password is None
    assert config.opensearch.verify_certs is True
    assert (config.sources_index_name, config.jobs_index_name) == (
        "loreley-sources",
        "loreley-jobs",
    )
    assert config.indexer.base_url == "http://indexer:8000"
    assert config.jobs.owner == "crawler-1"
    heartbeat = config.jobs.heartbeat
    assert (
        heartbeat.lease_seconds,
        heartbeat.interval_seconds,
        heartbeat.retry_interval_seconds,
        heartbeat.stop_timeout_seconds,
    ) == (300, 100, 10, 30)
    policy = config.retry_policy
    assert (
        policy.max_attempts,
        policy.initial_backoff_seconds,
        policy.backoff_multiplier,
        policy.max_backoff_seconds,
    ) == (3, 1.0, 2.0, 30.0)
    assert 0 < policy.jitter_ratio < 1  # 「ジッタあり」
    crawl = config.crawl
    assert (crawl.chunk_size, crawl.last_seen_max_ids, crawl.batch_max_documents) == (500, 500, 20)
    assert (crawl.batch_max_raw_bytes, crawl.consecutive_skip_limit) == (32 * MIB, 20)
    assert crawl.finish_id_list_warning_threshold == 8_000
    assert (crawl.polling_interval_seconds, crawl.polling_timeout_seconds) == (5, 1_800)
    assert config.documents.max_raw_bytes == 20 * MIB
    assert config.documents.max_enumerated_documents == 500_000
    assert (config.jobs.admitting_lock_grace_seconds, config.jobs.runner_scan_interval_seconds) == (
        60,
        5,
    )
    assert config.scheduler.check_interval_seconds == 30
    assert (
        config.scheduler.timezone == UTC
    )  # 未設定は UTC(OS の tzdata を使わない標準ライブラリの UTC)
    timeouts = config.indexer.timeouts
    assert (timeouts.start, timeouts.last_seen, timeouts.register_batch) == (30, 60, 300)
    assert (timeouts.discard_deletions, timeouts.delete_documents) == (600, 4_200)
    assert config.repository.scan_page_size == 1_000


def test_the_defaults_come_from_the_module_settings_not_from_a_second_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load(monkeypatch)

    assert config.crawl == CrawlSettings()
    assert config.documents == DocumentsSettings()
    assert config.file_system == FileSystemSettings()
    assert config.repository == RepositorySettings()
    assert config.jobs.heartbeat == HeartbeatSettings()
    assert config.indexer.timeouts == ApiTimeouts()
    assert config.indexer.connect_timeout_seconds == IndexerClientConfig.connect_timeout_seconds


# --- 環境変数 → 各モジュールの設定 ---

# (環境変数のフィールド名, 値, 設定された先の `CrawlerConfig` の属性パス, 期待する値)
MAPPING: list[tuple[str, str, str, Any]] = [
    ("http_host", "0.0.0.0", "http_host", "0.0.0.0"),
    ("http_port", "9000", "http_port", 9000),
    ("log_level", "warning", "log_level", "WARNING"),
    ("owner", "crawler-9", "jobs.owner", "crawler-9"),
    ("opensearch_url", "https://os:9201", "opensearch.url", "https://os:9201"),
    ("opensearch_verify_certs", "false", "opensearch.verify_certs", False),
    ("opensearch_ca_certs_path", "/ca.pem", "opensearch.ca_certs_path", "/ca.pem"),
    ("os_store_request_timeout_seconds", "12", "opensearch.store_request_timeout_seconds", 12),
    (
        "os_heartbeat_request_timeout_seconds",
        "5",
        "opensearch.heartbeat_request_timeout_seconds",
        5,
    ),
    ("sources_index_name", "s-index", "sources_index_name", "s-index"),
    ("jobs_index_name", "j-index", "jobs_index_name", "j-index"),
    ("scan_page_size", "250", "repository.scan_page_size", 250),
    ("scan_pit_keep_alive_seconds", "90", "repository.scan_pit_keep_alive_seconds", 90),
    ("scan_request_timeout_seconds", "45", "repository.scan_request_timeout_seconds", 45),
    ("bulk_delete_batch_size", "300", "repository.bulk_delete_batch_size", 300),
    ("indexer_url", "http://idx:9000", "indexer.base_url", "http://idx:9000"),
    ("indexer_connect_timeout_seconds", "3", "indexer.connect_timeout_seconds", 3),
    ("indexer_start_timeout_seconds", "11", "indexer.timeouts.start", 11),
    ("indexer_finish_timeout_seconds", "12", "indexer.timeouts.finish", 12),
    ("indexer_status_timeout_seconds", "13", "indexer.timeouts.status", 13),
    ("indexer_last_seen_timeout_seconds", "14", "indexer.timeouts.last_seen", 14),
    ("indexer_register_batch_timeout_seconds", "15", "indexer.timeouts.register_batch", 15),
    ("indexer_discard_deletions_timeout_seconds", "16", "indexer.timeouts.discard_deletions", 16),
    ("indexer_delete_documents_timeout_seconds", "17", "indexer.timeouts.delete_documents", 17),
    (
        "indexer_delete_deletion_records_timeout_seconds",
        "18",
        "indexer.timeouts.delete_deletion_records",
        18,
    ),
    ("retry_max_attempts", "5", "retry_policy.max_attempts", 5),
    ("retry_initial_backoff_seconds", "2", "retry_policy.initial_backoff_seconds", 2),
    ("retry_backoff_multiplier", "3", "retry_policy.backoff_multiplier", 3),
    ("retry_max_backoff_seconds", "60", "retry_policy.max_backoff_seconds", 60),
    ("retry_jitter_ratio", "0.5", "retry_policy.jitter_ratio", 0.5),
    ("runner_scan_interval_seconds", "7", "jobs.runner_scan_interval_seconds", 7),
    ("admitting_lock_grace_seconds", "70", "jobs.admitting_lock_grace_seconds", 70),
    ("heartbeat_lease_seconds", "600", "jobs.heartbeat.lease_seconds", 600),
    ("heartbeat_interval_seconds", "50", "jobs.heartbeat.interval_seconds", 50),
    ("heartbeat_retry_interval_seconds", "5", "jobs.heartbeat.retry_interval_seconds", 5),
    ("heartbeat_stop_timeout_seconds", "45", "jobs.heartbeat.stop_timeout_seconds", 45),
    ("scheduler_check_interval_seconds", "20", "scheduler.check_interval_seconds", 20),
    ("timezone", "Asia/Tokyo", "scheduler.timezone", ZoneInfo("Asia/Tokyo")),
    ("chunk_size", "200", "crawl.chunk_size", 200),
    ("last_seen_max_ids", "300", "crawl.last_seen_max_ids", 300),
    ("batch_max_documents", "7", "crawl.batch_max_documents", 7),
    ("batch_max_raw_bytes", str(40 * MIB), "crawl.batch_max_raw_bytes", 40 * MIB),
    ("consecutive_skip_limit", "9", "crawl.consecutive_skip_limit", 9),
    ("invalid_id_example_limit", "8", "crawl.invalid_id_example_limit", 8),
    ("finish_id_list_warning_threshold", "5000", "crawl.finish_id_list_warning_threshold", 5000),
    ("polling_interval_seconds", "2", "crawl.polling_interval_seconds", 2),
    ("polling_timeout_seconds", "900", "crawl.polling_timeout_seconds", 900),
    ("polling_max_consecutive_failures", "4", "crawl.polling_max_consecutive_failures", 4),
    ("warnings_max_entries", "10", "crawl.warnings_max_entries", 10),
    ("previous_crawl_lookup_jobs", "6", "crawl.previous_crawl_lookup_jobs", 6),
    ("max_raw_bytes", str(10 * MIB), "documents.max_raw_bytes", 10 * MIB),
    ("max_enumerated_documents", "1000", "documents.max_enumerated_documents", 1000),
    ("display_max_chars", "80", "documents.display_max_chars", 80),
    ("fs_max_patterns", "50", "file_system.max_patterns", 50),
    ("fs_max_pattern_bytes", "512", "file_system.max_pattern_bytes", 512),
    ("fs_read_chunk_bytes", "4096", "file_system.read_chunk_bytes", 4096),
    ("fs_message_path_max_chars", "100", "file_system.message_path_max_chars", 100),
]
# 認証の 2 項目と、Indexer の上限 6 項目は、下の専用のテストで確かめる。
SPECIAL_FIELDS = {
    "opensearch_username",
    "opensearch_password",
    "indexer_max_raw_bytes",
    "indexer_max_batch_documents",
    "indexer_max_batch_bytes",
    "indexer_max_request_body_bytes",
    "indexer_max_last_seen_ids",
    "indexer_skip_oversize_id_limit",
}


def value_at(config: CrawlerConfig, path: str) -> Any:
    value: Any = config
    for name in path.split("."):
        value = getattr(value, name)
    return value


def test_the_mapping_table_covers_every_settings_field() -> None:
    covered = {name for name, *_ in MAPPING} | SPECIAL_FIELDS
    assert covered == set(Settings.model_fields)


@pytest.mark.parametrize(
    ("field", "raw", "path", "expected"),
    MAPPING,
    ids=[case[0] for case in MAPPING],
)
def test_each_environment_variable_reaches_its_module_setting(
    monkeypatch: pytest.MonkeyPatch, field: str, raw: str, path: str, expected: Any
) -> None:
    config = load(monkeypatch, **{field: raw})

    assert value_at(config, path) == expected


def test_every_module_setting_field_has_an_environment_variable() -> None:
    """設定 dataclass に項目を足したのに、環境変数を足し忘れていないこと。"""
    names = set(Settings.model_fields)
    templates: list[tuple[type, str]] = [
        (CrawlSettings, "{}"),
        (DocumentsSettings, "{}"),
        (RepositorySettings, "{}"),
        (HeartbeatSettings, "heartbeat_{}"),
        (FileSystemSettings, "fs_{}"),
        (ApiTimeouts, "indexer_{}_timeout_seconds"),
        (config_module.IndexerLimits, "indexer_{}"),
        (config_module.RetryPolicy, "retry_{}"),
    ]
    for dataclass_type, template in templates:
        for item in dataclasses.fields(dataclass_type):
            assert template.format(item.name) in names, (dataclass_type.__name__, item.name)
    # Scheduler の設定は、環境変数名の規則が `scheduler_` 接頭辞だけではない(タイムゾーンは全ソース
    # 共通の `LORELEY_CRAWLER_TIMEZONE`)。
    scheduler_names = {
        "scheduler_check_interval_seconds" if item.name == "check_interval_seconds" else item.name
        for item in dataclasses.fields(config_module.SchedulerSettings)
    }
    assert scheduler_names <= names


def test_a_variable_without_the_prefix_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHUNK_SIZE", "1")
    monkeypatch.setenv("OWNER", "someone-else")

    config = load(monkeypatch)

    assert config.crawl.chunk_size == CrawlSettings().chunk_size
    assert config.jobs.owner == "crawler-1"


def test_a_lowercase_log_level_is_accepted_and_an_unknown_one_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert load(monkeypatch, log_level="debug").log_level == "DEBUG"

    error = error_of(monkeypatch, log_level="verbose")

    assert f"{PREFIX}LOG_LEVEL" in str(error)
    assert "verbose" not in str(error)


# --- 必須項目と owner ---


@pytest.mark.parametrize("name", ["owner", "opensearch_url", "indexer_url"])
def test_a_missing_required_variable_fails_the_startup_naming_the_variable(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    set_env(monkeypatch)
    monkeypatch.delenv(PREFIX + name.upper())

    with pytest.raises(ConfigError) as raised:
        load_config()

    assert str(raised.value) == f"invalid settings: {PREFIX}{name.upper()}: missing"


def test_every_missing_required_variable_is_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ConfigError) as raised:
        load_config()

    assert str(raised.value) == (
        f"invalid settings: {PREFIX}OWNER: missing; {PREFIX}OPENSEARCH_URL: missing; "
        f"{PREFIX}INDEXER_URL: missing"
    )


@pytest.mark.parametrize(
    ("owner", "message"),
    [
        ("", "owner must not be empty"),
        ("x" * 257, "owner must be at most 256 bytes in UTF-8"),
        ("あ" * 86, "owner must be at most 256 bytes in UTF-8"),
        ("crawler\n1", "owner must not contain control characters"),
    ],
)
def test_an_invalid_owner_fails_the_startup(
    monkeypatch: pytest.MonkeyPatch, owner: str, message: str
) -> None:
    error = error_of(monkeypatch, owner=owner)

    assert str(error) == f"invalid jobs settings: {message}"


def test_an_owner_of_exactly_256_bytes_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    assert load(monkeypatch, owner="x" * 256).jobs.owner == "x" * 256


def test_an_owner_with_a_lone_surrogate_fails_without_echoing_it() -> None:
    """環境変数には入れられないが、`Settings` を直接組み立てる呼び出しでも値を載せない。"""
    settings = Settings(owner="a\ud800b", opensearch_url="http://os:9200", indexer_url="http://i:8")

    with pytest.raises(ConfigError) as raised:
        build_config(settings)

    assert str(raised.value) == "invalid jobs settings: UnicodeEncodeError"


# --- 秘密 ---


def test_the_password_reaches_the_connection_and_the_log_secrets_but_not_any_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load(monkeypatch, opensearch_username="crawler", opensearch_password=PASSWORD)

    assert config.opensearch.username == "crawler"
    assert config.opensearch.password == PASSWORD
    assert config.log_secrets == (PASSWORD,)
    assert PASSWORD not in repr(config)
    assert PASSWORD not in str(config)
    assert PASSWORD not in repr(config.opensearch)
    assert PASSWORD not in repr(Settings())  # `SecretStr`


def test_without_a_password_there_are_no_log_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    assert load(monkeypatch).log_secrets == ()


@pytest.mark.parametrize(
    "overrides",
    [
        {"http_port": "not-a-number"},
        {"chunk_size": "0"},
        {"os_store_request_timeout_seconds": "-1"},
        {"opensearch_url": "http://user:SENTINEL-url-password@host:9200"},
        {"opensearch_url": "http://host:99999999"},
        {"indexer_url": "http://user:SENTINEL-url-password@host:8000"},
        {"indexer_url": "ftp://host"},
        {"retry_max_attempts": "0"},
        {"sources_index_name": "same", "jobs_index_name": "same"},
        {"heartbeat_stop_timeout_seconds": "1"},
        {"max_raw_bytes": str(100 * MIB)},
        {"indexer_max_raw_bytes": "1"},
        {"log_level": "SENTINEL-level"},
    ],
    ids=lambda overrides: next(iter(overrides)),
)
def test_no_error_message_contains_the_password_or_a_given_value(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str]
) -> None:
    error = error_of(
        monkeypatch, opensearch_username="crawler", opensearch_password=PASSWORD, **overrides
    )

    text = f"{error} {error!r}"
    assert PASSWORD not in text
    assert "SENTINEL" not in text
    # 元の例外(入力値を持つ)を連鎖させない。
    assert error.__cause__ is None
    assert error.__context__ is None


def test_a_password_without_a_username_fails_and_is_not_echoed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = error_of(monkeypatch, opensearch_password=PASSWORD)

    assert str(error) == "invalid OpenSearch settings: username and password must be set together"


def test_at_most_ten_setting_errors_are_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = {
        name: "x"
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
            "max_raw_bytes",
            "max_enumerated_documents",
        )
    }

    message = str(error_of(monkeypatch, **bad))

    assert message.count("int_parsing") == 10
    assert message.endswith("... and 2 more")


# --- 整合性検査の呼び出し ---


def test_a_crawler_value_above_the_indexer_limit_fails_the_startup_with_names_and_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = error_of(
        monkeypatch,
        max_raw_bytes=str(30 * MIB),
        batch_max_raw_bytes=str(40 * MIB),
        indexer_max_raw_bytes=str(20 * MIB),
    )

    assert str(error) == (
        "startup consistency check failed: "
        f"max_raw_bytes={30 * MIB} exceeds MAX_RAW_BYTES={20 * MIB}"
    )


@pytest.mark.parametrize(
    ("crawler", "indexer", "limit_name"),
    [
        (
            {"batch_max_documents": "51"},
            {"indexer_max_batch_documents": "50"},
            "MAX_BATCH_DOCUMENTS",
        ),
        (
            {"batch_max_raw_bytes": str(65 * MIB)},
            {"indexer_max_batch_bytes": str(64 * MIB)},
            "MAX_BATCH_BYTES",
        ),
        (
            {"batch_max_raw_bytes": str(32 * MIB)},
            {"indexer_max_request_body_bytes": str(40 * MIB)},  # 32 MiB の 4/3 倍は 40 MiB を超える
            "MAX_REQUEST_BODY_BYTES",
        ),
        ({"last_seen_max_ids": "1001"}, {"indexer_max_last_seen_ids": "1000"}, "MAX_LAST_SEEN_IDS"),
        (
            {"finish_id_list_warning_threshold": "10001"},
            {"indexer_skip_oversize_id_limit": "10000"},
            "SKIP_OVERSIZE_ID_LIMIT",
        ),
    ],
)
def test_each_indexer_limit_is_checked_by_the_startup(
    monkeypatch: pytest.MonkeyPatch,
    crawler: dict[str, str],
    indexer: dict[str, str],
    limit_name: str,
) -> None:
    error = error_of(monkeypatch, **crawler, **indexer)

    assert str(error).startswith("startup consistency check failed: ")
    assert f" exceeds {limit_name}=" in str(error)


def test_values_equal_to_the_indexer_limits_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    config = load(
        monkeypatch,
        indexer_max_raw_bytes=str(20 * MIB),
        indexer_max_batch_documents="20",
        indexer_max_batch_bytes=str(32 * MIB),
        indexer_max_request_body_bytes=str(32 * MIB * 4 // 3 + 1),
        indexer_max_last_seen_ids="500",
        indexer_skip_oversize_id_limit="8000",
    )

    assert config.unchecked_indexer_limits == ()


def test_a_raw_limit_above_the_batch_limit_fails_even_without_the_indexer_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = error_of(monkeypatch, max_raw_bytes=str(33 * MIB))

    assert str(error) == (
        f"startup consistency check failed: max_raw_bytes={33 * MIB} "
        f"exceeds batch_max_raw_bytes={32 * MIB}"
    )


def test_all_violations_are_reported_together(monkeypatch: pytest.MonkeyPatch) -> None:
    error = error_of(
        monkeypatch,
        batch_max_documents="51",
        indexer_max_batch_documents="50",
        last_seen_max_ids="1001",
        indexer_max_last_seen_ids="1000",
        heartbeat_stop_timeout_seconds="1",
        sources_index_name="same",
        jobs_index_name="same",
    )

    text = str(error)
    assert "batch_max_documents=51 exceeds MAX_BATCH_DOCUMENTS=50" in text
    assert "last_seen_max_ids=1001 exceeds MAX_LAST_SEEN_IDS=1000" in text
    assert "heartbeat_stop_timeout_seconds=1.0 is below" in text
    assert "sources_index_name and jobs_index_name must differ" in text


def test_unset_indexer_limits_are_listed_as_unchecked_and_the_rest_are_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert load(monkeypatch).unchecked_indexer_limits == (
        "MAX_RAW_BYTES",
        "MAX_BATCH_DOCUMENTS",
        "MAX_BATCH_BYTES",
        "MAX_REQUEST_BODY_BYTES",
        "MAX_LAST_SEEN_IDS",
        "SKIP_OVERSIZE_ID_LIMIT",
    )
    partial = load(
        monkeypatch, indexer_max_raw_bytes=str(20 * MIB), indexer_max_last_seen_ids="500"
    )
    assert partial.unchecked_indexer_limits == (
        "MAX_BATCH_DOCUMENTS",
        "MAX_BATCH_BYTES",
        "MAX_REQUEST_BODY_BYTES",
        "SKIP_OVERSIZE_ID_LIMIT",
    )


def test_the_indexer_limits_use_a_name_that_cannot_be_confused_with_the_crawlers_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`LORELEY_CRAWLER_MAX_RAW_BYTES` は Crawler 自身の値で、Indexer の上限ではない。"""
    config = load(monkeypatch, max_raw_bytes=str(10 * MIB))

    assert config.documents.max_raw_bytes == 10 * MIB
    assert "MAX_RAW_BYTES" in config.unchecked_indexer_limits


def test_the_warning_names_the_unchecked_limits_and_no_value(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    config = load(monkeypatch, indexer_max_raw_bytes=str(20 * MIB))

    with caplog.at_level(logging.WARNING, logger=config_module.__name__):
        warn_about_unchecked_indexer_limits(config)

    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert "MAX_BATCH_DOCUMENTS" in record.getMessage()
    assert "MAX_RAW_BYTES," not in record.getMessage()  # 設定済みの項目は載せない


def test_no_warning_when_every_indexer_limit_is_set(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    config = load(
        monkeypatch,
        indexer_max_raw_bytes=str(20 * MIB),
        indexer_max_batch_documents="50",
        indexer_max_batch_bytes=str(64 * MIB),
        indexer_max_request_body_bytes=str(100 * MIB),
        indexer_max_last_seen_ids="1000",
        indexer_skip_oversize_id_limit="10000",
    )

    with caplog.at_level(logging.WARNING, logger=config_module.__name__):
        warn_about_unchecked_indexer_limits(config)

    assert caplog.records == []


# --- ハートビートの時間 ---


def test_the_stop_timeout_must_be_at_least_twice_the_heartbeat_client_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert load(
        monkeypatch, os_heartbeat_request_timeout_seconds="15", heartbeat_stop_timeout_seconds="30"
    )

    error = error_of(
        monkeypatch,
        os_heartbeat_request_timeout_seconds="15",
        heartbeat_stop_timeout_seconds="29.9",
    )

    assert str(error) == (
        "startup consistency check failed: heartbeat_stop_timeout_seconds=29.9 is below "
        "2 * os_heartbeat_request_timeout_seconds=30.0"
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"heartbeat_retry_interval_seconds": "100"},  # 再試行間隔 == 更新間隔
            "invalid heartbeat settings: require 0 < retry_interval < interval < lease",
        ),
        (
            {"heartbeat_interval_seconds": "300"},  # 更新間隔 == リース
            "invalid heartbeat settings: require 0 < retry_interval < interval < lease",
        ),
        (
            {"heartbeat_lease_seconds": "50"},  # リース < 更新間隔
            "invalid heartbeat settings: require 0 < retry_interval < interval < lease",
        ),
        (
            {"heartbeat_retry_interval_seconds": "0"},
            "invalid heartbeat settings: require 0 < retry_interval < interval < lease",
        ),
        (
            {"heartbeat_stop_timeout_seconds": "0"},
            "invalid heartbeat settings: stop_timeout_seconds must be positive",
        ),
    ],
)
def test_the_heartbeat_time_relation_is_enforced(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str], message: str
) -> None:
    assert str(error_of(monkeypatch, **overrides)) == message


def test_check_heartbeat_timing_has_an_exact_boundary_at_twice_the_timeout() -> None:
    heartbeat = HeartbeatSettings(stop_timeout_seconds=20)

    assert check_heartbeat_timing(heartbeat, 10) == ()
    [violation] = check_heartbeat_timing(heartbeat, 10.5)
    assert violation == TimingViolation(
        "heartbeat_stop_timeout_seconds", 20, "2 * os_heartbeat_request_timeout_seconds", 21
    )
    assert violation.describe() == (
        "heartbeat_stop_timeout_seconds=20 is below 2 * os_heartbeat_request_timeout_seconds=21.0"
    )


def test_the_default_heartbeat_values_satisfy_the_checks() -> None:
    from loreley_crawler.infrastructure.opensearch import OpenSearchConnectionConfig

    assert (
        check_heartbeat_timing(
            HeartbeatSettings(), OpenSearchConnectionConfig.heartbeat_request_timeout_seconds
        )
        == ()
    )


# --- そのほかの検査 ---


def test_the_two_index_names_must_differ(monkeypatch: pytest.MonkeyPatch) -> None:
    error = error_of(monkeypatch, sources_index_name="same", jobs_index_name="same")

    assert (
        str(error)
        == "startup consistency check failed: sources_index_name and jobs_index_name must differ"
    )


def test_an_empty_index_name_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    error = error_of(monkeypatch, jobs_index_name="")

    assert str(error) == f"invalid settings: {PREFIX}JOBS_INDEX_NAME: string_too_short"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"chunk_size": "0"}, "invalid crawl settings: chunk_size must be at least 1"),
        (
            {"polling_interval_seconds": "0"},
            "invalid crawl settings: polling_interval_seconds must be positive",
        ),
        (
            {"max_enumerated_documents": "0"},
            "invalid documents settings: max_enumerated_documents must be at least 1",
        ),
        (
            {"scan_page_size": "0"},
            "invalid repository settings: scan_page_size must be between 1 and 10000",
        ),
        ({"fs_max_patterns": "0"}, "invalid file system settings: max_patterns must be at least 1"),
        (
            {"scheduler_check_interval_seconds": "0"},
            "invalid scheduler settings: check_interval_seconds must be positive",
        ),
        ({"retry_max_attempts": "0"}, "invalid retry settings: max_attempts must be at least 1"),
        (
            {"retry_jitter_ratio": "1.5"},
            "invalid retry settings: jitter_ratio must be between 0 and 1",
        ),
        (
            {"runner_scan_interval_seconds": "0"},
            "invalid jobs settings: runner_scan_interval_seconds must be positive",
        ),
        (
            {"indexer_start_timeout_seconds": "0"},
            "invalid Indexer settings: the timeout of start must be positive",
        ),
        (
            {"indexer_url": "http://idx/path"},
            "invalid Indexer settings: the Indexer URL must not include a path, query or fragment",
        ),
        (
            {"opensearch_url": "http://u:p@host"},
            "invalid OpenSearch settings: credentials must not be embedded in the OpenSearch URL",
        ),
        (
            {"os_store_request_timeout_seconds": "0"},
            "invalid OpenSearch settings: store_request_timeout_seconds must be positive",
        ),
    ],
)
def test_an_out_of_range_value_fails_with_the_module_validation_message(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str], message: str
) -> None:
    assert str(error_of(monkeypatch, **overrides)) == message


@pytest.mark.parametrize("name", ["UTC", "Asia/Tokyo", "America/New_York", "Etc/GMT-9"])
def test_an_iana_time_zone_name_is_accepted(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    config = load(monkeypatch, timezone=name)

    expected = UTC if name == "UTC" else ZoneInfo(name)  # `UTC` は tzdata を使わない
    assert config.scheduler.timezone == expected


@pytest.mark.parametrize(
    "name",
    [
        "Asia/SENTINEL_Nowhere",  # 存在しない名前
        "",
        " ",
        "Asia",  # ディレクトリ
        "../SENTINEL",  # 正規化されていない相対パス
        "/etc/SENTINEL",  # 絶対パス
    ],
)
def test_an_invalid_time_zone_name_fails_the_startup_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    error = error_of(monkeypatch, timezone=name)

    assert str(error) == "invalid scheduler settings: timezone must be an IANA time zone name"
    assert "SENTINEL" not in str(error) and error.__cause__ is None and error.__context__ is None


def test_loading_does_not_create_any_client_or_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """設定を読むだけで、OpenSearch・Indexer には触れない(接続は起動順の次の段階)。"""
    import opensearchpy

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("loading the configuration must not connect")

    monkeypatch.setattr(opensearchpy, "OpenSearch", forbidden)

    assert load(monkeypatch).opensearch.url == "http://opensearch:9200"


@pytest.mark.parametrize(
    ("port", "is_valid"), [("0", False), ("1", True), ("65535", True), ("65536", False)]
)
def test_the_http_port_must_be_in_the_tcp_range(
    monkeypatch: pytest.MonkeyPatch, port: str, is_valid: bool
) -> None:
    set_env(monkeypatch, http_port=port)

    if is_valid:
        assert load_config().http_port == int(port)
        return
    with pytest.raises(ConfigError) as raised:
        load_config()
    assert str(raised.value).startswith(f"invalid settings: {PREFIX}HTTP_PORT: ")
    assert port not in str(raised.value).split(": ", 2)[2]  # 値は載せない
