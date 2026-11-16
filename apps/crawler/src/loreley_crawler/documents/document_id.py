"""`document_id` の算出(interface 5.2。確定: CI-K-1)。

`document_id = SHA-256(source_id + "\\0" + external_id)` の小文字 16 進(64 桁)。

単独の関数として置き、`crawl` が `last-seen`・終了通知の ID 一覧・バッチ応答の照合に使う。
Indexer の `compute_document_id` とは共有ライブラリを作らず、別々に実装する(module CM-P-6)。
ずれは、テストベクタ(`tests/documents/`)と、バッチ応答との実行時の照合で検出する。
"""

import hashlib

from loreley_crawler.documents.identifiers import normalize_path_form

_NUL = "\0"


def compute_document_id(source_id: str, external_id: str) -> str:
    """NFC と `\\` → `/` の正規化(冪等)を適用してから計算する。先頭の `/` は除かない。

    規則適用(`apply_external_id_rules`)を通した最終形に加えて、それを通さない値も受ける
    (テストベクタが、通すと `invalid_external_id` になる値を直接入力する)。
    NUL を含む入力と、UTF-8 にできない入力(孤立サロゲート)は拒否する。例外のメッセージに
    入力値を含めない。
    """
    if _NUL in source_id or _NUL in external_id:
        raise ValueError("source_id and external_id must not contain NUL")
    material = f"{source_id}{_NUL}{normalize_path_form(external_id)}"
    try:
        encoded = material.encode("utf-8")
    except UnicodeEncodeError:
        # `UnicodeEncodeError` は入力値を保持するため、そのまま伝播させない。
        raise ValueError("source_id and external_id must be valid Unicode text") from None
    return hashlib.sha256(encoded).hexdigest()
