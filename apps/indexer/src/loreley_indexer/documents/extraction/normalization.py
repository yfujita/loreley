"""本文の正規化と、サイズ上限での切り詰め(arch 4.2、15.2)。

結果が決定的であること(同じ入力から同じ `text_hash`)を最優先にする。NFKC は使わない。
"""

import hashlib
import re
import unicodedata

# 3 連続以上の空行(= 改行 4 個以上)を 2 行に圧縮する。
_BLANK_LINE_RUN = re.compile(r"\n{4,}")
# 除く文字: Unicode の一般カテゴリ Cc(制御文字: U+0000〜U+001F、U+007F〜U+009F)と
# Cs(サロゲート: U+D800〜U+DFFF)のうち、タブ(U+0009)と改行(U+000A)以外。
# 1 文字ずつ `unicodedata.category` で判定すると、数 MiB の本文で数秒かかるため、同じ範囲を
# 正規表現にしている(範囲がカテゴリと一致することはテストで固定している)。
_REMOVED_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\ud800-\udfff]")
_CONTINUATION_BYTE_MASK = 0xC0
_CONTINUATION_BYTE_TAG = 0x80


def normalize_text(text: str) -> str:
    """改行を `\\n` に統一し、NUL・制御文字(タブ・改行を除く)と行末空白を除き、NFC にする。

    制御文字を除いてから NFC にする。逆順だと、`e` + NUL + 結合文字のように制御文字を除いて
    初めて合成可能になる並びが、NFC にならずに残る。
    孤立サロゲート(PDF の抽出結果に混ざりうる)は UTF-8 にできず `text_hash` を計算できないため、
    制御文字と同じく除く。
    """
    unified_newlines = text.replace("\r\n", "\n").replace("\r", "\n")
    printable = _REMOVED_CHARS.sub("", unified_newlines)
    composed = unicodedata.normalize("NFC", printable)
    stripped = "\n".join(line.rstrip() for line in composed.split("\n"))
    return _BLANK_LINE_RUN.sub("\n\n\n", stripped)


def truncate_to_utf8_bytes(text: str, max_bytes: int) -> tuple[str, bool]:
    """UTF-8 で `max_bytes` 以下になるよう、文字の境界で切り詰める。(結果, 切り詰めたか)を返す。"""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, False
    cut = max_bytes
    # 切り位置が文字の途中(継続バイト)なら、その文字の先頭まで戻す。
    while cut > 0 and encoded[cut] & _CONTINUATION_BYTE_MASK == _CONTINUATION_BYTE_TAG:
        cut -= 1
    return encoded[:cut].decode("utf-8"), True


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
