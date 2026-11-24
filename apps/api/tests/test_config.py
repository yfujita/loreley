"""設定の検証(C 11章 13)。違反は、値を出さずに起動失敗(`ConfigError`)にする。"""

import os
import tomllib
import zoneinfo
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from pydantic import BaseModel, ValidationError

from loreley_api.config import (
    MAX_REPORTED_SETTING_ERRORS,
    ConfigError,
    Settings,
    describe_settings_errors,
    load_config,
    load_settings,
)

PREFIX = "LORELEY_API_"
REQUIRED = {
    "opensearch_url": "http://opensearch:9200",
    "crawler_url": "http://crawler:8001",
    "indexer_url": "http://indexer:8000",
}


@pytest.fixture(autouse=True)
def clean_api_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """実行環境の `LORELEY_API_*` が、既定値のテストに混ざらないようにし、必須の値だけ入れる。"""
    for name in [name for name in os.environ if name.startswith(PREFIX)]:
        monkeypatch.delenv(name)
    set_environment(monkeypatch, **REQUIRED)


PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]


def set_environment(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for name, value in values.items():
        monkeypatch.setenv(PREFIX + name.upper(), value)


def config_error_of(monkeypatch: pytest.MonkeyPatch, **values: str) -> ConfigError:
    set_environment(monkeypatch, **values)
    with pytest.raises(ConfigError) as error_info:
        load_config()
    return error_info.value


def assert_fails_without_the_value(
    monkeypatch: pytest.MonkeyPatch, *, name: str, value: str, kind: str
) -> None:
    """完全一致なので、`input`(値)・`ctx`(上限値)・`msg`(本文)を付け足すと失敗する。"""
    error = config_error_of(monkeypatch, **{name: value})

    assert str(error) == f"invalid settings: {name}: {kind}"
    assert value not in str(error)
    assert error.__context__ is None  # 値を持つ元の `ValidationError` を連鎖させない
    assert error.__cause__ is None


# --- 既定値と、環境変数での上書き ---


def test_the_defaults() -> None:
    config = load_config()

    assert (config.host, config.port, config.log_level) == ("127.0.0.1", 8080, "INFO")
    assert config.opensearch.url == "http://opensearch:9200"
    assert config.opensearch.username is None
    assert config.opensearch.password is None
    assert config.opensearch.verify_certs is True
    assert config.opensearch.ca_certs_path is None
    assert config.opensearch.request_timeout_seconds == 10
    assert config.opensearch.max_retries == 2
    assert config.opensearch.probe_timeout_seconds == 3
    index_names = config.index_names
    assert (index_names.sources, index_names.jobs) == ("loreley-sources", "loreley-jobs")
    assert (index_names.deletions, index_names.search) == ("loreley-deletions", "loreley-documents")
    assert config.crawler_client.base_url == "http://crawler:8001"
    assert config.crawler_client.connect_timeout_seconds == 3
    assert config.crawler_client.response_timeout_seconds == 60
    assert config.http_probe.timeout_seconds == 3
    admin = config.admin
    assert (admin.crawler_url, admin.indexer_url) == ("http://crawler:8001", "http://indexer:8000")
    assert admin.dashboards_health_url is None
    assert admin.embedding_health_url is None
    assert admin.llm_health_url is None
    assert admin.probe_timeout_seconds == 3
    assert admin.web_dist_dir == "/app/web"
    assert admin.cron_timezone is None
    assert admin.dashboards_url is None
    assert admin.admitting_lock_grace_seconds == 60
    assert admin.openapi_enabled is False


def test_the_settings_are_exactly_the_documented_variables() -> None:
    """C 7.2 の一覧(`LORELEY_API_` を除く名前の小文字)。足す・消すときは、設計書と揃える。"""
    assert set(Settings.model_fields) == {
        "host",
        "port",
        "log_level",
        "opensearch_url",
        "opensearch_username",
        "opensearch_password",
        "opensearch_verify_certs",
        "opensearch_ca_certs_path",
        "opensearch_request_timeout_seconds",
        "opensearch_max_retries",
        "sources_index_name",
        "jobs_index_name",
        "deletions_index_name",
        "search_index_name",
        "crawler_url",
        "indexer_url",
        "crawler_connect_timeout_seconds",
        "crawler_response_timeout_seconds",
        "health_probe_timeout_seconds",
        "dashboards_health_url",
        "embedding_health_url",
        "llm_health_url",
        "dashboards_url",
        "cron_timezone",
        "admitting_lock_grace_seconds",
        "openapi_enabled",
        "web_dist_dir",
    }


def test_environment_variables_override_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    set_environment(
        monkeypatch,
        host="0.0.0.0",
        port="9090",
        log_level="DEBUG",
        opensearch_username="reader",
        opensearch_password="secret",
        opensearch_verify_certs="false",
        opensearch_ca_certs_path="/certs/ca.pem",
        opensearch_request_timeout_seconds="20.5",
        opensearch_max_retries="0",
        sources_index_name="s",
        jobs_index_name="j",
        deletions_index_name="d",
        search_index_name="alias",
        crawler_connect_timeout_seconds="1",
        crawler_response_timeout_seconds="600",
        health_probe_timeout_seconds="30",
        dashboards_health_url="http://dashboards:5601/api/status?x=1",
        embedding_health_url="https://embedding.example/health",
        llm_health_url="http://llm/healthz",
        dashboards_url="https://dashboards.example/app",
        cron_timezone="Asia/Tokyo",
        admitting_lock_grace_seconds="3600",
        openapi_enabled="true",
        web_dist_dir="/srv/web",
    )

    config = load_config()

    assert (config.host, config.port, config.log_level) == ("0.0.0.0", 9090, "DEBUG")
    assert config.opensearch.username == "reader"
    assert config.opensearch.password == "secret"
    assert config.opensearch.verify_certs is False
    assert config.opensearch.ca_certs_path == "/certs/ca.pem"
    assert config.opensearch.request_timeout_seconds == 20.5
    assert config.opensearch.max_retries == 0
    assert config.opensearch.probe_timeout_seconds == 30
    assert (config.index_names.sources, config.index_names.jobs) == ("s", "j")
    assert (config.index_names.deletions, config.index_names.search) == ("d", "alias")
    assert config.crawler_client.connect_timeout_seconds == 1
    assert config.crawler_client.response_timeout_seconds == 600
    admin = config.admin
    assert admin.dashboards_health_url == "http://dashboards:5601/api/status?x=1"
    assert admin.embedding_health_url == "https://embedding.example/health"
    assert admin.llm_health_url == "http://llm/healthz"
    assert admin.dashboards_url == "https://dashboards.example/app"
    assert admin.cron_timezone == "Asia/Tokyo"
    assert admin.admitting_lock_grace_seconds == 3600
    assert admin.openapi_enabled is True
    assert admin.web_dist_dir == "/srv/web"


@pytest.mark.parametrize(("value", "expected"), [("debug", "DEBUG"), ("Warning", "WARNING")])
def test_the_log_level_accepts_any_case(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: str
) -> None:
    set_environment(monkeypatch, log_level=value)

    assert load_config().log_level == expected


def test_an_unrelated_environment_variable_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    set_environment(monkeypatch, unknown_setting="x")

    assert load_config().port == 8080


def test_the_settings_are_frozen() -> None:
    settings = load_settings()

    with pytest.raises(ValueError, match="frozen"):
        settings.port = 1


def test_the_password_is_not_in_the_repr_of_the_config(monkeypatch: pytest.MonkeyPatch) -> None:
    set_environment(monkeypatch, opensearch_username="u", opensearch_password="SENTINEL-SECRET")

    config = load_config()

    assert config.opensearch.password == "SENTINEL-SECRET"
    assert "SENTINEL-SECRET" not in repr(config)
    assert "SENTINEL-SECRET" not in repr(load_settings())


# --- 必須の欠落 ---


@pytest.mark.parametrize("name", ["opensearch_url", "crawler_url", "indexer_url"])
def test_a_missing_required_variable_fails_by_name(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.delenv(PREFIX + name.upper())

    with pytest.raises(ConfigError) as error_info:
        load_config()

    assert str(error_info.value) == f"invalid settings: {name}: missing"


def test_every_missing_required_variable_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in REQUIRED:
        monkeypatch.delenv(PREFIX + name.upper())

    with pytest.raises(ConfigError) as error_info:
        load_config()

    assert str(error_info.value) == (
        "invalid settings: opensearch_url: missing; crawler_url: missing; indexer_url: missing"
    )


# --- 範囲 ---


@pytest.mark.parametrize("port", ["1", "65535"])
def test_the_port_accepts_the_bounds(monkeypatch: pytest.MonkeyPatch, port: str) -> None:
    set_environment(monkeypatch, port=port)

    assert load_config().port == int(port)


@pytest.mark.parametrize(
    ("name", "lowest_valid", "highest_valid"),
    [
        ("opensearch_request_timeout_seconds", "0.001", "120"),
        ("crawler_connect_timeout_seconds", "0.001", "60"),
        ("crawler_response_timeout_seconds", "0.001", "600"),
        ("health_probe_timeout_seconds", "0.001", "30"),
        ("admitting_lock_grace_seconds", "0.001", "3600"),
        ("opensearch_max_retries", "0", "5"),
    ],
)
def test_numeric_settings_accept_the_bounds(
    monkeypatch: pytest.MonkeyPatch, name: str, lowest_valid: str, highest_valid: str
) -> None:
    for value in (lowest_valid, highest_valid):
        set_environment(monkeypatch, **{name: value})
        load_config()


@pytest.mark.parametrize(
    ("name", "value", "kind"),
    [
        ("port", "0", "greater_than_equal"),
        ("port", "65536", "less_than_equal"),
        ("port", "SENTINEL-PORT", "int_parsing"),
        ("log_level", "SENTINEL-LEVEL", "literal_error"),
        ("log_level", "TRACE", "literal_error"),
        ("opensearch_request_timeout_seconds", "0", "greater_than"),
        ("opensearch_request_timeout_seconds", "-1", "greater_than"),
        ("opensearch_request_timeout_seconds", "120.5", "less_than_equal"),
        ("opensearch_request_timeout_seconds", "SENTINEL-NUMBER", "float_parsing"),
        ("opensearch_max_retries", "-1", "greater_than_equal"),
        ("opensearch_max_retries", "6", "less_than_equal"),
        ("opensearch_max_retries", "1.5", "int_parsing"),
        ("crawler_connect_timeout_seconds", "0", "greater_than"),
        ("crawler_connect_timeout_seconds", "61", "less_than_equal"),
        ("crawler_response_timeout_seconds", "0", "greater_than"),
        ("crawler_response_timeout_seconds", "601", "less_than_equal"),
        ("health_probe_timeout_seconds", "0", "greater_than"),
        ("health_probe_timeout_seconds", "31", "less_than_equal"),
        ("admitting_lock_grace_seconds", "0", "greater_than"),
        ("admitting_lock_grace_seconds", "3601", "less_than_equal"),
        ("opensearch_verify_certs", "SENTINEL-BOOL", "bool_parsing"),
        ("openapi_enabled", "SENTINEL-BOOL", "bool_parsing"),
        ("sources_index_name", "", "string_too_short"),
        ("web_dist_dir", "", "string_too_short"),
    ],
)
def test_an_invalid_value_reports_the_field_and_the_kind_only(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str, kind: str
) -> None:
    error = config_error_of(monkeypatch, **{name: value})

    assert str(error) == f"invalid settings: {name}: {kind}"
    assert value not in str(error) or value == ""
    assert error.__context__ is None  # 値を持つ元の `ValidationError` を連鎖させない
    assert error.__cause__ is None


@pytest.mark.parametrize(
    ("value", "kind"),
    [("nan", "less_than_equal"), ("inf", "less_than_equal"), ("-inf", "greater_than")],
)
def test_a_timeout_that_is_not_a_finite_number_is_rejected(
    monkeypatch: pytest.MonkeyPatch, value: str, kind: str
) -> None:
    error = config_error_of(monkeypatch, health_probe_timeout_seconds=value)

    assert str(error) == f"invalid settings: health_probe_timeout_seconds: {kind}"


# --- URL ---

BAD_URLS = {
    "scheme": "ftp://host/path",
    "host": "http:///path",
    "userinfo": "http://SENTINEL-USER:SENTINEL-PASS@host",
    "fragment": "http://host/path#SENTINEL-FRAGMENT",
    "malformed": "http://host:SENTINEL-PORT",
}


@pytest.mark.parametrize("name", ["opensearch_url", "crawler_url", "indexer_url"])
@pytest.mark.parametrize(("reason", "value"), BAD_URLS.items())
def test_an_invalid_required_url_fails_without_showing_the_value(
    monkeypatch: pytest.MonkeyPatch, name: str, reason: str, value: str
) -> None:
    assert_fails_without_the_value(monkeypatch, name=name, value=value, kind=f"url_{reason}")


@pytest.mark.parametrize(
    "name", ["dashboards_health_url", "embedding_health_url", "llm_health_url", "dashboards_url"]
)
@pytest.mark.parametrize(("reason", "value"), BAD_URLS.items())
def test_an_invalid_optional_url_fails_without_showing_the_value(
    monkeypatch: pytest.MonkeyPatch, name: str, reason: str, value: str
) -> None:
    assert_fails_without_the_value(monkeypatch, name=name, value=value, kind=f"url_{reason}")


@pytest.mark.parametrize("name", ["crawler_url", "indexer_url"])
@pytest.mark.parametrize("value", ["https://host", "https://host:8001/"])
def test_crawler_and_indexer_urls_accept_http_only(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    assert_fails_without_the_value(monkeypatch, name=name, value=value, kind="url_scheme")


@pytest.mark.parametrize("name", ["crawler_url", "indexer_url"])
@pytest.mark.parametrize(
    "value",
    ["http://host/prefix", "http://host/prefix/", "http://host?SENTINEL=1", "http://host/?q"],
)
def test_crawler_and_indexer_urls_must_not_have_a_path_or_query(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    assert_fails_without_the_value(monkeypatch, name=name, value=value, kind="url_path")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://crawler:8001", "http://crawler:8001"),
        ("http://crawler:8001/", "http://crawler:8001"),
        ("HTTP://Crawler.Example", "http://Crawler.Example"),
        ("http://[::1]:8001/", "http://[::1]:8001"),
    ],
)
def test_the_trailing_slash_of_a_base_url_is_removed(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: str
) -> None:
    set_environment(monkeypatch, crawler_url=value, indexer_url=value)

    config = load_config()

    assert config.crawler_client.base_url == expected
    assert config.admin.crawler_url == expected
    assert config.admin.indexer_url == expected


def test_the_opensearch_and_health_urls_accept_https_a_path_and_a_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_environment(
        monkeypatch,
        opensearch_url="https://opensearch.example:9200/prefix",
        embedding_health_url="https://embedding.example/health?mode=quick",
        dashboards_url="http://localhost:5601/app/home",
    )

    config = load_config()

    assert config.opensearch.url == "https://opensearch.example:9200/prefix"
    assert config.admin.embedding_health_url == "https://embedding.example/health?mode=quick"
    assert config.admin.dashboards_url == "http://localhost:5601/app/home"


@pytest.mark.parametrize(
    "name", ["dashboards_health_url", "embedding_health_url", "llm_health_url", "dashboards_url"]
)
def test_an_empty_optional_url_is_not_set(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    set_environment(monkeypatch, **{name: ""})

    admin = load_config().admin

    assert getattr(admin, name) is None


# --- IANA 名 ---


@pytest.mark.parametrize("name", ["Asia/Tokyo", "UTC", "America/New_York"])
def test_a_valid_time_zone_is_accepted(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    set_environment(monkeypatch, cron_timezone=name)

    assert load_config().admin.cron_timezone == name


def test_a_valid_time_zone_is_accepted_without_the_os_zoneinfo_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """slim イメージ(OS に zoneinfo がない)でも、直接の依存の `tzdata` で IANA 名を解決できる。"""
    ZoneInfo.clear_cache()
    zoneinfo.reset_tzpath(to=[])
    try:
        set_environment(monkeypatch, cron_timezone="Asia/Tokyo")

        assert load_config().admin.cron_timezone == "Asia/Tokyo"
    finally:
        zoneinfo.reset_tzpath()
        ZoneInfo.clear_cache()


def test_tzdata_is_a_direct_dependency() -> None:
    """間接依存(`opensearch-py` 経由)のままだと、その依存が変わったときに黙って失われる。"""
    pyproject = tomllib.loads((PROJECT_DIRECTORY / "pyproject.toml").read_text(encoding="utf-8"))

    names = {
        canonicalize_name(Requirement(dependency).name)
        for dependency in pyproject["project"]["dependencies"]
    }
    assert "tzdata" in names


@pytest.mark.parametrize(
    "value",
    ["SENTINEL/Nowhere", "../../etc/passwd", "/etc/passwd", "America", " Asia"],
)
def test_an_invalid_time_zone_fails_without_showing_the_value(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    error = config_error_of(monkeypatch, cron_timezone=value)

    assert str(error) == "invalid settings: cron_timezone: timezone_invalid"
    assert error.__context__ is None


def test_an_empty_time_zone_is_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    set_environment(monkeypatch, cron_timezone="")

    assert load_config().admin.cron_timezone is None


# --- 組み合わせ ---


@pytest.mark.parametrize(
    "duplicates",
    [
        {"sources_index_name": "same", "jobs_index_name": "same"},
        {"jobs_index_name": "same", "deletions_index_name": "same"},
        {"deletions_index_name": "same", "search_index_name": "same"},
        {"sources_index_name": "same", "search_index_name": "same"},
        {"jobs_index_name": "loreley-sources"},
    ],
)
def test_the_four_index_names_must_differ(
    monkeypatch: pytest.MonkeyPatch, duplicates: dict[str, str]
) -> None:
    error = config_error_of(monkeypatch, **duplicates)

    assert str(error) == "invalid settings: settings: index_names_not_distinct"


@pytest.mark.parametrize("given", ["opensearch_username", "opensearch_password"])
def test_the_username_and_the_password_must_be_given_together(
    monkeypatch: pytest.MonkeyPatch, given: str
) -> None:
    error = config_error_of(monkeypatch, **{given: "SENTINEL-CREDENTIAL"})

    assert str(error) == "invalid settings: settings: opensearch_credentials_incomplete"
    assert "SENTINEL" not in str(error)


def test_every_error_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    error = config_error_of(
        monkeypatch, port="SENTINEL-PORT", log_level="SENTINEL-LEVEL", crawler_url="ftp://x"
    )

    assert str(error) == (
        "invalid settings: port: int_parsing; log_level: literal_error; crawler_url: url_scheme"
    )


def test_the_secret_is_not_shown_when_another_setting_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = config_error_of(
        monkeypatch,
        opensearch_username="u",
        opensearch_password="SENTINEL-SECRET",
        port="SENTINEL-PORT",
    )

    assert "SENTINEL" not in str(error)


def test_many_errors_are_reported_up_to_the_limit_with_the_rest_counted() -> None:
    """違反が上限を超えても、入力値は出さない(センチネルで確認)。"""

    class Many(BaseModel):
        a: int
        b: int
        c: int
        d: int
        e: int
        f: int
        g: int
        h: int
        i: int
        j: int
        k: int

    assert MAX_REPORTED_SETTING_ERRORS == 10
    with pytest.raises(ValidationError) as error_info:
        Many(**{name: "SENTINEL-VALUE" for name in Many.model_fields})

    description = describe_settings_errors(error_info.value)

    expected = [f"{name}: int_parsing" for name in "abcdefghij"] + ["... and 1 more"]
    assert description == "; ".join(expected)
    assert "SENTINEL" not in description


def test_loading_the_config_makes_no_network_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """起動時の検証は、外部に接続しない(`.invalid` のホストでも成功する)。"""
    set_environment(
        monkeypatch,
        opensearch_url="http://opensearch.invalid:9200",
        crawler_url="http://crawler.invalid:8001",
        indexer_url="http://indexer.invalid:8000",
    )

    assert load_config().opensearch.url == "http://opensearch.invalid:9200"
