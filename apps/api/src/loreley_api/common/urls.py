"""URL の検証(C 7.3。純粋関数)。

共通の規則だけを持つ: 許可した scheme、ホストがある、ユーザー情報(`user:pass@`)がない、
フラグメントがない。許可する scheme と、パス・クエリの規則(`CRAWLER_URL` は固定のパスを足すので
パスなし、など)は、呼び出し側が決める。

違反は `InvalidUrlError`。理由 `reason` は固定の値で、URL の値は含めない(秘密を含みうるため)。
"""

import unicodedata
from collections.abc import Collection
from typing import Literal
from urllib.parse import SplitResult, urlsplit

UrlViolation = Literal["malformed", "scheme", "host", "userinfo", "fragment"]


class InvalidUrlError(ValueError):
    def __init__(self, reason: UrlViolation) -> None:
        super().__init__(f"invalid url: {reason}")
        self.reason: UrlViolation = reason


def check_url(value: str, *, allowed_schemes: Collection[str]) -> SplitResult:
    """共通の規則を満たす URL を分解して返す。違反は `InvalidUrlError`(値を含まない)。"""
    # 空白・制御文字は、urllib が黙って取り除くものがあり、検証をすり抜けるので先に弾く。
    if not value or any(_is_blank_or_control(character) for character in value):
        raise InvalidUrlError("malformed")
    try:
        parts = urlsplit(value)
        _ = parts.port  # 範囲外・数字でないポートは、ここで `ValueError`
    except ValueError:
        raise InvalidUrlError("malformed") from None
    if parts.scheme not in allowed_schemes:
        raise InvalidUrlError("scheme")
    if not parts.hostname:
        raise InvalidUrlError("host")
    if "@" in parts.netloc:
        raise InvalidUrlError("userinfo")
    if "#" in value:
        raise InvalidUrlError("fragment")
    return parts


def _is_blank_or_control(character: str) -> bool:
    return character.isspace() or unicodedata.category(character) == "Cc"
