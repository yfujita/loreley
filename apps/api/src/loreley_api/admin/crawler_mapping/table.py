"""B 9.2 の API ごとの写像表(データ。D 4.7。C 4.4)。

キーは `(操作, Crawler のステータス, Crawler の code)`、値は Admin API の応答の決め方。表は B の
表と 1 対 1 にしてあり、API ごとの分岐は `translate.py` に書かない。**表にない組み合わせは、
`translate` が 502 `crawler_error` にする**(B 2.6。想定外の `code`・ステータス・形)。B が 502 と
明記している行(`invalid_request` など)も、B と並べて保守できるよう明示してある。

成功(2xx)と、送信の失敗(接続前・応答喪失)・契約外の応答は、API によらず同じ扱いなので表には
持たない(`translate.py`)。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from loreley_api.admin.base.codes import ErrorCode


class CrawlerOperation(StrEnum):
    """Crawler の 6 API(`CrawlerClient` の 6 操作と 1 対 1。B 9.2)。"""

    REGISTER_SOURCE = "register_source"  # EP-03(9.2.4)
    UPDATE_SOURCE = "update_source"  # EP-04(9.2.5)
    START_DELETE_JOB = "start_delete_job"  # EP-05(9.2.6)
    START_CRAWL = "start_crawl"  # EP-06(9.2.1)
    CANCEL_JOB = "cancel_job"  # EP-07(9.2.2)
    RELEASE_LOCK = "release_lock"  # EP-08(9.2.3)


class DetailKind(StrEnum):
    """Admin API の応答の `details` に、Crawler の応答から何を載せるか。"""

    NONE = "none"
    # `details.status`(文字列または `null`。`source_already_exists`・`job_already_finished`)。
    STATUS = "status"
    # `existing_job` と `lock_state`(EP-05。`options_applied`・`requested` は付けない。B 2.7)。
    LOCK_HELD = "lock_held"
    # 上に `options_applied=false` と `requested`(EP-06)。
    LOCK_HELD_WITH_OPTIONS = "lock_held_with_options"
    # `existing_job` と `lock_state`(EP-08)。
    LOCK_IN_USE = "lock_in_use"


@dataclass(frozen=True)
class Passthrough:
    """Crawler の応答を、決まった code・ステータスの Admin API のエラーに写す。"""

    code: ErrorCode
    status: int
    retryable: bool = False
    details: DetailKind = DetailKind.NONE


# `RenameFields` の値で、「送ったほうの TTL の項目」(`ttl_days` または `ttl_seconds`)を表す。
SENT_TTL_FIELD = "<the ttl field that was sent>"


@dataclass(frozen=True)
class RenameFields:
    """400 `invalid_request`: Crawler が指した項目のうち、Admin API の名前に写せるものだけを返す。

    `fields` は Crawler の項目名 → Admin API の項目名。写せる項目が 1 件もなければ 502(Admin API が
    送らない・検証済みの違反。B 2.6)。`reason` はそのまま。
    """

    fields: Mapping[str, str]


@dataclass(frozen=True)
class BranchOnField:
    """400 `invalid_request`: 項目 `field` を指していれば `when_present`、なければ `otherwise`。

    EP-07: `job_id` を理由とする 400 は、存在しない ID と同義なので 404 `job_not_found`
    (AAPI-P-39)。
    """

    field: str
    when_present: Passthrough
    otherwise: Passthrough


@dataclass(frozen=True)
class DecomposeConfigInvalid:
    """400 `config_invalid`: `message` を項目と違反の種類に分解して返す(B 2.5)。"""


type Outcome = Passthrough | RenameFields | BranchOnField | DecomposeConfigInvalid
type RowKey = tuple[CrawlerOperation, int, str]

_CRAWLER_ERROR = Passthrough(ErrorCode.CRAWLER_ERROR, 502)
_CRAWLER_UNAVAILABLE = Passthrough(ErrorCode.CRAWLER_UNAVAILABLE, 503, retryable=True)
_SOURCE_CONFIG_NOT_FOUND = Passthrough(ErrorCode.SOURCE_CONFIG_NOT_FOUND, 404)
_JOB_NOT_FOUND = Passthrough(ErrorCode.JOB_NOT_FOUND, 404)
_SOURCE_DELETING = Passthrough(ErrorCode.SOURCE_DELETING, 409)
_MAINTENANCE_ENABLED = Passthrough(ErrorCode.MAINTENANCE_ENABLED, 409)

# 設定の登録・更新の 400 `invalid_request` で、Admin API の名前に写せる項目(B 2.6)。
_SETTING_FIELD_NAMES: Mapping[str, str] = {
    "connector_type": "connector_type",
    "connector_config": "connector_config",
    "ttl": SENT_TTL_FIELD,
    "ratio_threshold": "ratio_threshold_percent",
    "min_delete_count": "min_delete_count",
    "schedule_cron": "schedule_cron",
}

# 9.2.4(登録)と 9.2.5(更新)に共通の行。登録は 409 `source_already_exists`、更新は 404・409
# `source_deleting` が加わる。
_SOURCE_SETTING_ROWS: Mapping[tuple[int, str], Outcome] = {
    (400, "invalid_request"): RenameFields(_SETTING_FIELD_NAMES),
    (400, "config_invalid"): DecomposeConfigInvalid(),
    (500, "internal_error"): _CRAWLER_ERROR,
    (503, "unavailable"): _CRAWLER_UNAVAILABLE,
}

_ROWS_BY_OPERATION: Mapping[CrawlerOperation, Mapping[tuple[int, str], Outcome]] = {
    # 9.2.4 設定の登録(EP-03)
    CrawlerOperation.REGISTER_SOURCE: {
        **_SOURCE_SETTING_ROWS,
        (409, "source_already_exists"): Passthrough(
            ErrorCode.SOURCE_ALREADY_EXISTS, 409, details=DetailKind.STATUS
        ),
    },
    # 9.2.5 設定の更新(EP-04)
    CrawlerOperation.UPDATE_SOURCE: {
        **_SOURCE_SETTING_ROWS,
        (404, "source_config_not_found"): _SOURCE_CONFIG_NOT_FOUND,
        (409, "source_deleting"): _SOURCE_DELETING,
    },
    # 9.2.6 ソース削除ジョブ起動(EP-05)。`source_deleting` は返らない(削除中も受け付ける)。
    CrawlerOperation.START_DELETE_JOB: {
        (404, "source_config_not_found"): _SOURCE_CONFIG_NOT_FOUND,
        (409, "maintenance_enabled"): _MAINTENANCE_ENABLED,
        (409, "lock_held"): Passthrough(ErrorCode.LOCK_HELD, 409, details=DetailKind.LOCK_HELD),
        (400, "invalid_request"): _CRAWLER_ERROR,
        (503, "unavailable"): _CRAWLER_UNAVAILABLE,
        (500, "internal_error"): _CRAWLER_ERROR,
    },
    # 9.2.1 クロール起動(EP-06)
    CrawlerOperation.START_CRAWL: {
        (404, "source_config_not_found"): _SOURCE_CONFIG_NOT_FOUND,
        (409, "source_deleting"): _SOURCE_DELETING,
        (409, "maintenance_enabled"): _MAINTENANCE_ENABLED,
        (409, "lock_held"): Passthrough(
            ErrorCode.LOCK_HELD, 409, details=DetailKind.LOCK_HELD_WITH_OPTIONS
        ),
        (400, "invalid_request"): _CRAWLER_ERROR,
        (503, "unavailable"): _CRAWLER_UNAVAILABLE,
        (500, "internal_error"): _CRAWLER_ERROR,
    },
    # 9.2.2 取り消し(EP-07)。`job_id` の形を理由とする 400・404 `not_found` は 404 `job_not_found`。
    CrawlerOperation.CANCEL_JOB: {
        (404, "job_not_found"): _JOB_NOT_FOUND,
        (400, "invalid_request"): BranchOnField("job_id", _JOB_NOT_FOUND, _CRAWLER_ERROR),
        (404, "not_found"): _JOB_NOT_FOUND,
        (409, "job_not_cancellable"): Passthrough(ErrorCode.JOB_NOT_CANCELLABLE, 409),
        # 成功には変換しない(画面が成功扱いにする。AAPI-P-21)。
        (409, "job_already_finished"): Passthrough(
            ErrorCode.JOB_ALREADY_FINISHED, 409, details=DetailKind.STATUS
        ),
        (503, "unavailable"): _CRAWLER_UNAVAILABLE,
        (500, "internal_error"): _CRAWLER_ERROR,
    },
    # 9.2.3 ロック解放(EP-08)。404 は返らない(設定がなくても解放できる)。
    CrawlerOperation.RELEASE_LOCK: {
        (409, "lock_in_use"): Passthrough(
            ErrorCode.LOCK_IN_USE, 409, details=DetailKind.LOCK_IN_USE
        ),
        (400, "invalid_request"): _CRAWLER_ERROR,
        (503, "unavailable"): _CRAWLER_UNAVAILABLE,
        (500, "internal_error"): _CRAWLER_ERROR,
    },
}

TABLE: Mapping[RowKey, Outcome] = {
    (operation, status, code): outcome
    for operation, rows in _ROWS_BY_OPERATION.items()
    for (status, code), outcome in rows.items()
}
