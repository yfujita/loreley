"""EP-01 `GET /sources`・EP-02 `GET /sources/{source_id}`(アプリ全体。C 11章 6・12)。"""

import logging
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from loreley_api.common.timestamps import format_instant
from tests.admin.factories import ADMIN_PREFIX
from tests.fakes.clock import DEFAULT_NOW as NOW
from tests.fakes.in_memory_readers import STORE_TIMEOUT, STORE_UNAVAILABLE, InMemoryReaders
from tests.secret_assertions import assert_secret_absent

SOURCES = f"{ADMIN_PREFIX}/sources"
SENTINEL = "SENTINEL-INPUT-VALUE"


def at(seconds_from_now: float) -> str:
    return format_instant(NOW + timedelta(seconds=seconds_from_now))


def seed_source(readers: InMemoryReaders, source_id: str, **fields: Any) -> None:
    defaults: dict[str, Any] = {
        "connector_type": "file_system",
        "connector_config": {"root": "/data/documents"},
        "ttl": 2_592_000,
        "ratio_threshold": 0.2,
        "min_delete_count": 10,
        "schedule_cron": None,
        "status": "active",
        "updated_at": "2026-11-20T02:00:00.000Z",
    }
    readers.put_source(source_id, **{**defaults, **fields})


def seed_job(
    readers: InMemoryReaders, job_id: str, source_id: str, *, queued_at: float = 0, **fields: Any
) -> None:
    status = fields.pop("status", "succeeded")
    defaults = {"trigger": "manual", "force_delete": False, "rewrite_mode": False}
    readers.put_job(
        job_id,
        source_id=source_id,
        status=status,
        queued_at=at(queued_at),
        **{**defaults, **fields},
    )


def errors_of(response: Any) -> list[dict[str, str]]:
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    return error["details"]["errors"]


# --- EP-01 ---


def test_the_list_has_the_documented_shape_and_headers(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_source(readers, "docs-share", schedule_cron="0 3 * * *")
    seed_job(
        readers,
        "job-1",
        "docs-share",
        status="failed",
        queued_at=-100,
        started_at=at(-99),
        finished_at=at(-90),
        failure_reason="enumeration_failed",
    )
    readers.put_document("d1", source_id="docs-share", index_status="indexed")
    readers.refresh_search()

    response = client.get(SOURCES)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "items": [
            {
                "source_id": "docs-share",
                "connector_type": "file_system",
                "schedule_cron": "0 3 * * *",
                "status": "active",
                "last_crawl": {
                    "job_id": "job-1",
                    "source_id": "docs-share",
                    "job_type": "crawl",
                    "trigger": "manual",
                    "status": "failed",
                    "force_delete": False,
                    "rewrite_mode": False,
                    "queued_at": at(-100),
                    "started_at": at(-99),
                    "finished_at": at(-90),
                    "failure_reason": "enumeration_failed",
                    "stalled": False,
                    "cancellable": False,
                },
                "last_completed_at": None,
                "delete_job": None,
                "document_count": 1,
                "unavailable": {},
            }
        ],
        "unavailable": {},
    }


def test_an_empty_catalog_still_has_the_top_level_fields(client: TestClient) -> None:
    assert client.get(SOURCES).json() == {"items": [], "unavailable": {}}


def test_a_failed_source_list_is_a_503_without_details(
    readers: InMemoryReaders, client: TestClient
) -> None:
    readers.behavior.inject("sources.list_all", STORE_UNAVAILABLE)

    response = client.get(SOURCES)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "unavailable",
            "message": "the data store is unavailable",
            "retryable": True,
        }
    }


def test_never_run_and_failed_rows_are_told_apart_by_the_row_unavailable(
    readers: InMemoryReaders, client: TestClient
) -> None:
    """B 2.2 の例。2 行の `last_crawl` はどちらも `null` だが、行の `unavailable` で区別できる。"""
    seed_source(readers, "source-a")
    seed_source(readers, "source-b")
    readers.behavior.inject("jobs.latest_by_source", STORE_UNAVAILABLE)
    readers.refresh_search()

    body = client.get(SOURCES).json()

    rows = {item["source_id"]: item for item in body["items"]}
    assert rows["source-a"]["last_crawl"] is None
    assert rows["source-a"]["unavailable"] == {
        "last_crawl": "store_unavailable",
        "last_completed_at": "store_unavailable",
    }
    assert body["unavailable"] == {}


