"""Connector の型・エラー・`ConnectorType`。他に依存しない(R5)。"""

from loreley_crawler.connectors.interface.connector import (
    Connector,
    ConnectorType,
    EnumerationStream,
)
from loreley_crawler.connectors.interface.errors import (
    ConnectorError,
    ErrorCategory,
    ErrorScope,
    RetryHint,
    converting_unexpected_errors,
    errno_name,
    to_connector_error,
)
from loreley_crawler.connectors.interface.models import (
    Completed,
    DocumentMetadata,
    DocumentRef,
    FetchedDocument,
)

__all__ = [
    "Completed",
    "Connector",
    "ConnectorError",
    "ConnectorType",
    "DocumentMetadata",
    "DocumentRef",
    "EnumerationStream",
    "ErrorCategory",
    "ErrorScope",
    "FetchedDocument",
    "RetryHint",
    "converting_unexpected_errors",
    "errno_name",
    "to_connector_error",
]
