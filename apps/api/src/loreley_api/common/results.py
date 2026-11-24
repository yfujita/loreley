"""読み取りの結果型(C 8.6)。

Reader は例外を呼び出し側へ漏らさず、`Ok(値)` か `Failed` を返す。`services` は `Failed` の項目を
`null` にして `unavailable` に理由を載せる(部分失敗)。
"""

from dataclasses import dataclass
from typing import Literal

# `timeout`: 接続・読み取りのタイムアウト。`unavailable`: それ以外の失敗
# (接続拒否・5xx・部分的な失敗など)。
FailureKind = Literal["timeout", "unavailable"]
# 読み取りの対象。`store` は `loreley-*`(設定・ジョブ・削除記録)、`search_index` は
# 検索インデックス。
FailureTarget = Literal["store", "search_index"]


@dataclass(frozen=True)
class Ok[T]:
    value: T


@dataclass(frozen=True)
class Failed:
    kind: FailureKind
    target: FailureTarget
    # ログ用の例外クラス名。メッセージは、入力値や ID を含みうるので持たない。
    error_class_name: str


type Result[T] = Ok[T] | Failed
