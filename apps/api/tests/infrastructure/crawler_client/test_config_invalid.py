"""`config_invalid` の `message` の分解(B 2.5。C 4.5。C 11章 4)。"""

import pytest

from loreley_api.infrastructure.crawler_client import ConfigViolation
from loreley_api.infrastructure.crawler_client.config_invalid import (
    MESSAGE_MAX_CHARS,
    decompose,
    describe,
)


@pytest.mark.parametrize(
    ("message", "field", "detail"),
    [
        (
            "include_patterns[2]: `\\` を含む(エスケープはない)",
            "connector_config.include_patterns[2]",
            "`\\` を含む(エスケープはない)",
        ),
        ("root: `/` で始まる絶対パスでない", "connector_config.root", "`/` で始まる絶対パスでない"),
        # 前半が `connector_config` 自身のときだけ、プレフィックスを付けない。
        ("connector_config: オブジェクトでない", "connector_config", "オブジェクトでない"),
        ("connector_config: 未知の項目がある", "connector_config", "未知の項目がある"),
        ("follow_symlinks: 真偽値でない", "connector_config.follow_symlinks", "真偽値でない"),
        ("_private1: x", "connector_config._private1", "x"),
        # 最初の `: ` で分ける。詳細に `: ` があってもよい。
        ("root: a: b", "connector_config.root", "a: b"),
        ("exclude_patterns[0]: x", "connector_config.exclude_patterns[0]", "x"),
        ("exclude_patterns[12345]: x", "connector_config.exclude_patterns[12345]", "x"),
    ],
)
def test_a_well_formed_message_is_decomposed_into_field_and_detail(
    message: str, field: str, detail: str
) -> None:
    assert decompose(message) == ConfigViolation(field=field, detail=detail)


@pytest.mark.parametrize(
    "message",
    [
        "root\n: x",  # 前半に改行を含む
        "root\n: ",
        "root:x",  # `: ` がない
        "root:",
        "root",
        "",
        ": x",  # 前半が空
        "root: ",  # 後半が空
        "1root: x",  # 数字で始まる
        "ro ot: x",
        "root.sub: x",  # `.` は前半に含められない
        "include_patterns[]: x",
        "include_patterns[-1]: x",
        "include_patterns[a]: x",
        "include_patterns[1][2]: x",
        "include_patterns[1]x: x",
        "ルート: x",
        "root ← x",
    ],
)
def test_a_message_that_does_not_fit_the_format_is_not_decomposed(message: str) -> None:
    assert decompose(message) is None


def test_a_trailing_newline_in_the_detail_is_kept_as_is() -> None:
    """後半は固定文として、加工せずに通す(前半だけが形の検査の対象)。"""
    assert decompose("root: x\n") == ConfigViolation("connector_config.root", "x\n")


def test_a_head_with_a_trailing_newline_does_not_match() -> None:
    """`re.match` + `$` なら通ってしまう前半(末尾の改行)を、`fullmatch` は通さない。"""
    assert decompose("root\n: detail") is None


@pytest.mark.parametrize("message", [None, 123, ["root: x"], {"root": "x"}, b"root: x", True])
def test_a_message_that_is_not_a_string_is_not_decomposed(message: object) -> None:
    assert decompose(message) is None


def test_a_message_of_512_characters_may_be_truncated_and_is_not_decomposed() -> None:
    message = "root: " + "あ" * (MESSAGE_MAX_CHARS - len("root: "))
    assert len(message) == MESSAGE_MAX_CHARS

    assert decompose(message) is None


def test_a_message_of_511_characters_is_decomposed() -> None:
    message = "root: " + "あ" * (MESSAGE_MAX_CHARS - 1 - len("root: "))
    assert len(message) == MESSAGE_MAX_CHARS - 1

    assert decompose(message) is not None


def test_describe_keeps_the_original_message_and_the_decomposition() -> None:
    result = describe("root: `/` で始まる絶対パスでない")

    assert result.crawler_message == "root: `/` で始まる絶対パスでない"
    assert result.violation == ConfigViolation(
        "connector_config.root", "`/` で始まる絶対パスでない"
    )


def test_describe_of_an_undecomposable_message_keeps_the_message_only() -> None:
    result = describe("free text")

    assert result.crawler_message == "free text"
    assert result.violation is None


def test_describe_cuts_an_overlong_crawler_message_to_512_characters() -> None:
    result = describe("x" * 600)

    assert result.crawler_message == "x" * MESSAGE_MAX_CHARS
    assert result.violation is None
