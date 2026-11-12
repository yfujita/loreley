import os

import pytest
from annotated_types import Le
from pydantic import ValidationError

from loreley_indexer.api import ApiConfig
from loreley_indexer.config import MIB, Settings
from loreley_indexer.crawl_runs import DeletionConfig, LifecycleConfig
from loreley_indexer.documents import RegistrationConfig, SummarizationConfig
from loreley_indexer.documents.extraction import ExtractionConfig
from loreley_indexer.infrastructure.opensearch import IndexNames, OpenSearchConnectionConfig


@pytest.fixture(autouse=True)
def clean_indexer_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """実行環境の `LORELEY_INDEXER_*` が、既定値や必須チェックのテストに混ざらないようにする。"""
    for name in [name for name in os.environ if name.startswith("LORELEY_INDEXER_")]:
        monkeypatch.delenv(name)


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, opensearch_url="http://opensearch:9200", **overrides)


# plan 0002 §4 の表の既定値。
PLANNED_DEFAULTS = {
    # P5: HTTP の待ち受けとログ(設計書に規定なし。運用上の既定)
    "http_host": "127.0.0.1",
    "http_port": 8000,
    "log_level": "INFO",
    "opensearch_username": None,
    "opensearch_password": None,
    "opensearch_verify_certs": True,
    "opensearch_ca_certs_path": None,
    "os_request_timeout_seconds": 30.0,
    "os_transport_max_retries": 2,
    "os_delete_by_query_timeout_seconds": 600.0,
    "search_index_name": "loreley-documents",
    "deletions_index_name": "loreley-deletions",
    "jobs_index_name": "loreley-jobs",
    "max_raw_bytes": 20 * MIB,
    "max_batch_documents": 50,
    "max_batch_bytes": 64 * MIB,
    "max_request_body_bytes": 100 * MIB,
    "max_content_bytes": 5 * MIB,
    "max_last_seen_ids": 1_000,
    "write_conflict_max_rereads": 3,
    "update_retry_on_conflict": 3,
    "delete_by_query_max_reruns": 5,
    "retry_backoff_initial_seconds": 1.0,
    "retry_backoff_factor": 2.0,
    "retry_backoff_max_seconds": 30.0,
    "skip_oversize_id_limit": 10_000,
    "deletion_batch_size": 100,
    "deletion_retention_count": 20,
    "max_deletion_targets": 200_000,
    "search_after_page_size": 1_000,
    "deletion_poll_interval_seconds": 2.0,
    "deletion_poll_backoff_max_seconds": 300.0,
    "delete_error_retry_attempts": 3,
    "discard_max_attempts": 20,
    "summary_enabled": False,
    "summary_concurrency": 1,
    "summary_max_attempts": 3,
    "summary_queue_size": 100,
    "summary_rescan_page_size": 100,
    "summary_rescan_min_interval_seconds": 60.0,
    "summary_rescan_max_interval_seconds": 3_600.0,
    "llm_timeout_seconds": 60.0,
    "summary_input_max_chars": 30_000,
}


@pytest.mark.parametrize(("name", "expected"), PLANNED_DEFAULTS.items())
def test_default_matches_the_planned_provisional_value(name: str, expected: object) -> None:
    assert getattr(make_settings(), name) == expected


def test_every_setting_except_the_url_has_a_planned_default() -> None:
    assert set(Settings.model_fields) - {"opensearch_url"} == set(PLANNED_DEFAULTS)


def test_values_are_read_from_prefixed_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LORELEY_INDEXER_OPENSEARCH_URL", "http://os.example:9200")
    monkeypatch.setenv("LORELEY_INDEXER_MAX_BATCH_DOCUMENTS", "10")
    monkeypatch.setenv("LORELEY_INDEXER_SUMMARY_ENABLED", "true")
    settings = Settings(_env_file=None)
    assert settings.opensearch_url == "http://os.example:9200"
    assert settings.max_batch_documents == 10
    assert settings.summary_enabled is True


