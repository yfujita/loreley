"""Admin API の code・理由コード・状態の値(B 2.2・2.3・2.4・2.9・8.1)。"""

from enum import StrEnum


class ErrorCode(StrEnum):
    """エラー応答の `code`。共通 code のうち Admin API が直接返すものと、Admin 固有の code。"""

    INVALID_REQUEST = "invalid_request"
    UNAVAILABLE = "unavailable"
    CONFIG_INVALID = "config_invalid"
    SOURCE_CONFIG_NOT_FOUND = "source_config_not_found"
    JOB_NOT_FOUND = "job_not_found"
    LOCK_HELD = "lock_held"
    LOCK_IN_USE = "lock_in_use"
    SOURCE_DELETING = "source_deleting"
    MAINTENANCE_ENABLED = "maintenance_enabled"
    SOURCE_ALREADY_EXISTS = "source_already_exists"
    JOB_NOT_CANCELLABLE = "job_not_cancellable"
    JOB_ALREADY_FINISHED = "job_already_finished"
    CRAWLER_ERROR = "crawler_error"
    CRAWLER_UNAVAILABLE = "crawler_unavailable"
    CRAWLER_UNREACHABLE = "crawler_unreachable"
    CRAWLER_RESPONSE_LOST = "crawler_response_lost"


class Reason(StrEnum):
    """`details.errors[].reason`。A 5.2 の共通の値に、Admin 固有の `config_invalid` を加える。

    `exclusive`・`config_invalid` は、pydantic の検証エラーの `type` からは作れない(Admin API 自身の
    検証と、Crawler の違反の写像が明示的に付ける)ので、`common/http/handlers.py` の対応表には
    足さない(AAM-U-3)。
    """

    REQUIRED = "required"
    TYPE = "type"
    FORMAT = "format"
    RANGE = "range"
    EXCLUSIVE = "exclusive"
    UNKNOWN_FIELD = "unknown_field"
    UNSUPPORTED = "unsupported"
    CONFIG_INVALID = "config_invalid"


class UnavailableReason(StrEnum):
    """`unavailable` の値(取得できなかった項目の理由。B 2.2)。"""

    STORE_UNAVAILABLE = "store_unavailable"
    SEARCH_INDEX_UNAVAILABLE = "search_index_unavailable"
    TIMEOUT = "timeout"
    # 保存済みの値が読めない(EP-02 の設定項目だけ)。
    MALFORMED = "malformed"


class LockState(StrEnum):
    """`lock_state`(B 2.9)。"""

    NONE = "none"
    HELD_CRAWL = "held_crawl"
    HELD_DELETE = "held_delete"
    LEASE_EXPIRED = "lease_expired"
    ORPHAN = "orphan"
    JUST_ACQUIRED = "just_acquired"
    UNKNOWN = "unknown"


class ComponentState(StrEnum):
    """EP-13 の `components[].state`(B 8.1)。`not_configured` は任意コンポーネントだけ。"""

    NORMAL = "normal"
    ABNORMAL = "abnormal"
    UNDETERMINED = "undetermined"
    NOT_CONFIGURED = "not_configured"


class JobType(StrEnum):
    """`JobBrief.job_type`(B 2.11)。この 2 値以外の保存値は読めない値(`null`。C 5.4)。"""

    CRAWL = "crawl"
    SOURCE_DELETE = "source_delete"


class JobTrigger(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"


class JobStatus(StrEnum):
    """保存上のジョブの状態(B 2.11)。リース切れの実行中も `running`(`stalled` は別の項目)。"""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIALLY_SUCCEEDED = "partially_succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.SUCCEEDED,
        JobStatus.PARTIALLY_SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }
)


class SourceStatus(StrEnum):
    """データソース設定の `status`(B 2.11)。"""

    ACTIVE = "active"
    DELETING = "deleting"


class RerunBlockedReason(StrEnum):
    """`rerun_blocked_reason`(B 2.9。`source_missing` は案 AAPI-P-41)。"""

    NOT_CRAWL = "not_crawl"
    NOT_FAILED = "not_failed"
    STALLED = "stalled"
    SUPERSEDED = "superseded"
    SOURCE_DELETING = "source_deleting"
    SOURCE_MISSING = "source_missing"


class RegistrationPhase(StrEnum):
    """`registration.phase`(B 5.2)。"""

    FINAL = "final"
    IN_PROGRESS = "in_progress"
    INCOMPLETE = "incomplete"


class DeletionConfirmation(StrEnum):
    """`deletion.confirmation`(B 5.2)。確認に入っていないジョブは `null`。"""

    CONFIRMED = "confirmed"
    UNCONFIRMED = "unconfirmed"
    UNKNOWN = "unknown"


class DeletionCurrentState(StrEnum):
    """`deletion.current_state`(B 5.2)。"""

    AVAILABLE = "available"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"


class DocumentTab(StrEnum):
    """EP-11 の `tab`(B 6.1)。値は、件数の対象(`CountTarget`)の名前と同じ。"""

    SKIPPED = "skipped"
    EXTRACT_FAILED = "extract_failed"
    OVERSIZE = "oversize"
    SUMMARY_PENDING = "summary_pending"


class DocumentExistence(StrEnum):
    """`skipped` タブの行の `existence`(B 6.1)。検索インデックスにあるかどうか。"""

    EXISTING = "existing"
    NEW = "new"
    UNKNOWN = "unknown"


class SkipStage(StrEnum):
    """スキップ記録の `stage`(B 6.1)。この 2 値以外の保存値は読めない値(`null`)。"""

    FETCH = "fetch"
    INDEX = "index"


class OversizeDetector(StrEnum):
    """原本サイズ超過の記録の `detected_by`(B 6.1)。"""

    CRAWLER = "crawler"
    INDEXER = "indexer"
