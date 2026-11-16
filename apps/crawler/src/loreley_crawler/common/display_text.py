"""保存・表示する文字列の整形(architecture CA-P-48。FS 7.3・9.4)。

`failure_detail`・`warnings`・ログに、ファイル名などの外部由来の文字列を出す前に通す。
孤立サロゲートを含む文字列は、そのまま JSON にして送ると Indexer が拒否し(K59)、
制御文字(改行など)を含む名前はログの行を偽造できてしまう(R11)。

エスケープするのは制御文字(Unicode カテゴリ Cc)だけ。行・段落区切り(Zl・Zp。U+2028・U+2029)と
双方向制御文字(Cf。U+202E など)は対象外で、そのまま残る(改行による行の偽造は Cc の改行で防げる。
表示の並びを変える文字の扱いは、必要になったときに決める)。

`external_id` に使う、孤立サロゲートの ID 用エスケープ(単射)は、ここでは扱わない
(`documents` が行う。interface 5.1)。ここの置換は表示用で、単射を求めない。
"""

import re
import unicodedata

REPLACEMENT_CHARACTER = "�"

_LONE_SURROGATE = re.compile("[\ud800-\udfff]")
_NAMED_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def replace_lone_surrogates(value: str) -> str:
    """孤立サロゲート 1 文字を U+FFFD 1 文字に置き換える(interface 5.1 の表示用置換)。

    Python の `str` では、サロゲートのコードポイントはすべて孤立している(対にならない)。
    """
    return _LONE_SURROGATE.sub(REPLACEMENT_CHARACTER, value)


def escape_control_characters(value: str) -> str:
    """制御文字(Unicode カテゴリ Cc)をエスケープする。

    改行・復帰・タブは `\\n`・`\\r`・`\\t`、それ以外は `\\xNN`。バックスラッシュ自体は変えない
    (読みやすさを優先し、エスケープの有無から元の文字列を復元することは求めない)。
    """
    return "".join(_escape_character(character) for character in value)


def format_display_text(value: str, *, max_chars: int) -> str:
    """孤立サロゲートの置換、制御文字のエスケープ、切り詰めをこの順に行う。

    切り詰めはエスケープの後に行うので、結果は `max_chars` 文字以内になる。
    エスケープ列(`\\n` など)の途中では切らない。切り詰めたことを示す印は付けない。
    """
    if max_chars < 0:
        raise ValueError("max_chars must not be negative")
    pieces: list[str] = []
    length = 0
    for character in replace_lone_surrogates(value):
        piece = _escape_character(character)
        if length + len(piece) > max_chars:
            break
        pieces.append(piece)
        length += len(piece)
    return "".join(pieces)


def _escape_character(character: str) -> str:
    named = _NAMED_ESCAPES.get(character)
    if named is not None:
        return named
    if unicodedata.category(character) == "Cc":
        return f"\\x{ord(character):02x}"
    return character