def test_opensearch_url_is_required() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# (設定名, 上限)。仮値でも無制限にならないよう、すべての数値に上限がある(K39)。
UPPER_BOUNDS = [
    ("max_raw_bytes", 100 * MIB),
    ("max_batch_documents", 500),
    ("max_batch_bytes", 256 * MIB),
    ("max_request_body_bytes", 512 * MIB),
    ("max_content_bytes", 50 * MIB),
    ("max_last_seen_ids", 10_000),
    ("write_conflict_max_rereads", 10),
    ("update_retry_on_conflict", 10),
    ("delete_by_query_max_reruns", 20),
    ("skip_oversize_id_limit", 100_000),
    ("deletion_batch_size", 1_000),
    ("deletion_retention_count", 1_000),
    ("max_deletion_targets", 2_000_000),
    ("search_after_page_size", 10_000),
    ("deletion_poll_interval_seconds", 60),
    ("deletion_poll_backoff_max_seconds", 3_600),
    ("delete_error_retry_attempts", 10),
    ("discard_max_attempts", 100),
    ("summary_concurrency", 8),
    ("summary_max_attempts", 10),
    ("summary_queue_size", 10_000),
    ("summary_rescan_page_size", 1_000),
    ("summary_rescan_min_interval_seconds", 3_600),
    ("summary_rescan_max_interval_seconds", 86_400),
    ("llm_timeout_seconds", 600),
    ("summary_input_max_chars", 1_000_000),
    ("os_request_timeout_seconds", 300),
    ("os_transport_max_retries", 5),
    ("os_delete_by_query_timeout_seconds", 3_600),
    ("retry_backoff_initial_seconds", 60),
    ("retry_backoff_factor", 10),
    ("retry_backoff_max_seconds", 300),
    ("http_port", 65_535),
]


# 上限どうしの整合の検証(`max_raw_bytes ≤ max_batch_bytes` など)に合わせて、同時に上げる設定。
RAISED_WITH = {
    "max_raw_bytes": {"max_batch_bytes": 256 * MIB, "max_request_body_bytes": 512 * MIB},
    "max_batch_bytes": {"max_request_body_bytes": 512 * MIB},
}


@pytest.mark.parametrize(("name", "upper_bound"), UPPER_BOUNDS)
def test_value_at_the_upper_bound_is_accepted(name: str, upper_bound: float) -> None:
    settings = make_settings(**{name: upper_bound, **RAISED_WITH.get(name, {})})
    assert getattr(settings, name) == upper_bound


@pytest.mark.parametrize(("name", "upper_bound"), UPPER_BOUNDS)
def test_value_above_the_upper_bound_is_rejected(name: str, upper_bound: float) -> None:
    with pytest.raises(ValidationError):
        make_settings(**{name: upper_bound + 1})


def test_every_numeric_setting_has_an_upper_bound_listed_in_the_table() -> None:
    """新しい数値設定に上限を付け忘れると(無制限になりうる)ここで気づく。"""
    upper_bounds = dict(UPPER_BOUNDS)
    numeric_fields = {
        name: field
        for name, field in Settings.model_fields.items()
        if field.annotation in (int, float)
    }
    declared = {
        name: [constraint.le for constraint in field.metadata if isinstance(constraint, Le)]
        for name, field in numeric_fields.items()
    }
    assert {name: bounds for name, bounds in declared.items() if len(bounds) != 1} == {}
    assert {name: bounds[0] for name, bounds in declared.items()} == upper_bounds


