"""形式別の抽出、正規化・切り詰め・`text_hash`(module 4.3、arch 4.2)。

限界(未検証): PDF は ASCII の標準フォントの最小構成だけで確かめている。日本語を含む PDF
(CID フォント・ToUnicode など)の抽出は、実際の PDF での検証が必要で、ここでは確認していない。
"""

import hashlib
import logging

import pytest
from pypdf import PageObject

from loreley_indexer.documents.extraction import (
    ExtractedText,
    ExtractionConfig,
    ExtractionFailed,
    ExtractionFailureReason,
    TextExtractor,
)
from loreley_indexer.documents.extraction.html import UnparsableHtmlError
from tests.documents.extraction.samples import encrypted_pdf, minimal_pdf, pdf_with_pages

MAX_CONTENT_BYTES = 1024


@pytest.fixture
def extractor() -> TextExtractor:
    return TextExtractor(ExtractionConfig(max_content_bytes=MAX_CONTENT_BYTES))


def extracted(result: object) -> ExtractedText:
    assert isinstance(result, ExtractedText)
    return result


def failure_reason(result: object) -> ExtractionFailureReason:
    assert isinstance(result, ExtractionFailed)
    return result.reason


# --- 形式別の抽出(arch 16.2 S-7) ---


def test_plain_text_utf8(extractor: TextExtractor) -> None:
    result = extracted(extractor.extract("日本語のテキスト\nline2".encode(), "text/plain"))
    assert result.text == "日本語のテキスト\nline2"
    assert result.truncated is False


def test_utf8_bom_is_not_part_of_the_text(extractor: TextExtractor) -> None:
    raw = b"\xef\xbb\xbf" + "BOM付き".encode()
    assert extracted(extractor.extract(raw, "text/plain")).text == "BOM付き"


def test_cp932_text_is_decoded(extractor: TextExtractor) -> None:
    raw = "Shift_JIS の日本語です。①㈱".encode("cp932")
    assert extracted(extractor.extract(raw, "text/plain")).text == "Shift_JIS の日本語です。①㈱"


def test_utf8_is_tried_before_cp932(extractor: TextExtractor) -> None:
    # CP932 でも読めるバイト列(ASCII)は UTF-8 として読む。結果は同じ文字列。
    assert extracted(extractor.extract(b"plain ascii", "text/plain")).text == "plain ascii"


def test_undecodable_bytes_fail_instead_of_guessing(extractor: TextExtractor) -> None:
    # UTF-8 としても、CP932 としても(先頭バイトだけで終わる)不正なバイト列。
    result = extractor.extract(b"abc\x81", "text/plain")
    assert failure_reason(result) is ExtractionFailureReason.UNDECODABLE_TEXT


def test_empty_text_is_extracted_as_empty_content(extractor: TextExtractor) -> None:
    result = extracted(extractor.extract(b"", "text/plain"))
    assert result.text == ""
    assert result.text_hash == hashlib.sha256(b"").hexdigest()


@pytest.mark.parametrize("mime_type", ["text/markdown", "text/x-markdown"])
def test_markdown_is_kept_as_the_original_text(extractor: TextExtractor, mime_type: str) -> None:
    markdown = "# Title\n\n* item\n\n`code` and <b>tag</b>\n"
    assert extracted(extractor.extract(markdown.encode(), mime_type)).text == markdown


def test_html_drops_script_style_and_comments_and_keeps_block_boundaries(
    extractor: TextExtractor,
) -> None:
    html = (
        "<html><head><title>題名</title><style>p { color: red }</style></head>"
        "<body><!-- コメント --><p>一つ目 &amp; 二つ目</p>"
        "<script>var secret = 1;</script><p>三つ目</p></body></html>"
    )
    text = extracted(extractor.extract(html.encode(), "text/html")).text
    assert "color" not in text
    assert "secret" not in text
    assert "コメント" not in text
    assert text.split("\n") == ["題名", "一つ目 & 二つ目", "三つ目"]


def test_html_in_cp932_is_decoded(extractor: TextExtractor) -> None:
    raw = "<html><body><p>日本語</p></body></html>".encode("cp932")
    assert extracted(extractor.extract(raw, "text/html")).text == "日本語"


