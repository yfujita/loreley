"""包含・除外パターン(glob)の検証と照合(FS 設計書 2.2・2.3)。

構文は案(CFS-U-1。未確定)で、構文に依存する処理はこのモジュールに閉じる。変更するときは
設計書の改版が先で、ここと `config.py` の項目の意味だけを直せばよい。

構文: 特別な文字は `*`(`/` 以外の 0 文字以上)、`?`(`/` 以外の 1 文字)、`**`(単独のセグメント。
0 個以上のセグメント。末尾の `P/**` は `P` 自体と配下すべて)の 3 つだけ。エスケープはない。
パターンはルートからの相対パスの全体に一致させる。パターンも相対パスも NFC にして照合する。

照合は正規表現を使わない。正規表現はバックトラックで、`*a*a*a*a*a*a*b` のようなパターンや、
離して並べた `**` で、照合の時間が指数的に延びる。照合は中断できず(Job Runner が止まる)、
入力は管理者の設定と共有の中の名前なので、最悪の入力でも多項式の時間で終わるようにする。
- セグメント内の `*`・`?` は、貪欲な 2 ポインタ法(最後の `*` の位置だけに戻る)。
  パターンの長さと名前の長さの積に比例する時間。
- セグメントどうしは、パターンのセグメントを順に進めながら「到達しうるパスのセグメント位置」の
  集合を持つ。`**` は 0 個以上の(空でない)セグメントの分だけ位置を進める。
  セグメント照合の回数は、パターンのセグメント数とパスのセグメント数の積以下。
"""

import unicodedata
from dataclasses import dataclass
from itertools import pairwise

_DOUBLE_STAR = "**"
_WILDCARDS = "*?"


def find_pattern_violation(pattern: str, *, max_bytes: int) -> str | None:
    """パターンが規則(FS 2.2)に違反していれば、違反の種類(固定文)を返す。入力値は含めない。"""
    try:
        encoded = pattern.encode("utf-8")
    except UnicodeEncodeError:
        return "孤立サロゲートを含む"
    if not 1 <= len(encoded) <= max_bytes:
        return f"長さが 1〜{max_bytes} バイトの範囲外"
    if "\0" in pattern:
        return "NUL を含む"
    if "\\" in pattern:
        return "`\\` を含む(エスケープはない)"
    segments = pattern.split("/")
    if "" in segments:
        return "空のセグメントがある(先頭・末尾・連続する `/`)"
    if any(segment in {".", ".."} for segment in segments):
        return "`.` または `..` のセグメントがある"
    if any(_DOUBLE_STAR in segment and segment != _DOUBLE_STAR for segment in segments):
        return "`**` が単独のセグメントでない"
    if any(left == right == _DOUBLE_STAR for left, right in pairwise(segments)):
        return "`**` のセグメントが隣り合っている"
    return None


@dataclass(frozen=True)
class GlobPattern:
    """検証済みのパターン。セグメントは NFC。"""

    segments: tuple[str, ...]

    def matches(self, nfc_relative_path: str) -> bool:
        """NFC の相対パス(空でないセグメントを `/` で区切ったもの)の全体に一致するか。"""
        path_segments = nfc_relative_path.split("/")
        last_index = len(self.segments) - 1
        # パターンのセグメントをここまで照合したとき、次に照合するパスのセグメントの位置の集合。
        positions = {0}
        for index, segment in enumerate(self.segments):
            if segment == _DOUBLE_STAR:
                if index == last_index:
                    # 末尾の `**` は、残りが 0 個以上のセグメントのどれでも一致する
                    # (`P/**` は `P` 自体と配下すべて。`**` だけなら全部)。
                    return True
                positions = _skip_segments(positions, path_segments)
                continue
            positions = {
                position + 1
                for position in positions
                if position < len(path_segments)
                and _matches_segment(segment, path_segments[position])
            }
            if not positions:
                return False
        return len(path_segments) in positions


def compile_pattern(pattern: str) -> GlobPattern:
    """検証済みのパターンを NFC にして、セグメントに分ける。"""
    return GlobPattern(tuple(unicodedata.normalize("NFC", pattern).split("/")))


def matches_any(patterns: tuple[GlobPattern, ...], nfc_relative_path: str) -> bool:
    return any(pattern.matches(nfc_relative_path) for pattern in patterns)


def _skip_segments(positions: set[int], path_segments: list[str]) -> set[int]:
    """`**`(0 個以上の空でないセグメント)を通った後の位置の集合。"""
    reached: set[int] = set()
    covered_up_to = -1
    for start in sorted(positions):
        if start <= covered_up_to:
            continue  # 前の起点からの連続した範囲に含まれている
        position = start
        reached.add(position)
        while position < len(path_segments) and path_segments[position] != "":
            position += 1
            reached.add(position)
        covered_up_to = position
    return reached


def _matches_segment(pattern_segment: str, name: str) -> bool:
    """1 つのセグメント内の照合。`*` は 0 文字以上、`?` は 1 文字(どちらも `/` を含まない)。"""
    if not any(wildcard in pattern_segment for wildcard in _WILDCARDS):
        return pattern_segment == name
    pattern_index = 0
    name_index = 0
    last_star_index = -1  # 最後に見た `*` の位置。ここだけに戻る(バックトラックを爆発させない)
    star_matched_up_to = 0
    while name_index < len(name):
        pattern_char = (
            pattern_segment[pattern_index] if pattern_index < len(pattern_segment) else ""
        )
        if pattern_char == "*":
            last_star_index = pattern_index
            star_matched_up_to = name_index
            pattern_index += 1
        elif pattern_char == "?" or (pattern_char != "" and pattern_char == name[name_index]):
            pattern_index += 1
            name_index += 1
        elif last_star_index != -1:
            # 最後の `*` に 1 文字多く食わせて、そこから照合し直す。
            star_matched_up_to += 1
            name_index = star_matched_up_to
            pattern_index = last_star_index + 1
        else:
            return False
    return pattern_segment[pattern_index:].strip("*") == ""