@pytest.mark.parametrize(
    "name",
    [
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
        "deletion_retention_count",
        "max_deletion_targets",
        "search_after_page_size",
        "delete_error_retry_attempts",
        "discard_max_attempts",
        "summary_concurrency",
        "summary_max_attempts",
        "summary_queue_size",
        "summary_rescan_page_size",
        "summary_input_max_chars",
    ],
)
def test_zero_is_rejected_where_it_would_disable_the_limit(name: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(**{name: 0})


@pytest.mark.parametrize("name", ["update_retry_on_conflict", "os_transport_max_retries"])
def test_zero_retries_is_allowed_but_negative_is_rejected(name: str) -> None:
    assert getattr(make_settings(**{name: 0}), name) == 0
    with pytest.raises(ValidationError):
        make_settings(**{name: -1})


@pytest.mark.parametrize(
    "name",
    [
        "os_request_timeout_seconds",
        "os_delete_by_query_timeout_seconds",
        "retry_backoff_initial_seconds",
        "retry_backoff_max_seconds",
        "deletion_poll_interval_seconds",
        "summary_rescan_min_interval_seconds",
        "llm_timeout_seconds",
    ],
)
def test_durations_must_be_greater_than_zero(name: str) -> None:
    assert getattr(make_settings(**{name: 0.001}), name) == 0.001
    for invalid in (0, 0.0, -1):
        with pytest.raises(ValidationError):
            make_settings(**{name: invalid})


def test_rescan_max_interval_below_the_min_interval_is_rejected() -> None:
    """間隔の上限が下限より短いと、間隔を伸ばすどころか縮めてしまう。"""
    settings = make_settings(
        summary_rescan_min_interval_seconds=120.0, summary_rescan_max_interval_seconds=120.0
    )
    assert settings.summary_rescan_max_interval_seconds == 120.0
    with pytest.raises(ValidationError):
        make_settings(
            summary_rescan_min_interval_seconds=120.0, summary_rescan_max_interval_seconds=119.9
        )
    with pytest.raises(ValidationError):
        make_settings(summary_rescan_max_interval_seconds=59.0)  # 既定の下限(60 秒)より短い


def test_deletion_poll_backoff_max_below_the_poll_interval_is_rejected() -> None:
    """上限が通常の間隔より短いと、失敗が続くほど間隔を縮めてしまう。"""
    settings = make_settings(
        deletion_poll_interval_seconds=10.0, deletion_poll_backoff_max_seconds=10.0
    )
    assert settings.deletion_poll_backoff_max_seconds == 10.0
    with pytest.raises(ValidationError):
        make_settings(deletion_poll_interval_seconds=10.0, deletion_poll_backoff_max_seconds=9.9)
    with pytest.raises(ValidationError):
        make_settings(deletion_poll_backoff_max_seconds=1.0)  # 既定の間隔(2 秒)より短い


def test_backoff_factor_below_one_is_rejected_because_it_would_shrink_the_wait() -> None:
    assert make_settings(retry_backoff_factor=1).retry_backoff_factor == 1
    with pytest.raises(ValidationError):
        make_settings(retry_backoff_factor=0.99)


def test_opensearch_connection_exposes_the_secret_value_to_the_client_config_only() -> None:
    settings = make_settings(
        opensearch_username="indexer", opensearch_password="s3cret", os_transport_max_retries=4
    )
    connection = settings.opensearch_connection()
    assert connection == OpenSearchConnectionConfig(
        url="http://opensearch:9200",
        username="indexer",
        password="s3cret",
        verify_certs=True,
        ca_certs_path=None,
        request_timeout_seconds=30.0,
        transport_max_retries=4,
        delete_by_query_timeout_seconds=600.0,
    )
    assert "s3cret" not in repr(settings)
    assert "s3cret" not in repr(connection)


def test_index_names_follow_the_settings() -> None:
    settings = make_settings(search_index_name="docs-alias", jobs_index_name="jobs-x")
    assert settings.index_names() == IndexNames(
        search_index="docs-alias", deletions="loreley-deletions", jobs="jobs-x"
    )


def test_extraction_config_follows_max_content_bytes() -> None:
    assert make_settings().extraction_config() == ExtractionConfig(max_content_bytes=5 * MIB)
    assert make_settings(max_content_bytes=1024).extraction_config() == ExtractionConfig(
        max_content_bytes=1024
    )


def test_registration_config_follows_the_settings() -> None:
    settings = make_settings(
        max_raw_bytes=1024,
        write_conflict_max_rereads=4,
        max_last_seen_ids=50,
        summary_enabled=True,
    )

    assert settings.registration_config() == RegistrationConfig(
        max_raw_bytes=1024,
        write_conflict_max_rereads=4,
        max_last_seen_ids=50,
        summary_enabled=True,
    )


def test_summarization_config_follows_the_settings() -> None:
    assert make_settings().summarization_config() == SummarizationConfig(
        enabled=False,
        concurrency=1,
        max_attempts=3,
        queue_size=100,
        rescan_page_size=100,
        rescan_min_interval_seconds=60.0,
        rescan_max_interval_seconds=3_600.0,
        write_conflict_max_rereads=3,
        retry_backoff_initial_seconds=1.0,
        retry_backoff_factor=2.0,
        retry_backoff_max_seconds=30.0,
        input_max_chars=30_000,
    )
    enabled = make_settings(summary_enabled=True, summary_concurrency=2, summary_queue_size=7)
    assert enabled.summarization_config().enabled is True
    assert enabled.summarization_config().concurrency == 2
    assert enabled.summarization_config().queue_size == 7


def test_lifecycle_config_follows_the_settings() -> None:
    assert make_settings().lifecycle_config() == LifecycleConfig(
        skip_oversize_id_limit=10_000,
        write_conflict_max_rereads=3,
        deletion_retention_count=20,
    )
    overridden = make_settings(
        skip_oversize_id_limit=5, write_conflict_max_rereads=4, deletion_retention_count=2
    )
    assert overridden.lifecycle_config() == LifecycleConfig(
        skip_oversize_id_limit=5, write_conflict_max_rereads=4, deletion_retention_count=2
    )


def test_delete_by_query_timeout_follows_its_own_setting_not_the_general_one() -> None:
    settings = make_settings(os_request_timeout_seconds=5, os_delete_by_query_timeout_seconds=900)
    connection = settings.opensearch_connection()
    assert connection.request_timeout_seconds == 5
    assert connection.delete_by_query_timeout_seconds == 900


def test_deletion_config_follows_the_settings() -> None:
    assert make_settings().deletion_config() == DeletionConfig(
        batch_size=100,
        max_deletion_targets=200_000,
        search_after_page_size=1_000,
        poll_interval_seconds=2.0,
        poll_backoff_max_seconds=300.0,
        delete_error_retry_attempts=3,
        retry_backoff_initial_seconds=1.0,
        retry_backoff_factor=2.0,
        retry_backoff_max_seconds=30.0,
        write_conflict_max_rereads=3,
        discard_max_attempts=20,
        delete_by_query_max_reruns=5,
    )
    overridden = make_settings(
        deletion_batch_size=7,
        max_deletion_targets=8,
        search_after_page_size=9,
        deletion_poll_interval_seconds=0.5,
        deletion_poll_backoff_max_seconds=20.0,
        delete_error_retry_attempts=2,
        retry_backoff_initial_seconds=0.1,
        retry_backoff_factor=3.0,
        retry_backoff_max_seconds=4.0,
        write_conflict_max_rereads=6,
        discard_max_attempts=5,
        delete_by_query_max_reruns=4,
    )
    assert overridden.deletion_config() == DeletionConfig(
        batch_size=7,
        max_deletion_targets=8,
        search_after_page_size=9,
        poll_interval_seconds=0.5,
        poll_backoff_max_seconds=20.0,
        delete_error_retry_attempts=2,
        retry_backoff_initial_seconds=0.1,
        retry_backoff_factor=3.0,
        retry_backoff_max_seconds=4.0,
        write_conflict_max_rereads=6,
        discard_max_attempts=5,
        delete_by_query_max_reruns=4,
    )


def test_api_config_follows_the_settings() -> None:
    assert make_settings().api_config() == ApiConfig(
        max_request_body_bytes=100 * MIB,
        max_batch_documents=50,
        max_batch_bytes=64 * MIB,
        max_raw_bytes=20 * MIB,
        max_last_seen_ids=1_000,
    )
    overridden = make_settings(
        max_request_body_bytes=8,
        max_batch_documents=2,
        max_batch_bytes=6,
        max_raw_bytes=4,
        max_last_seen_ids=5,
    )
    assert overridden.api_config() == ApiConfig(
        max_request_body_bytes=8,
        max_batch_documents=2,
        max_batch_bytes=6,
        max_raw_bytes=4,
        max_last_seen_ids=5,
    )


def test_the_port_must_be_a_valid_tcp_port() -> None:
    with pytest.raises(ValidationError):
        make_settings(http_port=0)


def test_the_log_level_accepts_only_known_names() -> None:
    assert make_settings(log_level="DEBUG").log_level == "DEBUG"
    with pytest.raises(ValidationError):
        make_settings(log_level="TRACE")


@pytest.mark.parametrize("written", ["info", "Info", "INFO", "warning", "error", "debug"])
def test_the_log_level_ignores_the_case(written: str) -> None:
    assert make_settings(log_level=written).log_level == written.upper()


def test_the_log_level_from_the_environment_ignores_the_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LORELEY_INDEXER_LOG_LEVEL", "warning")
    assert make_settings().log_level == "WARNING"


def test_the_log_level_rejects_a_non_string() -> None:
    with pytest.raises(ValidationError):
        make_settings(log_level=10)


# --- サイズ上限どうしの整合 ---


def test_the_default_and_the_maximum_size_limits_are_consistent() -> None:
    make_settings()  # 既定(20 / 64 / 100 MiB)
    make_settings(  # 上限(100 / 256 / 512 MiB)
        max_raw_bytes=100 * MIB, max_batch_bytes=256 * MIB, max_request_body_bytes=512 * MIB
    )


def test_a_raw_size_limit_above_the_batch_limit_is_rejected() -> None:
    assert make_settings(max_raw_bytes=64 * MIB, max_batch_bytes=64 * MIB).max_raw_bytes == 64 * MIB
    with pytest.raises(ValidationError, match="max_raw_bytes must not exceed max_batch_bytes"):
        make_settings(max_raw_bytes=64 * MIB + 1, max_batch_bytes=64 * MIB)


def test_a_batch_limit_that_base64_cannot_fit_in_the_request_body_limit_is_rejected() -> None:
    """base64 は約 4/3 倍。バッチ合計の上限まで届くリクエストが、ボディの上限で先に拒否される。"""
    ok = make_settings(max_raw_bytes=3, max_batch_bytes=3_000, max_request_body_bytes=4_000)
    assert ok.max_batch_bytes == 3_000  # 3000 * 4/3 == 4000: ちょうど収まる
    with pytest.raises(ValidationError, match="must not exceed max_request_body_bytes"):
        make_settings(max_raw_bytes=3, max_batch_bytes=3_000, max_request_body_bytes=3_999)


def test_secrets_do_not_appear_in_the_repr_or_dumps_of_the_settings() -> None:
    settings = make_settings(opensearch_username="admin", opensearch_password="SENTINEL-PASSWORD")

    rendered = [
        repr(settings),
        str(settings),
        settings.model_dump_json(),
        repr(settings.model_dump()),
        repr(settings.opensearch_connection()),
    ]

    assert all("SENTINEL-PASSWORD" not in text for text in rendered)


def test_a_validation_error_of_another_setting_does_not_show_the_password() -> None:
    with pytest.raises(ValidationError) as error_info:
        make_settings(opensearch_password="SENTINEL-PASSWORD", max_batch_documents=0)

    assert "SENTINEL-PASSWORD" not in str(error_info.value)