def test_html_tolerates_broken_markup(extractor: TextExtractor) -> None:
    result = extracted(extractor.extract(b"<p>unclosed <b>bold", "text/html"))
    assert "unclosed" in result.text
    assert "bold" in result.text


def test_pdf_text_is_extracted(extractor: TextExtractor) -> None:
    result = extracted(extractor.extract(minimal_pdf("Hello PDF"), "application/pdf"))
    assert result.text == "Hello PDF"


@pytest.mark.parametrize(
    "raw",
    [b"", b"not a pdf", minimal_pdf("Hello PDF")[:100], b"%PDF-1.4\n" + b"\x00" * 50],
    ids=["empty", "garbage", "truncated", "header-only"],
)
def test_corrupt_pdf_fails(extractor: TextExtractor, raw: bytes) -> None:
    result = extractor.extract(raw, "application/pdf")
    assert failure_reason(result) is ExtractionFailureReason.CORRUPT_DOCUMENT


def test_encrypted_pdf_fails_even_though_it_is_otherwise_valid(extractor: TextExtractor) -> None:
    result = extractor.extract(encrypted_pdf("Secret text"), "application/pdf")
    assert failure_reason(result) is ExtractionFailureReason.ENCRYPTED_PDF


def test_pdf_pages_are_joined_with_newlines(extractor: TextExtractor) -> None:
    result = extracted(extractor.extract(pdf_with_pages(["page1", "page2"]), "application/pdf"))
    assert result.text == "page1\npage2"


def test_pdf_with_only_an_owner_password_is_also_rejected_as_encrypted(
    extractor: TextExtractor,
) -> None:
    """開くのにパスワードが要らない(所有者パスワードだけの)暗号化 PDF も、暗号化として拒否する。"""
    raw = encrypted_pdf("Readable text", user_password="")
    result = extractor.extract(raw, "application/pdf")
    assert failure_reason(result) is ExtractionFailureReason.ENCRYPTED_PDF


def test_corrupt_html_is_a_failed_extraction(
    extractor: TextExtractor, monkeypatch: pytest.MonkeyPatch
) -> None:
    """構文解析器が拒否した HTML は `corrupt_document`。

    実際の入力では lxml は壊れた HTML も受け入れる(`test_html_tolerates_broken_markup`)ため、
    拒否は(`ParserRejectedMarkup` を起こす)差し替えで再現する。
    """

    def reject(_html: str) -> str:
        raise UnparsableHtmlError

    monkeypatch.setattr("loreley_indexer.documents.extraction.extractor.html_to_text", reject)

    result = extractor.extract(b"<p>text</p>", "text/html")

    assert failure_reason(result) is ExtractionFailureReason.CORRUPT_DOCUMENT