def test_a_lock_failure_of_one_source_is_reported_on_its_row_only(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_source(readers, "source-a")
    seed_source(readers, "source-b")
    seed_job(readers, "job-b", "source-b", status="running")
    readers.put_lock("source-b", job_id="job-b", lease_expires_at=at(60))
    readers.fail_document("jobs.get_locks", "source-b", STORE_TIMEOUT)
    readers.refresh_search()

    body = client.get(SOURCES).json()

    rows = {item["source_id"]: item for item in body["items"]}
    assert rows["source-a"]["last_crawl"] is None
    assert rows["source-a"]["unavailable"] == {}
    assert rows["source-b"]["last_crawl"]["stalled"] is None
    assert rows["source-b"]["last_crawl"]["cancellable"] is False
    assert rows["source-b"]["unavailable"] == {"last_crawl.stalled": "timeout"}
    assert body["unavailable"] == {}


def test_the_top_level_is_always_empty_and_no_key_uses_the_items_form(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_source(readers, "docs", status="deleting")
    seed_job(readers, "job-1", "docs", status="running")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(60))
    readers.behavior.inject("jobs.latest_by_source", STORE_UNAVAILABLE)
    readers.behavior.inject("search_index.count_by_source", STORE_TIMEOUT)
    readers.refresh_search()

    body = client.get(SOURCES).json()

    assert body["unavailable"] == {}
    assert body["items"][0]["unavailable"]
    assert not any(key.startswith("items") for key in body["items"][0]["unavailable"])


@pytest.mark.parametrize("query", ["?page=2", "?sort=source_id", "?source_id=a", "?unknown=1"])
def test_the_source_list_takes_no_query(client: TestClient, query: str) -> None:
    [error] = errors_of(client.get(f"{SOURCES}{query}"))

    assert error["reason"] == "unknown_field"


def test_the_source_list_accepts_only_get(client: TestClient) -> None:
    response = client.post(SOURCES)

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


# --- EP-02 ---


def test_the_detail_has_every_documented_field_in_order(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_source(readers, "docs", schedule_cron="0 3 * * *")
    readers.refresh_search()

    response = client.get(f"{SOURCES}/docs")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "source_id": "docs",
        "connector_type": "file_system",
        "connector_config": {"root": "/data/documents"},
        "ttl_seconds": 2_592_000,
        "ttl_days": 30,
        "ratio_threshold_percent": 20,
        "min_delete_count": 10,
        "schedule_cron": "0 3 * * *",
        "status": "active",
        "updated_at": "2026-11-20T02:00:00.000Z",
        "lock": {"state": "none", "job": None, "acquired_at": None},
        "last_crawl": None,
        "last_completed_at": None,
        "delete_job": None,
        "index": {"document_count": 0},
        "unavailable": {},
    }


def test_a_missing_source_is_a_404_source_config_not_found(client: TestClient) -> None:
    response = client.get(f"{SOURCES}/never-registered")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "source_config_not_found",
            "message": "the data source is not found",
            "retryable": False,
        }
    }


def test_a_failed_settings_read_is_a_503_not_a_404(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_source(readers, "docs")
    readers.behavior.inject("sources.get", STORE_UNAVAILABLE)

    response = client.get(f"{SOURCES}/docs")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "unavailable"


def test_a_partial_failure_is_a_200_with_nulls_and_the_top_level_full_path_keys(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_source(readers, "docs")
    readers.behavior.inject("jobs.get_locks", STORE_UNAVAILABLE)
    readers.behavior.inject("jobs.latest_by_source", STORE_TIMEOUT)
    readers.behavior.inject("counts.count_for_source", STORE_UNAVAILABLE)

    response = client.get(f"{SOURCES}/docs")

    assert response.status_code == 200
    body = response.json()
    assert body["lock"] is None
    assert (body["last_crawl"], body["last_completed_at"], body["delete_job"]) == (None, None, None)
    assert body["index"] == {"document_count": None}
    assert body["unavailable"] == {
        "lock": "store_unavailable",
        "last_crawl": "timeout",
        "last_completed_at": "timeout",
        "index.document_count": "store_unavailable",
    }
    assert body["source_id"] == "docs"


def test_an_unreadable_setting_is_null_with_a_malformed_key(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_source(readers, "docs", ttl="30d", status="paused")

    body = client.get(f"{SOURCES}/docs").json()

    assert (body["ttl_seconds"], body["ttl_days"], body["status"]) == (None, None, None)
    assert body["unavailable"] == {"ttl_seconds": "malformed", "status": "malformed"}


@pytest.mark.parametrize("source_id", ["-leading", ".dot", "a b", "a" * 257, "あ"])
def test_an_invalid_source_id_is_a_400_format_error_without_the_value(
    client: TestClient, source_id: str
) -> None:
    response = client.get(f"{SOURCES}/{source_id}")

    assert errors_of(response) == [{"field": "source_id", "reason": "format"}]


def test_a_source_id_with_a_slash_is_a_404_by_routing(client: TestClient) -> None:
    response = client.get(f"{SOURCES}/a/b")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("query", ["?page=1", "?unknown=1"])
def test_the_detail_takes_no_query(client: TestClient, query: str) -> None:
    [error] = errors_of(client.get(f"{SOURCES}/docs{query}"))

    assert error["reason"] == "unknown_field"


def test_the_path_is_validated_before_the_query(client: TestClient) -> None:
    """検証の順序は パス → クエリ(A 5.3)。"""
    response = client.get(f"{SOURCES}/-bad?unknown=1")

    assert errors_of(response) == [{"field": "source_id", "reason": "format"}]


def test_an_invalid_value_is_never_echoed_in_the_response_or_the_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    detail = client.get(f"{SOURCES}/{SENTINEL}!")
    listing = client.get(SOURCES, params={"unknown": SENTINEL})

    assert detail.status_code == 400
    assert listing.status_code == 400
    assert_secret_absent(SENTINEL, response_text=detail.text + listing.text, records=caplog.records)


def test_the_connector_config_is_returned_only_by_the_detail_and_not_logged(
    readers: InMemoryReaders, client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    seed_source(readers, "docs", connector_config={"root": f"/data/{SENTINEL}"})
    readers.refresh_search()

    listing = client.get(SOURCES)
    detail = client.get(f"{SOURCES}/docs")

    assert SENTINEL not in listing.text
    assert detail.json()["connector_config"] == {"root": f"/data/{SENTINEL}"}
    assert_secret_absent(SENTINEL, records=caplog.records)


def test_the_detail_accepts_only_get(client: TestClient) -> None:
    for method in (client.post, client.put, client.delete):
        response = method(f"{SOURCES}/docs")

        # POST・PUT・DELETE は後続のフェーズで足す(この時点では 405)。
        assert response.status_code == 405
