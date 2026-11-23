import os

import pytest
from pydantic import BaseModel, ValidationError

from loreley_api.config import (
    MAX_REPORTED_SETTING_ERRORS,
    ConfigError,
    Settings,
    describe_settings_errors,
    load_settings,
)

PREFIX = "LORELEY_API_"


@pytest.fixture(autouse=True)
def clean_api_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """実行環境の `LORELEY_API_*` が、既定値のテストに混ざらないようにする。"""
    for name in [name for name in os.environ if name.startswith(PREFIX)]:
        monkeypatch.delenv(name)


def set_environment(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for name, value in values.items():
        monkeypatch.setenv(PREFIX + name.upper(), value)


def config_error_of(monkeypatch: pytest.MonkeyPatch, **values: str) -> ConfigError:
    set_environment(monkeypatch, **values)
    with pytest.raises(ConfigError) as error_info:
        load_settings()
    return error_info.value


def test_the_defaults() -> None:
    settings = load_settings()

    assert settings.host == "127.0.0.1"
    assert settings.port == 8080
    assert settings.log_level == "INFO"


def test_the_settings_are_exactly_host_port_and_log_level() -> None:
    """基盤の設定は 3 つだけ(機能の設定は、その機能を実装するときに足す)。

    admin など機能の設定を足すときは、この期待値を更新する。
    """
    assert set(Settings.model_fields) == {"host", "port", "log_level"}


def test_environment_variables_override_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    set_environment(monkeypatch, host="0.0.0.0", port="9090", log_level="DEBUG")

    settings = load_settings()

    assert settings.host == "0.0.0.0"
    assert settings.port == 9090
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize(("value", "expected"), [("debug", "DEBUG"), ("Warning", "WARNING")])
def test_the_log_level_accepts_any_case(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: str
) -> None:
    set_environment(monkeypatch, log_level=value)

    assert load_settings().log_level == expected


@pytest.mark.parametrize("port", ["1", "65535"])
def test_the_port_accepts_the_bounds(monkeypatch: pytest.MonkeyPatch, port: str) -> None:
    set_environment(monkeypatch, port=port)

    assert load_settings().port == int(port)


def test_an_unrelated_environment_variable_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    set_environment(monkeypatch, unknown_setting="x")

    assert load_settings().port == 8080


def test_the_settings_are_frozen() -> None:
    settings = load_settings()

    with pytest.raises(ValueError, match="frozen"):
        settings.port = 1


@pytest.mark.parametrize(
    ("name", "value", "kind"),
    [
        ("port", "0", "greater_than_equal"),
        ("port", "65536", "less_than_equal"),
        ("port", "SENTINEL-PORT", "int_parsing"),
        ("log_level", "SENTINEL-LEVEL", "literal_error"),
        ("log_level", "TRACE", "literal_error"),
    ],
)
def test_an_invalid_value_reports_the_field_and_the_kind_only(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str, kind: str
) -> None:
    """完全一致なので、`input`(値)・`ctx`(上限値)・`msg`(本文)を付け足すと失敗する。"""
    error = config_error_of(monkeypatch, **{name: value})

    assert str(error) == f"invalid settings: {name}: {kind}"
    assert value not in str(error)
    assert error.__context__ is None  # 値を持つ元の `ValidationError` を連鎖させない
    assert error.__cause__ is None


def test_every_error_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    error = config_error_of(monkeypatch, port="SENTINEL-PORT", log_level="SENTINEL-LEVEL")

    assert str(error) == "invalid settings: port: int_parsing; log_level: literal_error"


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