def test_pages_after_the_size_limit_are_not_read(
    extractor: TextExtractor, monkeypatch: pytest.MonkeyPatch
) -> None:
    """本文が上限を超えたら、残りのページは読まない。切り詰めたこと(`truncated`)は反映する。"""
    pages_read: list[int] = []
    original = PageObject.extract_text

    def counting_extract_text(self: PageObject, *args: object, **kwargs: object) -> str:
        pages_read.append(1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(PageObject, "extract_text", counting_extract_text)
    raw = pdf_with_pages(["x" * 200] * 50)  # 全部で約 10000 バイト > 1024

    result = extracted(extractor.extract(raw, "application/pdf"))

    assert result.truncated is True
    assert result.text == ("x" * 200 + "\n") * 5 + "x" * 19  # 先頭から 1024 バイト
    assert len(pages_read) <= 7


def test_pdf_whose_text_shrinks_under_the_limit_after_normalization_is_read_to_the_end(
    extractor: TextExtractor, monkeypatch: pytest.MonkeyPatch
) -> None:
    """打ち切りの判定は、行末空白などを除いた(正規化後の)長さで行う。生の長さでは打ち切らない。"""
    raw = pdf_with_pages(["x" + " " * 600] * 4)  # 生では 2400 バイト超、正規化後は 7 バイト

    result = extracted(extractor.extract(raw, "application/pdf"))

    assert result.text == "x\nx\nx\nx"
    assert result.truncated is False


def test_pdf_over_the_limit_gives_the_same_text_as_reading_every_page(
    extractor: TextExtractor,
) -> None:
    """途中で打ち切っても、結果は全ページを読んで切り詰めた場合と同じ(同じ `text_hash`)。"""
    pages = [f"page{number:03d}-" + "y" * 100 for number in range(40)]
    full_text = "\n".join(pages)

    result = extracted(extractor.extract(pdf_with_pages(pages), "application/pdf"))

    assert result.truncated is True
    assert result.text == full_text.encode()[:MAX_CONTENT_BYTES].decode()


def test_pdf_whose_normalized_text_is_over_the_limit_by_one_page_is_truncated(
    extractor: TextExtractor,
) -> None:
    """後続ページが 1 文字でも超えるなら `truncated`。上限ちょうどまでの本文は残る(`>` の境界)。"""
    raw = pdf_with_pages(["x" * MAX_CONTENT_BYTES, "y"])

    result = extracted(extractor.extract(raw, "application/pdf"))

    assert result.truncated is True
    assert result.text == "x" * MAX_CONTENT_BYTES


def test_pdf_whose_normalized_text_is_exactly_the_limit_is_not_truncated(
    extractor: TextExtractor,
) -> None:
    result = extracted(
        extractor.extract(pdf_with_pages(["x" * MAX_CONTENT_BYTES]), "application/pdf")
    )

    assert result.truncated is False
    assert result.text == "x" * MAX_CONTENT_BYTES


def test_pdf_parser_warnings_never_reach_the_logs(
    extractor: TextExtractor, caplog: pytest.LogCaptureFixture
) -> None:
    """R9: pypdf は壊れた PDF の警告に原本の先頭(`invalid pdf header: b'SECRE'`)を含める。

    ログに出さない(`pypdf` ロガーの抑止を固定する)。
    """
    with caplog.at_level(logging.DEBUG):
        result = extractor.extract(b"SECRET-SENTINEL not a pdf", "application/pdf")

    assert failure_reason(result) is ExtractionFailureReason.CORRUPT_DOCUMENT
    assert [record for record in caplog.records if record.name.startswith("pypdf")] == []
    assert "SECRE" not in caplog.text


# --- 文字コード(UTF-8 と CP932 以外は読めない扱い) ---


@pytest.mark.parametrize(
    "raw",
    [
        "日本語のテキスト".encode("utf-16"),  # BOM 付き(リトルエンディアン)
        b"\xfe\xff" + "日本語のテキスト".encode("utf-16-be"),
        "日本語のテキスト".encode("utf-32"),
        b"\x00\x00\xfe\xff" + "日本語のテキスト".encode("utf-32-be"),
        "plain ascii".encode("utf-16"),
    ],
    ids=["utf16le", "utf16be", "utf32le", "utf32be", "utf16_ascii"],
)
@pytest.mark.parametrize("mime_type", ["text/plain", "text/html"])
def test_utf16_and_utf32_with_a_bom_are_undecodable_instead_of_garbled(
    extractor: TextExtractor, raw: bytes, mime_type: str
) -> None:
    result = extractor.extract(raw, mime_type)
    assert failure_reason(result) is ExtractionFailureReason.UNDECODABLE_TEXT


def test_cp932_text_with_private_use_characters_is_undecodable(extractor: TextExtractor) -> None:
    """CP932 のユーザー定義文字の領域(U+E000〜)にデコードされるのは、文字化けの典型。"""
    raw = "前".encode("cp932") + b"\xf0\x40" + "後".encode("cp932")
    result = extractor.extract(raw, "text/plain")
    assert failure_reason(result) is ExtractionFailureReason.UNDECODABLE_TEXT


def test_utf8_text_with_a_private_use_character_is_kept(extractor: TextExtractor) -> None:
    """私用領域の判定は CP932 のデコード結果だけ。正しい UTF-8 の文書は、そのまま読む。"""
    assert extracted(extractor.extract("a\ue000b".encode(), "text/plain")).text == "a\ue000b"


# --- mime_type の扱い ---


@pytest.mark.parametrize(
    "mime_type",
    ["text/plain; charset=utf-8", "TEXT/PLAIN", " text/plain ;charset=cp932"],
)
def test_mime_type_parameters_and_case_are_ignored(
    extractor: TextExtractor, mime_type: str
) -> None:
    assert extracted(extractor.extract(b"abc", mime_type)).text == "abc"


@pytest.mark.parametrize(
    "mime_type",
    ["application/msword", "image/png", "application/octet-stream", "", "text", "text/csv"],
)
def test_unknown_mime_type_fails(extractor: TextExtractor, mime_type: str) -> None:
    result = extractor.extract(b"abc", mime_type)
    assert failure_reason(result) is ExtractionFailureReason.UNSUPPORTED_MIME_TYPE


# --- 正規化・切り詰め・text_hash(arch 16.2 E-6、16.3 C-12 の抽出側) ---


def test_control_characters_and_nul_never_reach_the_text(extractor: TextExtractor) -> None:
    result = extracted(extractor.extract(b"a\x00b\x01c\r\nd\t e  \n", "text/plain"))
    assert result.text == "abc\nd\t e\n"


def test_text_over_the_limit_is_truncated_on_a_character_boundary(
    extractor: TextExtractor,
) -> None:
    raw = ("あ" * 400).encode()  # 1200 バイト > 1024
    result = extracted(extractor.extract(raw, "text/plain"))
    assert result.truncated is True
    assert result.text == "あ" * 341  # 1023 バイト。1024 バイト目は文字の途中
    assert len(result.text.encode("utf-8")) <= MAX_CONTENT_BYTES


def test_text_exactly_at_the_limit_is_not_truncated(extractor: TextExtractor) -> None:
    result = extracted(extractor.extract(b"x" * MAX_CONTENT_BYTES, "text/plain"))
    assert result.truncated is False
    assert len(result.text) == MAX_CONTENT_BYTES


def test_text_hash_covers_the_truncated_text_not_the_original(extractor: TextExtractor) -> None:
    raw = b"x" * (MAX_CONTENT_BYTES + 10)
    result = extracted(extractor.extract(raw, "text/plain"))
    assert result.truncated is True
    assert result.text_hash == hashlib.sha256(result.text.encode("utf-8")).hexdigest()
    assert result.text_hash != hashlib.sha256(raw).hexdigest()


def test_limit_applies_after_normalization(extractor: TextExtractor) -> None:
    # 正規化(行末空白の除去)で上限以内に収まるなら、切り詰めない。
    raw = ("x" + " " * 99 + "\n").encode() * 20  # 2000 バイト。正規化後は 40 バイト
    result = extracted(extractor.extract(raw, "text/plain"))
    assert result.truncated is False


def test_text_hash_is_deterministic(extractor: TextExtractor) -> None:
    raw = "同じ入力".encode()
    first = extracted(extractor.extract(raw, "text/plain"))
    second = extracted(extractor.extract(raw, "text/plain"))
    assert first == second


def test_text_hash_is_the_sha256_of_the_normalized_text(extractor: TextExtractor) -> None:
    result = extracted(extractor.extract(b"hello", "text/plain"))
    assert result.text_hash == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_inputs_that_normalize_to_the_same_text_have_the_same_hash(
    extractor: TextExtractor,
) -> None:
    lf = extracted(extractor.extract(b"a\nb\n", "text/plain"))
    crlf = extracted(extractor.extract(b"a  \r\nb\r\n", "text/plain"))
    assert lf.text_hash == crlf.text_hash


def test_different_text_gives_a_different_hash(extractor: TextExtractor) -> None:
    first = extracted(extractor.extract(b"one", "text/plain"))
    second = extracted(extractor.extract(b"two", "text/plain"))
    assert first.text_hash != second.text_hash


def test_failed_result_carries_no_text_or_hash(extractor: TextExtractor) -> None:
    # E-45 の抽出側: `extract_failed` の文書は `content`・`text_hash` を持たない。
    result = extractor.extract(b"abc", "application/msword")
    assert isinstance(result, ExtractionFailed)
    assert not hasattr(result, "text")
    assert not hasattr(result, "text_hash")


def test_failure_does_not_include_the_document_content() -> None:
    extractor = TextExtractor(ExtractionConfig(max_content_bytes=1024))
    sentinel = "SECRET-SENTINEL"
    result = extractor.extract(sentinel.encode() + b"\x81", "text/plain")
    assert sentinel not in repr(result)


def test_config_rejects_a_limit_below_one() -> None:
    with pytest.raises(ValueError):
        ExtractionConfig(max_content_bytes=0)
