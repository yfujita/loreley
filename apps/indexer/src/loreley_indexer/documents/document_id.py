"""`document_id` の算出(arch 3.2、api 3.3)。

`document_id = SHA-256(source_id + "\\0" + external_id)` の小文字 16 進。
`external_id` はハッシュの前に NFC へ正規化し、パス区切りを `/` に統一する。
大文字小文字は区別したまま扱う。先頭の `/` は除かない(下記)。
"""

import hashlib
import unicodedata

NUL = "\0"


def normalize_external_id(external_id: str) -> str:
    """NFC 正規化し、パス区切りを `\\` から `/` に統一する。

    設計書の「ルートからの相対パス、先頭に `/` を付けない」は入力(Crawler が渡す値)の前提で、
    Indexer が除く規則ではない。`last-seen` は Crawler が算出した ID を受けるため、
    Indexer だけが先頭の `/` を除くと、同じ文書の ID が Crawler と食い違う。
    """
    return unicodedata.normalize("NFC", external_id).replace("\\", "/")


def compute_document_id(source_id: str, external_id: str) -> str:
    """同じ (source_id, external_id) は、再取得しても同じ ID になる。

    NUL で区切るので、NUL を含まない限り、連結で別の組が同じ値にならない。
    その前提を守るため、NUL を含む入力は拒否する。UTF-8 にできない入力(孤立サロゲート)も拒否する。
    どちらも例外メッセージに入力値を含めない。
    """
    if NUL in source_id or NUL in external_id:
        raise ValueError("source_id and external_id must not contain NUL")
    material = f"{source_id}{NUL}{normalize_external_id(external_id)}"
    try:
        encoded = material.encode("utf-8")
    except UnicodeEncodeError:
        # `UnicodeEncodeError` は入力値を保持するため、そのまま伝播させない。
        raise ValueError("source_id and external_id must be valid Unicode text") from None
    return hashlib.sha256(encoded).hexdigest()
