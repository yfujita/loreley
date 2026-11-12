"""要約用 LLM のクライアント(インターフェースと、無効な既定実装)。"""

from loreley_indexer.infrastructure.llm.client import (
    DisabledLlmClient,
    LlmClient,
    LlmCompletion,
    LlmDisabledError,
    LlmFailure,
    LlmFailureKind,
    LlmResult,
)

__all__ = [
    "DisabledLlmClient",
    "LlmClient",
    "LlmCompletion",
    "LlmDisabledError",
    "LlmFailure",
    "LlmFailureKind",
    "LlmResult",
]
