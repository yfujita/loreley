"""`validate_config`(FS 設計書 2.2。10章 #5 の違反・#21)。I/O をしない。"""

from typing import Any

import pytest

from loreley_crawler.connectors.filesystem import (
    FileSystemConnectorType,
    FileSystemSettings,
)
from loreley_crawler.connectors.filesystem.config import parse_config
from loreley_crawler.connectors.interface import (
    ConnectorError,
    ErrorCategory,
    ErrorScope,
    RetryHint,
)
from tests.fakes.fake_fs_ops import ScriptedFsOps

SETTINGS = FileSystemSettings()


def invalid_reason(connector_config: object) -> str:
    with pytest.raises(ConnectorError) as exc_info:
        parse_config(connector_config, SETTINGS)
    error = exc_info.value
    assert error.category is ErrorCategory.CONFIG_INVALID
    assert error.scope is ErrorScope.SOURCE
    assert error.retry is RetryHint.PERMANENT
    return error.message


def test_a_minimal_config_uses_the_defaults() -> None:
    config = parse_config({"root": "/mnt/docs"}, SETTINGS)

    assert config.root == "/mnt/docs"
    assert config.include_patterns == ()
    assert config.exclude_patterns == ()
    assert config.follow_symlinks is False
    assert config.include_hidden is False


def test_the_example_of_the_design_is_valid() -> None:
    config = parse_config(
        {
            "root": "/mnt/docs",
            "include_patterns": ["**/*.rst"],
            "exclude_patterns": ["**/lost+found", "archive/**"],
            "follow_symlinks": False,
            "include_hidden": False,
        },
        SETTINGS,
    )

    assert len(config.include_patterns) == 1
    assert len(config.exclude_patterns) == 2


@pytest.mark.parametrize("connector_config", [None, [], "root", 1, ["/mnt"]])
def test_the_config_must_be_an_object(connector_config: object) -> None:
    assert "オブジェクトでない" in invalid_reason(connector_config)


def test_an_unknown_key_is_rejected_without_echoing_the_key() -> None:
    reason = invalid_reason({"root": "/mnt", "include_pattern": ["*.rst"], "SECRET-KEY": 1})

    assert "未知の項目" in reason
    assert "include_pattern" not in reason
    assert "SECRET-KEY" not in reason


def test_root_is_required() -> None:
    assert invalid_reason({}).startswith("root:")


@pytest.mark.parametrize("item", ["root", "include_patterns", "exclude_patterns"])
def test_null_is_a_type_violation(item: str) -> None:
    config: dict[str, Any] = {"root": "/mnt", item: None}

    assert invalid_reason(config).startswith(f"{item}:")


@pytest.mark.parametrize("item", ["follow_symlinks", "include_hidden"])
@pytest.mark.parametrize("value", [None, 0, 1, "true", "false", [], {}])
def test_flags_accept_only_booleans(item: str, value: object) -> None:
    assert invalid_reason({"root": "/mnt", item: value}).startswith(f"{item}:")


@pytest.mark.parametrize("item", ["follow_symlinks", "include_hidden"])
def test_flags_accept_true_and_false(item: str) -> None:
    attribute = item
    assert getattr(parse_config({"root": "/mnt", item: True}, SETTINGS), attribute) is True
    assert getattr(parse_config({"root": "/mnt", item: False}, SETTINGS), attribute) is False


@pytest.mark.parametrize(
    "root",
    [
        "",
        "mnt/docs",  # 相対パス
        "./docs",
        "/mnt/../docs",  # `.`・`..` のセグメント
        "/mnt/./docs",
        "/mnt/..",
        "/mnt//docs",  # 連続する `/`
        "//",
        "/mnt/docs//",
        "/mnt/\x00docs",
        "/mnt/\ud800docs",
        123,
        ["/mnt"],
    ],
)
def test_invalid_roots_are_rejected(root: object) -> None:
    assert invalid_reason({"root": root}).startswith("root:")


