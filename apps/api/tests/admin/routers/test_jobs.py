"""EP-09 `GET /jobs`・EP-10 `GET /jobs/{job_id}`(アプリ全体。C 11章 6・7・12)。"""

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

JOBS = f"{ADMIN_PREFIX}/jobs"
SENTINEL = "SENTINEL-INPUT-VALUE"


def at(seconds_from_now: float) -> str:
    return format_instant(NOW + timedelta(seconds=seconds_from_now))


def seed_job(
    readers: InMemoryReaders,
    job_id: str,
    *,
    source_id: str = "docs",
    queued_at: float = 0,
    **fields: Any,
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


# --- EP-09 ---


def test_the_list_has_the_documented_shape_and_headers(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_job(readers, "job-1", status="running", started_at=at(-9))
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(60))
    readers.refresh_search()

    response = client.get(JOBS)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "items": [
            {
                "job_id": "job-1",
                "source_id": "docs",
                "job_type": "crawl",
                "trigger": "manual",
                "status": "running",
                "force_delete": False,
                "rewrite_mode": False,
                "queued_at": at(0),
                "started_at": at(-9),
                "finished_at": None,
                "failure_reason": None,
                "stalled": False,
                "cancellable": True,
                "unavailable": {},
            }
        ],
        "total": 1,
        "page": 1,
        "items_per_page": 25,
        "window_limit": 10_000,
        "unavailable": {},
    }


def test_an_empty_list_still_has_every_field(client: TestClient) -> None:
    assert client.get(JOBS).json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "items_per_page": 25,
        "window_limit": 10_000,
        "unavailable": {},
    }


