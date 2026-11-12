"""抽出の結果(module 4.3: 「本文・`text_hash`・`truncated`」または「抽出失敗」)。"""

from dataclasses import dataclass
from enum import StrEnum


class ExtractionFailureReason(StrEnum):
    """失敗の種別。文書の内容を含まない固定の名前だけを持つ(R9)。"""

    UNSUPPORTED_MIME_TYPE = "unsupported_mime_type"
    UNDECODABLE_TEXT = "undecodable_text"  # UTF-8 でも CP932 でも読めない、または読めたと言えない
    ENCRYPTED_PDF = "encrypted_pdf"
    CORRUPT_DOCUMENT = "corrupt_document"  # PDF・HTML を構文解析できない


@dataclass(frozen=True)
class ExtractedText:
    """検索インデックスの `content`・`truncated`・`text_hash` に書く値。"""

    text: str
    truncated: bool
    text_hash: str  # `text`(切り詰め後)の UTF-8 の SHA-256、16 進小文字(arch 1.3)


@dataclass(frozen=True)
class ExtractionFailed:
    """`index_status=extract_failed` で登録する(arch 4.2)。`content`・`text_hash` は持たない。"""

    reason: ExtractionFailureReason


ExtractionResult = ExtractedText | ExtractionFailed
