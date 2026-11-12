"""`raw_content`(base64)のサイズ判定とデコード(api 4.3、plan 案1・案22)。

巨大な base64 を、上限の判定の前にデコードしない(メモリを使い切らないため、K39)。
サイズは base64 文字列の長さから算出する。パディングありの正しい base64 なら、
デコード後のバイト数は `長さ / 4 * 3 - パディングの文字数` で、デコードせずに分かる。
"""

import base64
import binascii
from dataclasses import dataclass


class InvalidBase64Error(ValueError):
    """base64 として不正。入力の値は含めない。"""


def estimate_decoded_size(encoded: str) -> int:
    """デコード後のバイト数。デコードはしない。

    長さが 4 の倍数でない(パディングがない・欠けている)ものは不正として拒否する。
    文字種の検査はデコード時に行う(`decode_base64`)。
    """
    if len(encoded) % 4 != 0:
        raise InvalidBase64Error("raw_content is not valid base64")
    # `rstrip` は巨大な文字列を複製するので使わない。3 個以上の `=` は、デコード時に拒否される。
    padding = 2 if encoded.endswith("==") else 1 if encoded.endswith("=") else 0
    return len(encoded) // 4 * 3 - padding


def decode_base64(encoded: str) -> bytes:
    """標準の base64(パディングあり)を厳密にデコードする。不正なら `InvalidBase64Error`。"""
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise InvalidBase64Error("raw_content is not valid base64") from None


@dataclass(frozen=True)
class SizedContent:
    """デコード後の原本(上限超過ならデコードせず `raw_content` は空)と、判定用のサイズ。"""

    raw_content: bytes
    size: int  # 申告された `size` と、推定したデコード後のサイズの大きい方


def prepare_raw_content(encoded: str, *, declared_size: int, max_raw_bytes: int) -> SizedContent:
    """上限以内ならデコードし、超えていればデコードせずに、超過をサイズで伝える。

    超過した文書は、ドメインが `size > max_raw_bytes` で文書単位の `oversize` にする
    (抽出も書き込みもしない。plan 案1)。
    """
    estimated = estimate_decoded_size(encoded)
    if estimated > max_raw_bytes:
        return SizedContent(raw_content=b"", size=max(declared_size, estimated))
    return SizedContent(raw_content=decode_base64(encoded), size=declared_size)
