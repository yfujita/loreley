import hashlib
import unicodedata

import pytest

from loreley_indexer.documents.extraction.normalization import (
    _REMOVED_CHARS,
    hash_text,
    normalize_text,
    truncate_to_utf8_bytes,
)


def test_newlines_are_unified_to_lf() -> None:
    assert normalize_text("a\r\nb\rc\nd") == "a\nb\nc\nd"


def test_nul_and_control_characters_are_removed_but_tab_and_newline_stay() -> None:
    assert normalize_text("a\x00b\x07c\x1bd\x7fe\x85f\tg\nh") == "abcdef\tg\nh"


def test_removed_chars_pattern_matches_the_control_and_surrogate_categories() -> None:
    """正規表現(速度のため)が、一般カテゴリ Cc・Cs(タブと改行を除く)と同じ範囲であること。

    全コードポイントを 1 つの文字列にして一括で除き、残らなかった文字を数える。
    """
    all_code_points = "".join(map(chr, range(0x110000)))

    removed = {
        ord(char) for char in set(all_code_points) - set(_REMOVED_CHARS.sub("", all_code_points))
    }

    expected = {
        code_point
        for code_point in range(0x110000)
        if unicodedata.category(chr(code_point)) in ("Cc", "Cs") and code_point not in (0x09, 0x0A)
    }
    assert removed == expected


def test_lone_surrogates_are_removed() -> None:
    assert normalize_text("a\ud800b\udfffc") == "abc"


def test_trailing_whitespace_of_each_line_is_removed() -> None:
    assert normalize_text("a  \nb\t\nc　\nd") == "a\nb\nc\nd"


def test_leading_whitespace_is_kept() -> None:
    assert normalize_text("  a\n\tb") == "  a\n\tb"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a\n\n\nb", "a\n\n\nb"),  # 空行 2 つは圧縮しない
        ("a\n\n\n\nb", "a\n\n\nb"),  # 空行 3 つは 2 つにする
        ("a\n\n\n\n\n\n\nb", "a\n\n\nb"),
        ("a\n \n\t\n  \nb", "a\n\n\nb"),  # 空白だけの行も空行として数える
        ("a\n\nb", "a\n\nb"),
    ],
)
def test_three_or_more_blank_lines_are_compressed_to_two(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_text_is_normalized_to_nfc() -> None:
    nfd = unicodedata.normalize("NFD", "がぎ")
    assert nfd != "がぎ"
    assert normalize_text(nfd) == "がぎ"


def test_nfkc_is_not_applied() -> None:
    assert normalize_text("ｱｲｳ①㈱") == "ｱｲｳ①㈱"


def test_characters_that_become_composable_after_removing_a_control_are_still_nfc() -> None:
    assert normalize_text("e\x00́") == "é"


def test_lone_surrogates_are_removed_so_the_text_can_be_hashed() -> None:
    normalized = normalize_text("a\ud800b")
    assert normalized == "ab"
    hash_text(normalized)


def test_normalization_is_idempotent() -> None:
    raw = "a \r\n\r\n\r\n\r\nb\x00́ \n"
    once = normalize_text(raw)
    assert normalize_text(once) == once


def test_hash_text_is_sha256_hex_of_the_utf8_bytes() -> None:
    assert hash_text("hello") == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert hash_text("日本語") == hashlib.sha256("日本語".encode()).hexdigest()


# --- 切り詰め ---


def test_text_within_the_limit_is_not_truncated() -> None:
    assert truncate_to_utf8_bytes("abc", 3) == ("abc", False)
    assert truncate_to_utf8_bytes("あい", 6) == ("あい", False)


def test_ascii_text_over_the_limit_is_cut_at_the_limit() -> None:
    assert truncate_to_utf8_bytes("abcd", 3) == ("abc", True)


@pytest.mark.parametrize(
    ("max_bytes", "expected"),
    [(9, "あいう"), (8, "あい"), (7, "あい"), (6, "あい"), (5, "あ"), (3, "あ"), (2, ""), (0, "")],
)
def test_truncation_never_splits_a_character(max_bytes: int, expected: str) -> None:
    text = "あいうえ"
    truncated, was_truncated = truncate_to_utf8_bytes(text, max_bytes)
    assert truncated == expected
    assert was_truncated is True
    assert len(truncated.encode("utf-8")) <= max_bytes


def test_truncation_handles_four_byte_characters() -> None:
    assert truncate_to_utf8_bytes("a😀b", 4) == ("a", True)
    assert truncate_to_utf8_bytes("a😀b", 5) == ("a😀", True)