def test_the_default_order_is_newest_first_and_sort_can_reverse_it(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_job(readers, "old", queued_at=-10)
    seed_job(readers, "new", queued_at=-1)
    readers.refresh_search()

    def ids(query: str) -> list[str]:
        return [item["job_id"] for item in client.get(f"{JOBS}{query}").json()["items"]]

    assert ids("") == ["new", "old"]
    assert ids("?sort=-queued_at") == ["new", "old"]
    assert ids("?sort=queued_at") == ["old", "new"]


def test_the_page_and_the_page_size_choose_the_window(
    readers: InMemoryReaders, client: TestClient
) -> None:
    for number in range(60):
        seed_job(readers, f"job-{number:02d}", queued_at=-number)
    readers.refresh_search()

    body = client.get(f"{JOBS}?page=2&items_per_page=25").json()

    assert [item["job_id"] for item in body["items"]][:2] == ["job-25", "job-26"]
    assert (body["total"], body["page"], body["items_per_page"]) == (60, 2, 25)
    assert len(body["items"]) == 25


@pytest.mark.parametrize("items_per_page", [25, 50, 100])
def test_the_window_boundary_is_accepted_at_exactly_10000(
    client: TestClient, items_per_page: int
) -> None:
    last_page = 10_000 // items_per_page

    response = client.get(f"{JOBS}?page={last_page}&items_per_page={items_per_page}")

    assert response.status_code == 200
    assert response.json()["page"] == last_page


@pytest.mark.parametrize("items_per_page", [25, 50, 100])
def test_a_page_beyond_the_window_is_a_400_range_on_page(
    client: TestClient, items_per_page: int
) -> None:
    first_page_over = 10_000 // items_per_page + 1

    response = client.get(f"{JOBS}?page={first_page_over}&items_per_page={items_per_page}")

    assert errors_of(response) == [{"field": "page", "reason": "range"}]


def test_the_total_is_exact_even_beyond_the_window(
    readers: InMemoryReaders, client: TestClient
) -> None:
    for number in range(10_030):
        seed_job(readers, f"job-{number:05d}", queued_at=-number)
    readers.refresh_search()

    body = client.get(f"{JOBS}?page=400&items_per_page=25").json()

    assert body["total"] == 10_030
    assert body["window_limit"] == 10_000
    assert len(body["items"]) == 25


@pytest.mark.parametrize(
    ("query", "field", "reason"),
    [
        ("page=0", "page", "range"),
        ("page=-1", "page", "range"),
        ("page=abc", "page", "type"),
        ("page=1.5", "page", "type"),
        ("items_per_page=10", "items_per_page", "unsupported"),
        ("items_per_page=0", "items_per_page", "unsupported"),
        ("items_per_page=abc", "items_per_page", "type"),
        ("sort=status", "sort", "unsupported"),
        ("sort=-status", "sort", "unsupported"),
        ("sort=queued_at,job_id", "sort", "unsupported"),
        ("status=weird", "status", "unsupported"),
        ("status=ACTIVE", "status", "unsupported"),
        ("source_id=a/b", "source_id", "format"),
        ("source_id=", "source_id", "format"),
        ("source_id=-leading-dash", "source_id", "format"),
        ("unknown=1", "unknown", "unknown_field"),
    ],
)
def test_an_invalid_query_is_a_400_with_the_field_and_the_reason(
    client: TestClient, query: str, field: str, reason: str
) -> None:
    response = client.get(f"{JOBS}?{query}")

    assert errors_of(response) == [{"field": field, "reason": reason}]


def test_every_violation_of_the_filters_is_reported_together(client: TestClient) -> None:
    response = client.get(f"{JOBS}?source_id=a/b&status=weird")

    assert errors_of(response) == [
        {"field": "source_id", "reason": "format"},
        {"field": "status", "reason": "unsupported"},
    ]


def test_an_unknown_query_name_is_cleaned_up_and_its_value_is_not_echoed(
    client: TestClient,
) -> None:
    response = client.get(f"{JOBS}", params={"bad\nname": SENTINEL})

    [error] = errors_of(response)
    assert error == {"field": "bad\\nname", "reason": "unknown_field"}
    assert SENTINEL not in response.text


def test_an_invalid_value_is_never_echoed_in_the_response_or_the_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    response = client.get(JOBS, params={"source_id": f"{SENTINEL}/x", "status": SENTINEL})

    assert response.status_code == 400
    assert_secret_absent(SENTINEL, response_text=response.text, records=caplog.records)


@pytest.mark.parametrize(
    "status", ["queued", "running", "succeeded", "partially_succeeded", "failed", "cancelled"]
)
def test_each_status_filters_by_the_stored_status(
    readers: InMemoryReaders, client: TestClient, status: str
) -> None:
    for name in ("queued", "succeeded", "partially_succeeded", "failed", "cancelled"):
        seed_job(readers, f"job-{name}", status=name)
    seed_job(readers, "job-running", status="running")
    readers.put_lock("docs", job_id="job-running", lease_expires_at=at(60))
    readers.refresh_search()

    body = client.get(f"{JOBS}?status={status}").json()

    assert [item["job_id"] for item in body["items"]] == [f"job-{status}"]


def test_active_means_queued_or_running(readers: InMemoryReaders, client: TestClient) -> None:
    seed_job(readers, "job-queued", status="queued", queued_at=1)
    seed_job(readers, "job-running", status="running", queued_at=2)
    seed_job(readers, "job-failed", status="failed", queued_at=3)
    readers.put_lock("docs", job_id="job-running", lease_expires_at=at(60))
    readers.refresh_search()

    body = client.get(f"{JOBS}?status=active").json()

    assert {item["job_id"] for item in body["items"]} == {"job-queued", "job-running"}
    assert body["total"] == 2


def test_a_stalled_running_job_is_still_running_and_is_not_in_failed(
    readers: InMemoryReaders, client: TestClient
) -> None:
    """絞り込みは保存上の状態による。リース切れの実行中は `running`(`stalled` が別に出る)。"""
    seed_job(readers, "job-1", status="running")
    readers.put_lock("docs", job_id="job-1", lease_expires_at=at(-60))
    readers.refresh_search()

    running = client.get(f"{JOBS}?status=running").json()
    failed = client.get(f"{JOBS}?status=failed").json()

    assert [(item["job_id"], item["stalled"]) for item in running["items"]] == [("job-1", True)]
    assert failed["items"] == []


def test_an_unregistered_source_gives_an_empty_result_with_200(client: TestClient) -> None:
    response = client.get(f"{JOBS}?source_id=never-registered")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_a_failed_lock_document_is_reported_on_that_row_only(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_job(readers, "job-a", source_id="a", status="running", queued_at=2)
    seed_job(readers, "job-b", source_id="b", status="running", queued_at=1)
    readers.put_lock("a", job_id="job-a", lease_expires_at=at(60))
    readers.put_lock("b", job_id="job-b", lease_expires_at=at(60))
    readers.fail_document("jobs.get_locks", "b", STORE_TIMEOUT)
    readers.refresh_search()

    body = client.get(JOBS).json()

    rows = {item["job_id"]: item for item in body["items"]}
    assert (rows["job-a"]["stalled"], rows["job-a"]["unavailable"]) == (False, {})
    assert (rows["job-b"]["stalled"], rows["job-b"]["cancellable"]) == (None, False)
    assert rows["job-b"]["unavailable"] == {"stalled": "timeout"}
    assert body["unavailable"] == {}


def test_a_failed_list_read_is_a_503_without_details(
    readers: InMemoryReaders, client: TestClient
) -> None:
    readers.behavior.inject("jobs.list_jobs", STORE_UNAVAILABLE)

    response = client.get(JOBS)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "unavailable",
            "message": "the data store is unavailable",
            "retryable": True,
        }
    }


