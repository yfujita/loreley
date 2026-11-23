"""admin のテストが使う、偽物での組み立て。"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from loreley_api.admin import (
    AdminDependencies,
    AdminReaders,
    AdminSettings,
    build_admin_dependencies,
)
from loreley_api.common.timestamps import format_instant
from tests.api_config import make_admin_settings
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.in_memory_readers import InMemoryReaders
from tests.fakes.inline_runner import InlineRunner

ADMIN_PREFIX = "/api/admin/v1"
# 入力の検証で、エラーの本文・ログに入力値が漏れないことの確認に使う値。
SENTINEL = "SENTINEL-INPUT-VALUE"


def at(seconds_from_now: float) -> str:
    """固定の現在時刻(`DEFAULT_NOW`)から `seconds_from_now` 秒後の、API の日時の書式。"""
    return format_instant(DEFAULT_NOW + timedelta(seconds=seconds_from_now))


def seed_job(
    readers: InMemoryReaders,
    job_id: str,
    source_id: str = "docs",
    *,
    status: str = "succeeded",
    queued_at: float = 0,
    **fields: Any,
) -> None:
    """`queued_at` は現在からの秒数(大きいほど新しい)。"""
    defaults = {"trigger": "manual", "force_delete": False, "rewrite_mode": False}
    readers.put_job(
        job_id,
        source_id=source_id,
        status=status,
        queued_at=at(queued_at),
        **{**defaults, **fields},
    )


def errors_of(response: Any) -> list[dict[str, str]]:
    """400 `invalid_request` の応答から、違反の一覧を取り出す。"""
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    return error["details"]["errors"]


def on_nth_call(
    readers: InMemoryReaders, operation: str, n: int, action: Callable[[], None]
) -> None:
    """`operation` の n 回目(1 起点)の呼び出しの直前に `action` を実行する。"""
    for _ in range(n - 1):
        readers.behavior.before(operation, lambda: None)
    readers.behavior.before(operation, action)


def make_admin_dependencies(
    readers: InMemoryReaders,
    clock: FixedClock,
    runner: InlineRunner,
    settings: AdminSettings | None = None,
) -> AdminDependencies:
    return build_admin_dependencies(
        settings=settings if settings is not None else make_admin_settings(),
        clock=clock,
        # `BlockingRunner` の偽物(スレッドなし。実物は `tests/common/test_concurrency.py`)。
        runner=runner,  # type: ignore[arg-type]
        readers=AdminReaders(
            sources=readers.sources,
            jobs=readers.jobs,
            deletions=readers.deletions,
            search_index=readers.search_index,
            counts=readers.counts,
            cluster=readers.cluster,
        ),
    )
