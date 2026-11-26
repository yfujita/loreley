"""プローブの Protocol(`admin` が import するのは、これと `ProbeOutcome` だけ。R6)。

どのプローブも例外を漏らさず、結果を `ProbeOutcome` で返す。
"""

from typing import Protocol

from loreley_api.common.probe_outcome import ProbeOutcome


class HttpHealthCheck(Protocol):
    """`crawler`・`indexer`・`web`・任意コンポーネントの確認(C 6.1・6.2)。ブロッキング。"""

    def check(self, url: str) -> ProbeOutcome:
        """`url` に `GET` して、2xx かどうかだけで判定する。`url` は設定(環境変数)から得た値。"""
        ...
