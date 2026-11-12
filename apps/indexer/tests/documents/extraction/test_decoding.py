"""文字コードの判定の限界の確認(arch 4.2)。`decode_text` を直接呼ぶ。"""

import pytest

from loreley_indexer.documents.extraction import decoding
from loreley_indexer.documents.extraction.decoding import decode_text


@pytest.mark.parametrize(
    "raw",
    [
        "日本語のテキスト".encode("utf-16"),
        b"\xfe\xff" + "日本語のテキスト".encode("utf-16-be"),
        "日本語".encode("utf-32"),
        b"\x00\x00\xfe\xff" + "日本語".encode("utf-32-be"),
    ],
    ids=["utf16le", "utf16be", "utf32le", "utf32be"],
)
def test_utf16_and_utf32_bom_is_refused_without_relying_on_the_private_use_check(
    raw: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CP932 は BOM のバイトを私用領域の文字にデコードするため、私用領域の判定でも弾かれる。

    BOM の判定はそれとは独立に効くこと(判定の一方が変わっても、読めない扱いのままであること)。
    """
    monkeypatch.setattr(decoding, "_contains_private_use_char", lambda _text: False)

    assert decode_text(raw) is None


def test_private_use_check_refuses_cp932_user_defined_characters() -> None:
    assert decode_text(b"\xf0\x40") is None
    assert decode_text(b"\xf9\xfc") is None  # ユーザー定義領域の末尾


def test_cp932_text_without_private_use_characters_is_decoded() -> None:
    assert decode_text("日本語①㈱ｱｲｳ".encode("cp932")) == "日本語①㈱ｱｲｳ"


def test_the_misdetection_of_other_encodings_is_a_known_limit() -> None:
    """限界: EUC-JP の一部は、CP932 としてデコードできてしまい、文字化けのまま読める扱いになる。

    ここで固定しているのは「完全には防げない」という事実で、望ましい挙動ではない。
    """
    euc_jp = "ｱｲｳ".encode("euc-jp")  # 半角カナ(0x8E 0xB1 ...)

    assert decode_text(euc_jp) is not None
