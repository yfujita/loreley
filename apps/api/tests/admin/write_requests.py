"""書き込み系 EP(EP-03〜08)のテストが共有する、リクエスト・Crawler の応答・ロックの用意。"""

from typing import Any

from tests.admin.factories import at, seed_job
from tests.fakes.in_memory_readers import InMemoryReaders

# `seed_lock` が用意できる `lock_state`(`unknown` は、読み取りの失敗で再現する)。
LOCK_STATES = ("none", "held_crawl", "held_delete", "lease_expired", "orphan", "just_acquired")


def register_body(**overrides: Any) -> dict[str, Any]:
    """EP-03 の有効な本文(B 3.3 の例)。取り除きたい項目(省略)には `...` を渡す。"""
    body: dict[str, Any] = {
        "source_id": "docs-share",
        "connector_type": "file_system",
        "connector_config": {
            "root": "/data/documents/share",
            "include_patterns": [],
            "exclude_patterns": [],
            "follow_symlinks": False,
            "include_hidden": False,
        },
        "ttl_days": 30,
        "ratio_threshold_percent": 20,
        "min_delete_count": 10,
        "schedule_cron": "0 3 * * *",
    }
    body.update(overrides)
    return {name: value for name, value in body.items() if value is not ...}


def update_body(**overrides: Any) -> dict[str, Any]:
    """EP-04 の有効な本文。取り除きたい項目には `...` を渡す。"""
    body = register_body(**overrides)
    body.pop("source_id", None)
    body.pop("connector_type", None)
    return body


def crawler_source_body(source_id: str = "docs-share", **overrides: Any) -> dict[str, Any]:
    """Crawler が返す保存内容(`SourceRecord` の本文。crawler-api 4.4)。"""
    body: dict[str, Any] = {
        "source_id": source_id,
        "connector_type": "file_system",
        "connector_config": {"root": "/data/documents/share"},
        "ttl": 2_592_000,
        "ratio_threshold": 0.2,
        "min_delete_count": 10,
        "schedule_cron": "0 3 * * *",
        "status": "active",
        "updated_at": "2026-11-24T01:02:03.456Z",
    }
    body.update(overrides)
    return {name: value for name, value in body.items() if value is not ...}


def crawler_accepted_body(
    job_type: str = "crawl", *, with_options: bool = True, **overrides: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "job_id": "job-20261124T010203Z-3fa9c2d1",
        "job_type": job_type,
        "source_id": "docs",
        "status": "queued",
        "trigger": "manual",
        "queued_at": "2026-11-24T01:02:03.456Z",
    }
    if with_options:
        body.update({"force_delete": False, "rewrite_mode": False})
    body.update(overrides)
    return {name: value for name, value in body.items() if value is not ...}


def seed_lock(readers: InMemoryReaders, state: str, source_id: str = "docs") -> None:
    """`lock_state` が `state` になる、ロック文書・ジョブ記録を用意する(B 2.9)。"""
    job_id = f"job-{state}"
    match state:
        case "none":
            return
        case "held_crawl" | "held_delete":
            job_type = "crawl" if state == "held_crawl" else "source_delete"
            seed_job(readers, job_id, source_id, status="running", job_type=job_type)
            readers.put_lock(source_id, job_id=job_id, lease_expires_at=at(60), acquired_at=at(-5))
        case "lease_expired":
            seed_job(readers, job_id, source_id, status="running")
            readers.put_lock(source_id, job_id=job_id, lease_expires_at=at(-60), acquired_at=at(-5))
        case "orphan":
            readers.put_lock(source_id, job_id="no-such-job", acquired_at=at(-120))
        case "just_acquired":
            readers.put_lock(source_id, job_id="no-such-job", acquired_at=at(-10))
        case _:
            raise ValueError(f"unknown lock state: {state}")
