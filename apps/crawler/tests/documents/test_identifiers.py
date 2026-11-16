"""`external_id` の規則適用と検証(interface 5.1・10章 #2・#3。architecture 12章 #19・#21)。"""

import itertools
import unicodedata

import pytest

from loreley_crawler.connectors.interface import (
    ConnectorError,
    ErrorCategory,
    ErrorScope,
    RetryHint,
)
from loreley_crawler.documents import (
    MAX_EXTERNAL_ID_BYTES,
    apply_external_id_rules,
    compute_document_id,
    escape_lone_surrogates_for_id,
)
from loreley_crawler.documents.identifiers import normalize_path_form
from tests.unicode_samples import (
    COMBINING_ACUTE_ACCENT as ACUTE,
)
from tests.unicode_samples import (
    GA_NFC,
    GA_NFD,
    GI_NFC,
    GI_NFD,
)

REPLACEMENT = chr(0xFFFD)


def invalid(raw: str) -> ConnectorError:
    with pytest.raises(ConnectorError) as exc_info:
        apply_external_id_rules(raw)
    return exc_info.value


# --- #2 規則 ---


def test_an_nfd_input_gives_the_same_id_as_the_nfc_input() -> None:
    nfc = f"資料/{GA_NFC}{GI_NFC}.txt"
    nfd = f"資料/{GA_NFD}{GI_NFD}.txt"

    assert apply_external_id_rules(nfd) == apply_external_id_rules(nfc) == nfc
    assert compute_document_id("s", apply_external_id_rules(nfd)) == compute_document_id(
        "s", apply_external_id_rules(nfc)
    )


def test_a_backslash_is_treated_as_a_slash() -> None:
    assert apply_external_id_rules("a\\b.txt") == "a/b.txt"
    assert apply_external_id_rules("a\\b\\c") == "a/b/c"


def test_case_is_kept_and_makes_different_ids() -> None:
    assert apply_external_id_rules("Docs/Guide.md") == "Docs/Guide.md"
    assert compute_document_id(
        "s", apply_external_id_rules("Docs/Guide.md")
    ) != compute_document_id("s", apply_external_id_rules("docs/guide.md"))


def test_a_valid_value_is_kept_as_it_is() -> None:
    assert apply_external_id_rules("docs/guide.md") == "docs/guide.md"
    assert apply_external_id_rules("a b/日本語.txt") == "a b/日本語.txt"


# --- #3 検証 ---


@pytest.mark.parametrize(
    ("raw", "violation"),
    [
        ("", "空"),
        ("a\x00b", "NUL"),
        ("\x00", "NUL"),
        ("/a", "先頭が `/`"),
        ("/", "先頭が `/`"),
        ("\\a", "先頭が `/`"),  # 先頭が `\` のファイル名は、置換後に先頭が `/` になる
        ("\\\\a", "先頭が `/`"),
    ],
)
def test_invalid_values_are_invalid_external_id(raw: str, violation: str) -> None:
    error = invalid(raw)

    assert error.category is ErrorCategory.INVALID_EXTERNAL_ID
    assert error.scope is ErrorScope.DOCUMENT
    assert error.retry is RetryHint.PERMANENT
    assert violation in error.message


def test_a_leading_slash_is_not_removed() -> None:
    # 除去すると `/a` と `a` が同じ文書になる。
    assert apply_external_id_rules("a") == "a"
    assert invalid("/a").category is ErrorCategory.INVALID_EXTERNAL_ID


def test_the_limit_is_4096_bytes_of_utf8() -> None:
    assert MAX_EXTERNAL_ID_BYTES == 4096
    assert apply_external_id_rules("a" * 4096) == "a" * 4096
    assert "4096" in invalid("a" * 4097).message


def test_multibyte_characters_are_counted_in_bytes_not_characters() -> None:
    at_limit = "あ" * 1365 + "a"  # 3 * 1365 + 1 = 4096 バイト(1366 文字)
    assert apply_external_id_rules(at_limit) == at_limit
    assert invalid("あ" * 1366).category is ErrorCategory.INVALID_EXTERNAL_ID  # 4098 バイト
    assert invalid(at_limit + "a").category is ErrorCategory.INVALID_EXTERNAL_ID


def test_newlines_and_tabs_are_allowed() -> None:
    assert apply_external_id_rules("a\nb\tc.txt") == "a\nb\tc.txt"


