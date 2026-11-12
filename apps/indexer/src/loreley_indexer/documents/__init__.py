"""文書の登録と要約(module 4.3)。

公開する入口: バッチ登録(`DocumentRegistrar`)、`last_seen_at` 部分更新(`LastSeenUpdater`)、
要約の生成(`Summarization`。起動時の再走査を含む)。
"""

from loreley_indexer.documents.config import RegistrationConfig
from loreley_indexer.documents.last_seen import LastSeenUpdater
from loreley_indexer.documents.registration import DocumentRegistrar
from loreley_indexer.documents.requests import CrawlContext, DocumentInput, LockInfo
from loreley_indexer.documents.results import (
    Change,
    DocumentFailed,
    DocumentOutcome,
    DocumentRegistered,
    FailureType,
    LastSeenEntry,
    LastSeenResult,
)
from loreley_indexer.documents.summarization import (
    Summarization,
    SummarizationConfig,
    create_summarization,
)

__all__ = [
    "Change",
    "CrawlContext",
    "DocumentFailed",
    "DocumentInput",
    "DocumentOutcome",
    "DocumentRegistered",
    "DocumentRegistrar",
    "FailureType",
    "LastSeenEntry",
    "LastSeenResult",
    "LastSeenUpdater",
    "LockInfo",
    "RegistrationConfig",
    "Summarization",
    "SummarizationConfig",
    "create_summarization",
]
