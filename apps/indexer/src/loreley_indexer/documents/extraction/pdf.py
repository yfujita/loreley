"""PDF からの本文抽出(pypdf)。"""

import io
import logging

from pypdf import PdfReader

from loreley_indexer.documents.extraction.normalization import normalize_text

# pypdf は壊れた PDF の警告に、原本の一部(ヘッダのバイト列など)を含める。
# 本文をログに出さない(R9)ため、警告は出さない。失敗は例外で呼び出し側に伝わる。
logging.getLogger("pypdf").setLevel(logging.CRITICAL)


class EncryptedPdfError(Exception):
    pass


class UnreadablePdfError(Exception):
    pass


def pdf_to_text(raw_content: bytes, max_content_bytes: int) -> str:
    """全ページのテキストを改行でつないで返す。暗号化された PDF は、読めても拒否する。

    正規化後の本文が `max_content_bytes` を超えたら、残りのページは読まない(どのみち切り詰める
    ため。ページ数の多い PDF でも抽出に時間をかけない)。打ち切ったときの戻り値は、呼び出し側が
    正規化すると上限を超えるので、切り詰めたことが `truncated` に反映される。
    """
    # pypdf は壊れた PDF に対して、`PdfReadError` 以外の例外(KeyError、ValueError、
    # RecursionError など)も送出する。例外の種類に依存せず、読めない PDF は一括で扱う。
    try:
        reader = PdfReader(io.BytesIO(raw_content))
        is_encrypted = reader.is_encrypted
        page_texts = [] if is_encrypted else _extract_pages(reader, max_content_bytes)
    except Exception:
        raise UnreadablePdfError from None
    if is_encrypted:
        raise EncryptedPdfError
    return "\n".join(page_texts)


def _extract_pages(reader: PdfReader, max_content_bytes: int) -> list[str]:
    pages: list[str] = []
    accumulated_bytes = 0
    for page in reader.pages:
        page_text = page.extract_text()
        pages.append(page_text)
        accumulated_bytes += len(page_text.encode("utf-8", errors="replace")) + 1
        if accumulated_bytes <= max_content_bytes:
            continue
        # 空白や制御文字は正規化で減るので、生の長さではなく正規化後の長さで判定する。
        # 正規化済みの本文に置き換えて、次の判定で同じ本文を何度も正規化し直さない。
        normalized = normalize_text("\n".join(pages))
        accumulated_bytes = len(normalized.encode("utf-8"))
        if accumulated_bytes > max_content_bytes:
            return [normalized]
        pages = [normalized]
    return pages