@pytest.mark.parametrize(
    ("root", "expected"),
    [
        ("/mnt/docs", "/mnt/docs"),
        ("/mnt/docs/", "/mnt/docs"),  # 末尾の `/` は除いて保持する
        ("/", "/"),  # `/` だけは有効
        ("/mnt/..docs", "/mnt/..docs"),
        ("/mnt/資料", "/mnt/資料"),
    ],
)
def test_valid_roots_are_normalized(root: str, expected: str) -> None:
    assert parse_config({"root": root}, SETTINGS).root == expected


@pytest.mark.parametrize("item", ["include_patterns", "exclude_patterns"])
def test_patterns_must_be_an_array_of_strings(item: str) -> None:
    for value in ("*.md", {"a": "b"}, ("*.md",)):
        assert invalid_reason({"root": "/mnt", item: value}).startswith(f"{item}:")
    assert invalid_reason({"root": "/mnt", item: ["*.md", 1]}).startswith(f"{item}[1]:")


@pytest.mark.parametrize("item", ["include_patterns", "exclude_patterns"])
def test_pattern_count_boundary(item: str) -> None:
    assert parse_config({"root": "/mnt", item: ["*.md"] * 100}, SETTINGS) is not None
    assert invalid_reason({"root": "/mnt", item: ["*.md"] * 101}).startswith(f"{item}:")


@pytest.mark.parametrize("item", ["include_patterns", "exclude_patterns"])
def test_pattern_length_boundary_is_in_utf8_bytes(item: str) -> None:
    assert parse_config({"root": "/mnt", item: ["a" * 1024]}, SETTINGS) is not None
    assert invalid_reason({"root": "/mnt", item: ["a" * 1025]}).startswith(f"{item}[0]:")
    # 文字数は 1024 以下でも、UTF-8 で 1024 バイトを超える。
    assert invalid_reason({"root": "/mnt", item: ["あ" * 342]}).startswith(f"{item}[0]:")


@pytest.mark.parametrize(
    "pattern", ["**.md", "**/**", "a/**/**", "/a", "a\\b", "../a", "a/..", "", "a\x00"]
)
def test_violating_patterns_report_the_item_and_index(pattern: str) -> None:
    reason = invalid_reason({"root": "/mnt", "exclude_patterns": ["*.md", pattern]})

    assert reason.startswith("exclude_patterns[1]:")


def test_a_violation_never_echoes_the_input_value() -> None:
    reason = invalid_reason({"root": "/SECRET-ROOT/../x"})

    assert "SECRET" not in reason


def test_the_limits_can_be_changed_by_the_settings() -> None:
    settings = FileSystemSettings(max_patterns=2, max_pattern_bytes=5)

    assert parse_config({"root": "/m", "include_patterns": ["a", "bbbbb"]}, settings) is not None
    with pytest.raises(ConnectorError):
        parse_config({"root": "/m", "include_patterns": ["a", "b", "c"]}, settings)
    with pytest.raises(ConnectorError):
        parse_config({"root": "/m", "include_patterns": ["bbbbbb"]}, settings)


def test_validate_config_does_no_io() -> None:
    fs = ScriptedFsOps()
    connector_type = FileSystemConnectorType(fs)

    connector_type.validate_config({"root": "/does/not/exist", "follow_symlinks": True})
    with pytest.raises(ConnectorError):
        connector_type.validate_config({"root": "relative"})

    assert fs.behavior.calls == []
    assert fs.opened_flags == []


def test_the_default_limits_are_the_documented_provisional_values() -> None:
    settings = FileSystemSettings()

    assert (settings.max_patterns, settings.max_pattern_bytes) == (100, 1024)
    assert settings.read_chunk_bytes == 1024 * 1024
    assert settings.message_path_max_chars == 200


@pytest.mark.parametrize(
    "field",
    [
        "max_patterns",
        "max_pattern_bytes",
        "read_chunk_bytes",
        "message_path_max_chars",
    ],
)
def test_settings_must_be_at_least_one(field: str) -> None:
    assert getattr(FileSystemSettings(**{field: 1}), field) == 1
    for invalid_value in (0, -1):
        with pytest.raises(ValueError, match=field):
            FileSystemSettings(**{field: invalid_value})