def test_the_list_accepts_only_get(client: TestClient) -> None:
    response = client.post(JOBS)

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


# --- EP-10 ---


def seed_failed_crawl(readers: InMemoryReaders, job_id: str = "job-1") -> None:
    seed_job(
        readers,
        job_id,
        status="failed",
        started_at=at(-60),
        finished_at=at(-30),
        failure_reason="skip_limit_exceeded",
        failure_detail="skip_limit_exceeded: 20 consecutive skips",
        registration={"enumerated_count": 1300, "partial": True},
    )
    readers.put_source("docs", status="active")
    readers.refresh_search()


def test_the_detail_has_every_documented_field(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_failed_crawl(readers)

    response = client.get(f"{JOBS}/job-1")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert list(body) == [
        "job_id",
        "source_id",
        "job_type",
        "trigger",
        "status",
        "force_delete",
        "rewrite_mode",
        "queued_at",
        "started_at",
        "finished_at",
        "failure_reason",
        "stalled",
        "cancellable",
        "failure_detail",
        "lease_expires_at",
        "latest_for_source",
        "rerunnable",
        "rerun_blocked_reason",
        "cancel_after_finish_notice",
        "warnings",
        "registration",
        "deletion",
        "unavailable",
    ]
    assert body["rerunnable"] is True
    assert body["registration"]["phase"] == "incomplete"
    assert body["registration"]["created_count"] is None
    assert body["deletion"]["current_state"] == "not_found"
    assert body["unavailable"] == {}


def test_a_missing_job_is_a_404_job_not_found(client: TestClient) -> None:
    response = client.get(f"{JOBS}/no-such-job")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "job_not_found", "message": "the job is not found", "retryable": False}
    }


def test_a_lock_or_skip_record_id_is_a_404_not_a_job(
    readers: InMemoryReaders, client: TestClient
) -> None:
    readers.put_lock("docs", job_id="job-1")

    assert client.get(f"{JOBS}/lock-docs").status_code == 404


