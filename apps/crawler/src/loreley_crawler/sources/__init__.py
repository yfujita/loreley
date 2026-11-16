"""データソース設定(`loreley-sources`)の記録・読み書き・値の検証(module 4.3)。

`ConnectorRegistry`・`ConnectorError`・`ErrorCategory` は、`validate_connector_config` の引数と
送出する例外の型。`api` は R4 により `connectors` を import できないので、ここから使う。
"""

from loreley_crawler.connectors.interface import ConnectorError, ErrorCategory
from loreley_crawler.connectors.registry import ConnectorRegistry
from loreley_crawler.sources.records import (
    MalformedSourceRecord,
    NewSource,
    SourceRecord,
    SourceSettingsInput,
    SourceStatus,
    StoredSource,
)
from loreley_crawler.sources.results import (
    AlreadyRegistered,
    DeleteSourceResult,
    MarkDeletingResult,
    MarkedDeleting,
    Registered,
    RegisterResult,
    RegistrationConflict,
    SourceDeleted,
    SourceIsDeleting,
    SourceNotDeleting,
    SourceNotFound,
    Unchanged,
    Updated,
    UpdateResult,
)
from loreley_crawler.sources.schedule_cron import InvalidScheduleCron, next_fire_time
from loreley_crawler.sources.source_store import SourceReader, SourceStore
from loreley_crawler.sources.validation import (
    ProblemReason,
    ValueProblem,
    check_connector_config_is_object,
    check_connector_type,
    check_integer,
    check_ratio_threshold,
    check_schedule_cron,
    check_source_id,
    validate_connector_config,
    validate_source_values,
)

__all__ = [
    "AlreadyRegistered",
    "ConnectorError",
    "ConnectorRegistry",
    "DeleteSourceResult",
    "ErrorCategory",
    "InvalidScheduleCron",
    "MalformedSourceRecord",
    "MarkDeletingResult",
    "MarkedDeleting",
    "NewSource",
    "ProblemReason",
    "RegisterResult",
    "Registered",
    "RegistrationConflict",
    "SourceDeleted",
    "SourceIsDeleting",
    "SourceNotDeleting",
    "SourceNotFound",
    "SourceReader",
    "SourceRecord",
    "SourceSettingsInput",
    "SourceStatus",
    "SourceStore",
    "StoredSource",
    "Unchanged",
    "UpdateResult",
    "Updated",
    "ValueProblem",
    "check_connector_config_is_object",
    "check_connector_type",
    "check_integer",
    "check_ratio_threshold",
    "check_schedule_cron",
    "check_source_id",
    "next_fire_time",
    "validate_connector_config",
    "validate_source_values",
]
