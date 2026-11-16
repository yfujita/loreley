import pytest

from loreley_crawler.common.display_text import (
    REPLACEMENT_CHARACTER,
    escape_control_characters,
    format_display_text,
    replace_lone_surrogates,
)


def test_each_lone_surrogate_becomes_one_replacement_character() -> None:
    # Linux の UTF-8 でないファイル名は、バイトごとに 1 つの孤立サロゲート(U+DC80〜U+DCFF)になる。
    assert replace_lone_surrogates("a\udc82\udca0b") == f"a{REPLACEMENT_CHARACTER * 2}b"
    assert replace_lone_surrogates("\ud800") == REPLACEMENT_CHARACTER
    assert replace_lone_surrogates("\udfff") == REPLACEMENT_CHARACTER


def test_the_result_of_the_replacement_can_be_encoded_as_utf8() -> None:
    value = replace_lone_surrogates("docs/\udc82\udca0.txt")
    assert value.encode("utf-8").decode("utf-8") == value


def test_text_without_surrogates_is_unchanged() -> None:
    assert replace_lone_surrogates("日本語 ABC \U0001f600 �") == "日本語 ABC \U0001f600 �"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("a\nb", "a\\nb"),
        ("a\rb", "a\\rb"),
        ("a\tb", "a\\tb"),
        ("a\x00b", "a\\x00b"),
        ("a\x1bb", "a\\x1bb"),
        ("a\x7fb", "a\\x7fb"),
        ("a\x85b", "a\\x85b"),  # C1 制御文字(NEL)
        ("日本語 a b", "日本語 a b"),
    ],
)
def test_control_characters_are_escaped(value: str, expected: str) -> None:
    assert escape_control_characters(value) == expected


def test_an_escaped_name_cannot_forge_a_log_line() -> None:
    escaped = escape_control_characters("report.txt\nERROR forged line")
    assert "\n" not in escaped


def test_backslash_itself_is_left_as_is() -> None:
    assert escape_control_characters("a\\b") == "a\\b"


def test_format_applies_replacement_escaping_and_truncation() -> None:
    assert format_display_text("a\udc80\nb", max_chars=100) == f"a{REPLACEMENT_CHARACTER}\\nb"


def test_format_truncates_to_max_chars() -> None:
    assert format_display_text("abcdef", max_chars=3) == "abc"
    assert format_display_text("abc", max_chars=3) == "abc"
    assert format_display_text("abc", max_chars=0) == ""


def test_the_length_limit_applies_to_the_escaped_text() -> None:
    # `\n` は 2 文字に増えるので、4 文字の枠には 2 つ目の改行が収まらない。
    assert format_display_text("a\n\nb", max_chars=4) == "a\\n"
    assert format_display_text("a\n\nb", max_chars=5) == "a\\n\\n"


def test_truncation_does_not_cut_an_escape_sequence() -> None:
    assert format_display_text("ab\ncd", max_chars=3) == "ab"
    assert format_display_text("ab\x00cd", max_chars=5) == "ab"
    assert format_display_text("ab\x00cd", max_chars=6) == "ab\\x00"


def test_the_result_never_exceeds_max_chars() -> None:
    value = "\n\x00\udc80x" * 200
    for max_chars in (0, 1, 7, 200, 512):
        assert len(format_display_text(value, max_chars=max_chars)) <= max_chars


def test_truncation_counts_characters_not_bytes() -> None:
    assert format_display_text("日本語のファイル名", max_chars=4) == "日本語の"


def test_format_rejects_a_negative_limit() -> None:
    with pytest.raises(ValueError, match="max_chars"):
        format_display_text("a", max_chars=-1)
