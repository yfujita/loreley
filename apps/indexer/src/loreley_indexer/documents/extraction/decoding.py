"""文字コードの判定とデコード(arch 4.2: UTF-8 のほか Shift_JIS/CP932)。

自動判定ライブラリは使わず、厳密なデコードを UTF-8 → CP932 の順に試す。
どちらも読めなければ None(誤った文字コードで索引化しない)。

限界: 文字コードを判定しているのではなく、デコードできたものを採用している。
CP932 は割り当てが広いため、別の文字コード(EUC-JP など)のバイト列が、CP932 として
デコードできてしまい文字化けのまま索引化されることがある(特に半角カナへの誤判定)。
これは完全には防げない。次の 2 つだけは、誤判定として読めない扱いにする。
- UTF-16/32 の BOM で始まる(CP932 は BOM のバイトを私用領域の文字にデコードし、
  BOM 以降は NUL 混じりの文字化けになる)。
- CP932 のデコード結果に私用領域(U+E000〜U+F8FF)が含まれる(CP932 のユーザー定義文字の領域。
  文字化けの典型で、読める日本語の文書にはまず現れない)。
"""

import codecs

_UTF16_UTF32_BOMS = (
    codecs.BOM_UTF32_LE,
    codecs.BOM_UTF32_BE,
    codecs.BOM_UTF16_LE,
    codecs.BOM_UTF16_BE,
)
_PRIVATE_USE_AREA_START = ""
_PRIVATE_USE_AREA_END = ""


def decode_text(raw_content: bytes) -> str | None:
    if raw_content.startswith(_UTF16_UTF32_BOMS):
        return None
    try:
        # `utf-8-sig` は BOM の有無のどちらも読め、BOM は本文に含めない。
        return raw_content.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        decoded = raw_content.decode("cp932")
    except UnicodeDecodeError:
        return None
    if _contains_private_use_char(decoded):
        return None
    return decoded


def _contains_private_use_char(text: str) -> bool:
    return any(_PRIVATE_USE_AREA_START <= char <= _PRIVATE_USE_AREA_END for char in text)