def test_a_failed_read_of_the_job_is_a_503_not_a_404(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_failed_crawl(readers)
    readers.fail_document("jobs.get_jobs", "job-1", STORE_UNAVAILABLE)

    response = client.get(f"{JOBS}/job-1")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "unavailable"


def test_a_partial_failure_is_a_200_with_null_and_the_top_level_unavailable(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_failed_crawl(readers)
    readers.behavior.inject("jobs.latest_crawl_id", STORE_UNAVAILABLE)
    readers.behavior.inject("deletions.get_result", STORE_TIMEOUT)

    response = client.get(f"{JOBS}/job-1")

    assert response.status_code == 200
    body = response.json()
    assert body["latest_for_source"] is None
    assert (body["rerunnable"], body["rerun_blocked_reason"]) == (None, None)
    assert body["deletion"]["current"] is None
    assert body["deletion"]["current_state"] == "unavailable"
    assert body["unavailable"] == {
        "latest_for_source": "store_unavailable",
        "rerunnable": "store_unavailable",
        "deletion.current": "timeout",
    }


@pytest.mark.parametrize(
    "path",
    [
        "/jobs/a%00b",
        "/jobs/a%0db",
        "/jobs/a%09b",
        "/jobs/a%7Fb",
        f"/jobs/{'x' * 257}",
        f"/jobs/{'あ' * 86}",
    ],
)
def test_an_invalid_job_id_is_a_400_format_on_job_id(client: TestClient, path: str) -> None:
    response = client.get(f"{ADMIN_PREFIX}{path}")

    assert errors_of(response) == [{"field": "job_id", "reason": "format"}]


def test_a_job_id_with_a_line_feed_is_a_404_not_found_before_the_validation(
    client: TestClient,
) -> None:
    """現状の記録: Starlette の `Mount` の正規表現(`.` が改行に一致しない)で、外側が 404 にする。

    B 2.12 は制御文字を 400 `format` としているが、改行だけは検証に届かない(どちらもエラーで、
    Crawler・OpenSearch には届かない)。
    """
    response = client.get(f"{JOBS}/a%0Ab")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_a_job_id_with_a_slash_is_a_404_not_found_by_routing(client: TestClient) -> None:
    response = client.get(f"{JOBS}/a%2Fb")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_a_job_id_with_special_characters_is_looked_up_as_it_is(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_failed_crawl(readers, "job?#%.id")

    response = client.get(f"{JOBS}/job%3F%23%25.id")

    assert response.status_code == 200
    assert response.json()["job_id"] == "job?#%.id"


def test_an_unknown_query_of_the_detail_is_a_400(client: TestClient) -> None:
    assert errors_of(client.get(f"{JOBS}/job-1?verbose=1")) == [
        {"field": "verbose", "reason": "unknown_field"}
    ]


def test_the_detail_validates_the_path_before_the_query(client: TestClient) -> None:
    """検証の順序は パス → クエリ(A 5.3)。両方が違反なら、`job_id` の違反だけを返す。"""
    response = client.get(f"{ADMIN_PREFIX}/jobs/a%00b?verbose=1")

    assert errors_of(response) == [{"field": "job_id", "reason": "format"}]


def test_a_body_on_the_detail_is_ignored(readers: InMemoryReaders, client: TestClient) -> None:
    seed_failed_crawl(readers)

    response = client.request("GET", f"{JOBS}/job-1", content=b"not json at all")

    assert response.status_code == 200


def test_the_job_id_is_in_neither_the_error_response_nor_the_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    not_found = client.get(f"{JOBS}/{SENTINEL}")
    invalid = client.get(f"{JOBS}/{SENTINEL}%00")

    assert (not_found.status_code, invalid.status_code) == (404, 400)
    assert_secret_absent(
        SENTINEL, response_text=not_found.text + invalid.text, records=caplog.records
    )
    access_lines = [r.getMessage() for r in caplog.records if r.name == "loreley_api.access"]
    assert access_lines
    assert all("/jobs/{job_id}" in line for line in access_lines)
