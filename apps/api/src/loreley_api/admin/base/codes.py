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