def test_the_limit_applies_to_the_final_form_after_escaping() -> None:
    # 孤立サロゲート 1 文字(UTF-8 で 3 バイト相当)が、エスケープで 3 + 5 = 8 バイトになる(FS 8.5)。
    at_limit = "a" * (4096 - 8) + "\udc80"
    assert apply_external_id_rules(at_limit).encode("utf-8").__len__() == 4096
    assert invalid("a" * (4096 - 7) + "\udc80").category is ErrorCategory.INVALID_EXTERNAL_ID


def test_the_message_never_contains_the_value() -> None:
    for raw in ["/SENTINEL-ID", "SENTINEL-ID\x00", "S" * 5000]:
        assert "SENTINEL" not in invalid(raw).message
        assert "SSSSS" not in invalid(raw).message


# --- 孤立サロゲートの ID 用エスケープ ---


def test_a_lone_surrogate_becomes_fffd_u_and_four_uppercase_hex_digits() -> None:
    assert escape_lone_surrogates_for_id("\udc80") == f"{REPLACEMENT}uDC80"
    assert escape_lone_surrogates_for_id("a\ud800b") == f"a{REPLACEMENT}uD800b"
    assert escape_lone_surrogates_for_id("\udfff") == f"{REPLACEMENT}uDFFF"
    assert escape_lone_surrogates_for_id("\udc82\udca0") == f"{REPLACEMENT}uDC82{REPLACEMENT}uDCA0"


def test_a_literal_fffd_in_the_input_is_doubled() -> None:
    assert escape_lone_surrogates_for_id(REPLACEMENT) == REPLACEMENT * 2
    assert escape_lone_surrogates_for_id(f"{REPLACEMENT}uDC80") == f"{REPLACEMENT * 2}uDC80"


def test_the_escaped_value_is_deterministic_and_has_neither_backslash_nor_nul() -> None:
    first = apply_external_id_rules("x\udc80y\ud800")

    assert apply_external_id_rules("x\udc80y\ud800") == first
    assert "\\" not in first
    assert "\0" not in first
    assert not any(0xD800 <= ord(character) <= 0xDFFF for character in first)


def test_the_escaped_value_survives_a_second_nfc_unchanged() -> None:
    final_form = apply_external_id_rules(f"a\udc80{ACUTE}\ud800e{ACUTE}\udc8e{ACUTE}")

    # Indexer は受け取った値に NFC と `\` の置換を行う(冪等)ので、送る値と算出値が一致する。
    assert unicodedata.normalize("NFC", final_form) == final_form
    assert normalize_path_form(final_form) == final_form


def test_a_combining_character_after_the_escape_does_not_merge_different_inputs() -> None:
    # 末尾の 16 進文字 `E` + U+0301 は NFC で `É` に合成される(単射性は保たれる)。
    with_surrogate = apply_external_id_rules(f"\udc8e{ACUTE}")
    with_literal = apply_external_id_rules(f"{REPLACEMENT}uDC8E{ACUTE}")
    with_text = apply_external_id_rules(f"uDC8E{ACUTE}")

    assert len({with_surrogate, with_literal, with_text}) == 3


def test_a_literal_escape_sequence_in_a_name_differs_from_an_escaped_surrogate() -> None:
    assert apply_external_id_rules("\udc80") != apply_external_id_rules(f"{REPLACEMENT}uDC80")
    assert apply_external_id_rules("\udc80") != apply_external_id_rules("uDC80")


def test_the_escape_is_injective_over_all_short_strings_of_the_relevant_alphabet() -> None:
    alphabet = ["a", "u", "D", "C", "8", "0", REPLACEMENT, "\udc80", "\ud800", ACUTE]
    outputs: dict[str, str] = {}
    for length in range(0, 5):
        for characters in itertools.product(alphabet, repeat=length):
            raw = "".join(characters)
            escaped = escape_lone_surrogates_for_id(raw)
            assert outputs.setdefault(escaped, raw) == raw, (raw, outputs[escaped])


def test_the_display_replacement_is_not_injective_but_the_id_escape_is() -> None:
    from loreley_crawler.common.display_text import replace_lone_surrogates

    assert replace_lone_surrogates("\udc80") == replace_lone_surrogates("\ud800")
    assert escape_lone_surrogates_for_id("\udc80") != escape_lone_surrogates_for_id("\ud800")


def test_a_character_outside_the_bmp_is_not_a_lone_surrogate() -> None:
    # Python の `str` では、絵文字は 1 つのコードポイント。UTF-16 のサロゲートペアではない。
    name = "メモ\U0001f600.txt"

    assert escape_lone_surrogates_for_id(name) == name
    assert apply_external_id_rules(name) == name
