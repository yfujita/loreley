"""LLM クライアントのインターフェース(module 4.5)。

R9: 外部 LLM は、明示的に設定したときだけ呼ぶ。既定の実装は無効で、呼ぶと例外になる。
プロンプトには文書の本文が含まれるため、失敗の記録にもログにもプロンプトや応答を含めない。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from loreley_indexer.common.errors import IndexerError


class LlmDisabledError(IndexerError):
    """無効な構成で LLM が呼ばれた。呼び出し側が有効化の設定を確認せずに呼んだ実装の誤り。"""


class LlmFailureKind(StrEnum):
    CONNECTION = "connection"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True)
class LlmCompletion:
    text: str
    model: str  # `summary_model` に書く、モデル名・バージョン


@dataclass(frozen=True)
class LlmFailure:
    kind: LlmFailureKind


LlmResult = LlmCompletion | LlmFailure


class LlmClient(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> LlmResult:
        """接続の失敗・タイムアウトは例外ではなく `LlmFailure` で返す。"""


class DisabledLlmClient(LlmClient):
    def generate(self, prompt: str) -> LlmResult:
        raise LlmDisabledError("LLM is not configured")
