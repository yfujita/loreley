"""B 9.2 の API ごとの写像表の行(Crawler の応答 → Admin API の応答)。

`test_translate.py`(`translate` を直接呼ぶ)と、EP 経由のテスト(`routers/`)が同じ表を使う。
`lock_state` は `held_crawl`、`requested` は `REQUESTED` で呼んだときの期待値。
"""

from typing import Any

from loreley_api.admin.crawler_mapping import CrawlerOperation, RequestedOptions
from loreley_api.infrastructure.crawler_client import ConfigInvalidMessage, CrawlerRejected

REGISTER = CrawlerOperation.REGISTER_SOURCE
UPDATE = CrawlerOperation.UPDATE_SOURCE
START_DELETE = CrawlerOperation.START_DELETE_JOB
START_CRAWL = CrawlerOperation.START_CRAWL
CANCEL = CrawlerOperation.CANCEL_JOB
RELEASE = CrawlerOperation.RELEASE_LOCK

EXISTING_JOB = {
    "job_id": "job-20261122T010203Z-3fa9c2d1",
    "job_type": "crawl",
    "status": "running",
    "trigger": "schedule",
    "lease_expires_at": "2026-11-22T01:07:03.456Z",
}
REQUESTED = RequestedOptions(force_delete=True, rewrite_mode=False)


def rejected(
    status: int,
    code: str,
    details: dict[str, Any] | None = None,
    config_invalid: ConfigInvalidMessage | None = None,
) -> CrawlerRejected:
    return CrawlerRejected(status, code, details, config_invalid)


def field_errors(*entries: tuple[str, str]) -> dict[str, Any]:
    return {"errors": [{"field": field, "reason": reason} for field, reason in entries]}


CRAWLER_ERROR = (502, "crawler_error", False, None)
CRAWLER_UNAVAILABLE = (503, "crawler_unavailable", True, None)
LOCK_HELD_DETAILS = {"existing_job": EXISTING_JOB, "lock_state": "held_crawl"}

# B 9.2 の API ごとの表: (操作, Crawler の応答, Admin API の (status, code, retryable, details))。
# 並びは B の表の順。`lock_state` は `held_crawl`、`requested` は `REQUESTED` で呼ぶ。
ROWS: list[tuple[CrawlerOperation, CrawlerRejected, tuple[Any, ...]]] = [
    # 9.2.1 クロール起動
    (
        START_CRAWL,
        rejected(404, "source_config_not_found"),
        (404, "source_config_not_found", False, None),
    ),
    (START_CRAWL, rejected(409, "source_deleting"), (409, "source_deleting", False, None)),
    (START_CRAWL, rejected(409, "maintenance_enabled"), (409, "maintenance_enabled", False, None)),
    (
        START_CRAWL,
        rejected(409, "lock_held", {"existing_job": EXISTING_JOB}),
        (
            409,
            "lock_held",
            False,
            {
                "options_applied": False,
                "requested": {"force_delete": True, "rewrite_mode": False},
                **LOCK_HELD_DETAILS,
            },
        ),
    ),
    (
        START_CRAWL,
        rejected(400, "invalid_request", field_errors(("force_delete", "type"))),
        CRAWLER_ERROR,
    ),
    (START_CRAWL, rejected(503, "unavailable"), CRAWLER_UNAVAILABLE),
    (START_CRAWL, rejected(500, "internal_error"), CRAWLER_ERROR),
    # 9.2.2 取り消し
    (CANCEL, rejected(404, "job_not_found"), (404, "job_not_found", False, None)),
    (
        CANCEL,
        rejected(400, "invalid_request", field_errors(("job_id", "format"))),
        (404, "job_not_found", False, None),
    ),
    (CANCEL, rejected(404, "not_found"), (404, "job_not_found", False, None)),
    (CANCEL, rejected(409, "job_not_cancellable"), (409, "job_not_cancellable", False, None)),
    (
        CANCEL,
        rejected(409, "job_already_finished", {"status": "succeeded"}),
        (409, "job_already_finished", False, {"status": "succeeded"}),
    ),
    (CANCEL, rejected(400, "invalid_request", field_errors(("body", "type"))), CRAWLER_ERROR),
    (CANCEL, rejected(503, "unavailable"), CRAWLER_UNAVAILABLE),
    (CANCEL, rejected(500, "internal_error"), CRAWLER_ERROR),
    # 9.2.3 ロック解放
    (
        RELEASE,
        rejected(409, "lock_in_use", {"existing_job": EXISTING_JOB}),
        (409, "lock_in_use", False, LOCK_HELD_DETAILS),
    ),
    (
        RELEASE,
        rejected(400, "invalid_request", field_errors(("source_id", "format"))),
        CRAWLER_ERROR,
    ),
    (RELEASE, rejected(503, "unavailable"), CRAWLER_UNAVAILABLE),
    (RELEASE, rejected(500, "internal_error"), CRAWLER_ERROR),
    (RELEASE, rejected(404, "not_found"), CRAWLER_ERROR),  # 404 は返らない(契約外)
    # 9.2.4 設定の登録
    (
        REGISTER,
        rejected(400, "invalid_request", field_errors(("connector_type", "unsupported"))),
        (400, "invalid_request", False, field_errors(("connector_type", "unsupported"))),
    ),
    (
        REGISTER,
        rejected(400, "invalid_request", field_errors(("body", "type"))),
        CRAWLER_ERROR,
    ),
    (
        REGISTER,
        rejected(409, "source_already_exists", {"status": "active"}),
        (409, "source_already_exists", False, {"status": "active"}),
    ),
    (REGISTER, rejected(500, "internal_error"), CRAWLER_ERROR),
    (REGISTER, rejected(503, "unavailable"), CRAWLER_UNAVAILABLE),
    # 9.2.5 設定の更新
    (
        UPDATE,
        rejected(404, "source_config_not_found"),
        (404, "source_config_not_found", False, None),
    ),
    (UPDATE, rejected(409, "source_deleting"), (409, "source_deleting", False, None)),
    (
        UPDATE,
        rejected(400, "invalid_request", field_errors(("min_delete_count", "type"))),
        (400, "invalid_request", False, field_errors(("min_delete_count", "type"))),
    ),
    (UPDATE, rejected(500, "internal_error"), CRAWLER_ERROR),
    (UPDATE, rejected(503, "unavailable"), CRAWLER_UNAVAILABLE),
    # 9.2.6 ソース削除ジョブ起動
    (
        START_DELETE,
        rejected(404, "source_config_not_found"),
        (404, "source_config_not_found", False, None),
    ),
    (START_DELETE, rejected(409, "maintenance_enabled"), (409, "maintenance_enabled", False, None)),
    (
        START_DELETE,
        rejected(409, "lock_held", {"existing_job": EXISTING_JOB}),
        (409, "lock_held", False, LOCK_HELD_DETAILS),  # `options_applied`・`requested` は付けない
    ),
    (
        START_DELETE,
        rejected(400, "invalid_request", field_errors(("source_id", "format"))),
        CRAWLER_ERROR,
    ),
    (START_DELETE, rejected(503, "unavailable"), CRAWLER_UNAVAILABLE),
    (START_DELETE, rejected(500, "internal_error"), CRAWLER_ERROR),
    (START_DELETE, rejected(409, "source_deleting"), CRAWLER_ERROR),  # 削除中も受け付ける(返らない)
]
