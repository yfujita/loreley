"""EP-06 クロールの起動・EP-07 取消・EP-08 ロック解放(アプリ全体。C 11章 1・11・12)。

Crawler は `FakeCrawlerClient`(HTTP を通した確認は `test_write_eps_over_http.py`)。
データ削除に関わる指定(`force_delete`・`rewrite_mode`)・削除ジョブ・ロック解放が、取り違えられずに
Crawler に届くことを表駆動で確かめる。
"""

import json
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from loreley_api.infrastructure.crawler_client import CrawlerRejected, CrawlerSucceeded
from tests.admin.factories import ADMIN_PREFIX, SENTINEL, errors_of
from tests.admin.write_requests import (
    LOCK_STATES,
    crawler_accepted_body,
    register_body,
    seed_lock,
)
from tests.fakes.fake_crawler_client import FakeCrawlerClient
from tests.fakes.in_memory_readers import STORE_TIMEOUT, STORE_UNAVAILABLE, InMemoryReaders
from tests.fakes.inline_runner import InlineRunner
from tests.secret_assertions import assert_secret_absent

SOURCES = f"{ADMIN_PREFIX}/sources"
JOBS = f"{ADMIN_PREFIX}/jobs"
JSON_HEADERS = {"Content-Type": "application/json"}
EXISTING_JOB = {
    "job_id": "job-existing",
    "job_type": "crawl",
    "status": "running",
    "trigger": "schedule",
    "lease_expires_at": "2026-11-24T00:01:00.000Z",
}


def violations_of(response: Any) -> list[tuple[str, str]]:
    return [(error["field"], error["reason"]) for error in errors_of(response)]


def lock_conflict(code: str = "lock_held") -> CrawlerRejected:
    return CrawlerRejected(409, code, {"existing_job": EXISTING_JOB}, None)


# --- EP-06: 指定の取り違えがないこと ---

OPTION_COMBINATIONS = [(False, False), (True, False), (False, True), (True, True)]


@pytest.mark.parametrize(("force_delete", "rewrite_mode"), OPTION_COMBINATIONS)
def test_the_options_of_a_crawl_reach_the_crawler_and_the_response_unswapped(
    client: TestClient, crawler: FakeCrawlerClient, force_delete: bool, rewrite_mode: bool
) -> None:
    response = client.post(
        f"{SOURCES}/docs/crawl-jobs",
        json={"force_delete": force_delete, "rewrite_mode": rewrite_mode},
    )

    assert response.status_code == 202
    [request] = crawler.requests
    assert request.operation == "start_crawl"
    assert request.arguments == {
        "source_id": "docs",
        "force_delete": force_delete,
        "rewrite_mode": rewrite_mode,
    }
    body = response.json()
    assert (body["force_delete"], body["rewrite_mode"]) == (force_delete, rewrite_mode)
    assert (body["job_type"], body["trigger"], body["status"]) == ("crawl", "manual", "queued")


@pytest.mark.parametrize(("force_delete", "rewrite_mode"), OPTION_COMBINATIONS)
def test_the_requested_options_of_a_lock_conflict_are_the_ones_that_were_sent(
    client: TestClient, crawler: FakeCrawlerClient, force_delete: bool, rewrite_mode: bool
) -> None:
    crawler.behavior.inject("start_crawl", lock_conflict())

    response = client.post(
        f"{SOURCES}/docs/crawl-jobs",
        json={"force_delete": force_delete, "rewrite_mode": rewrite_mode},
    )

    assert response.status_code == 409
    assert response.json()["error"]["details"]["options_applied"] is False
    assert response.json()["error"]["details"]["requested"] == {
        "force_delete": force_delete,
        "rewrite_mode": rewrite_mode,
    }


@pytest.mark.parametrize(
    "request_kwargs",
    [{}, {"json": {}}, {"content": b"", "headers": JSON_HEADERS}, {"content": b"", "headers": {}}],
    ids=["no-body", "empty-object", "empty-json-body", "empty-without-content-type"],
)
def test_a_crawl_without_options_uses_false_for_both(
    client: TestClient, crawler: FakeCrawlerClient, request_kwargs: dict[str, Any]
) -> None:
    response = client.post(f"{SOURCES}/docs/crawl-jobs", **request_kwargs)

    assert response.status_code == 202
    assert crawler.requests[0].arguments == {
        "source_id": "docs",
        "force_delete": False,
        "rewrite_mode": False,
    }


def test_only_one_option_given_leaves_the_other_false(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    client.post(f"{SOURCES}/docs/crawl-jobs", json={"force_delete": True})
    client.post(f"{SOURCES}/docs/crawl-jobs", json={"rewrite_mode": True})

    assert [
        (r.arguments["force_delete"], r.arguments["rewrite_mode"]) for r in crawler.requests
    ] == [(True, False), (False, True)]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"force_delete": "true"}, [("force_delete", "type")]),
        ({"force_delete": 1}, [("force_delete", "type")]),
        ({"force_delete": None}, [("force_delete", "type")]),
        ({"rewrite_mode": "false"}, [("rewrite_mode", "type")]),
        ({"rewrite_mode": 0}, [("rewrite_mode", "type")]),
        ({"force_delete": []}, [("force_delete", "type")]),
        ({"unknown": True}, [("unknown", "unknown_field")]),
        (
            {"force_delete": "x", "rewrite_mode": "y", "other": 1},
            [("force_delete", "type"), ("rewrite_mode", "type"), ("other", "unknown_field")],
        ),
        ([], [("body", "type")]),
        ("true", [("body", "type")]),
    ],
)
def test_a_crawl_with_an_invalid_body_is_rejected_and_nothing_is_sent(
    client: TestClient,
    crawler: FakeCrawlerClient,
    body: Any,
    expected: list[tuple[str, str]],
) -> None:
    response = client.post(f"{SOURCES}/docs/crawl-jobs", json=body)

    assert sorted(violations_of(response)) == sorted(expected)
    assert crawler.requests == []


@pytest.mark.parametrize(
    ("content", "headers"),
    [
        (b"{broken", JSON_HEADERS),
        (b'{"force_delete": true}', {"Content-Type": "text/plain"}),
        (b'{"force_delete": true}', {}),
        (b'{"force_delete": NaN}', JSON_HEADERS),
        (b" " * (1024 * 1024 + 1), JSON_HEADERS),
    ],
    ids=["broken", "text-plain", "no-content-type", "nan", "over-1mib"],
)
def test_a_crawl_with_an_unreadable_body_is_a_400_without_details(
    client: TestClient, crawler: FakeCrawlerClient, content: bytes, headers: dict[str, str]
) -> None:
    """本文があるときは JSON(`application/json`)でなければならない。誤って送った `true` で
    データ削除を起動しない(`force_delete` は既定の `false` にならず、要求が拒否される)。
    """
    response = client.post(f"{SOURCES}/docs/crawl-jobs", content=content, headers=headers)

    assert response.status_code == 400
    assert "details" not in response.json()["error"]
    assert crawler.requests == []


def test_a_crawl_is_validated_in_the_order_path_query_body(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    bad_path = client.post(
        f"{SOURCES}/-bad/crawl-jobs?x=1", content=b"{broken", headers=JSON_HEADERS
    )
    bad_query = client.post(
        f"{SOURCES}/docs/crawl-jobs?x=1", content=b"{broken", headers=JSON_HEADERS
    )

    assert violations_of(bad_path) == [("source_id", "format")]
    assert violations_of(bad_query) == [("x", "unknown_field")]
    assert crawler.requests == []


# --- 本文なしの POST は Origin を問わず処理される(現状の記録。C 11章 11(c)。HO-41) ---


@pytest.mark.parametrize(
    ("path", "operation"),
    [
        (f"{SOURCES}/docs/delete-jobs", "start_delete_job"),
        (f"{SOURCES}/docs/crawl-jobs", "start_crawl"),
        (f"{JOBS}/job-1/cancel", "cancel_job"),
    ],
    ids=["EP-05", "EP-06", "EP-07"],
)
@pytest.mark.parametrize(
    "headers",
    [{}, {"Origin": "https://example.invalid"}, {"Origin": "null"}],
    ids=["no-origin", "foreign-origin", "null-origin"],
)
def test_a_post_without_a_body_is_processed_whatever_the_origin(
    client: TestClient,
    crawler: FakeCrawlerClient,
    path: str,
    operation: str,
    headers: dict[str, str],
) -> None:
    """ブラウザの単純なリクエスト(本文なしの POST)は、`Origin` が何でも処理される(保護はない)。

    README の注意書き(HO-41)の根拠となる事実の記録で、これを変えるときは設計(A 2.3・BAPI-U-8)
    から見直す。CORS のヘッダーは付かない(別オリジンのページは応答を読めないが、処理は行われる)。
    """
    response = client.post(path, headers=headers)

    assert response.status_code in (200, 202)
    assert [request.operation for request in crawler.requests] == [operation]
    assert not [name for name in response.headers if name.lower().startswith("access-control-")]


def test_a_registration_needs_the_json_content_type_so_a_simple_request_cannot_reach_it(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    """EP-03 は本文を要するので、ブラウザの単純なリクエスト(`text/plain`)では届かない(B 2.10)。"""
    response = client.post(
        f"{ADMIN_PREFIX}/sources",
        content=json.dumps(register_body()).encode(),
        headers={"Content-Type": "text/plain", "Origin": "https://example.invalid"},
    )

    assert response.status_code == 400
    assert crawler.requests == []


# --- EP-07 ---


@pytest.mark.parametrize(("crawler_status", "job_status"), [(200, "cancelled"), (202, "running")])
def test_a_cancel_keeps_the_status_and_body_of_the_crawler(
    client: TestClient, crawler: FakeCrawlerClient, crawler_status: int, job_status: str
) -> None:
    crawler.behavior.inject(
        "cancel_job", CrawlerSucceeded(crawler_status, {"job_id": "job-1", "status": job_status})
    )

    response = client.post(f"{JOBS}/job-1/cancel")

    assert response.status_code == crawler_status
    assert response.json() == {"job_id": "job-1", "status": job_status}
    assert [(r.operation, r.arguments) for r in crawler.requests] == [
        ("cancel_job", {"job_id": "job-1"})
    ]


@pytest.mark.parametrize(
    ("path_id", "job_id"),
    [
        ("a%3Fb%23c%25d", "a?b#c%d"),
        ("%2E", "."),
        ("%2E%2E", ".."),
        ("a%20b", "a b"),
        ("%E6%97%A5%E6%9C%AC", "日本"),
        ("x" * 256, "x" * 256),
        ("%E3%81%82" * 85, "あ" * 85),  # 255 バイト
    ],
)
def test_a_job_id_with_unusual_characters_reaches_the_crawler_as_it_is(
    client: TestClient, crawler: FakeCrawlerClient, path_id: str, job_id: str
) -> None:
    response = client.post(f"{JOBS}/{path_id}/cancel")

    assert response.status_code == 200
    assert crawler.requests[0].arguments == {"job_id": job_id}


@pytest.mark.parametrize(
    "path_id",
    ["x" * 257, "%E3%81%82" * 86, "a%00b", "a%09b", "a%0Db", "a%7Fb", "a%C2%80b"],
    ids=["257-chars", "258-bytes", "nul", "tab", "cr", "del", "c1-control"],
)
def test_an_invalid_job_id_is_rejected_and_not_sent(
    client: TestClient, crawler: FakeCrawlerClient, path_id: str
) -> None:
    response = client.post(f"{JOBS}/{path_id}/cancel")

    assert violations_of(response) == [("job_id", "format")]
    assert crawler.requests == []


def test_a_job_id_with_a_line_feed_is_a_404_before_the_validation_and_is_not_sent(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    """現状の記録(EP-10 と同じ): Starlette の `Mount` の正規表現が改行に一致せず 404 になる。"""
    response = client.post(f"{JOBS}/a%0Ab/cancel")

    assert response.status_code == 404
    assert crawler.requests == []


def test_a_job_id_with_a_slash_does_not_reach_a_route_and_is_not_sent(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    response = client.post(f"{JOBS}/a%2Fb/cancel")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert crawler.requests == []


def test_a_cancel_ignores_the_body_and_rejects_a_query(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    ignored = client.post(f"{JOBS}/job-1/cancel", content=b"{broken", headers=JSON_HEADERS)
    rejected = client.post(f"{JOBS}/job-1/cancel?x=1")

    assert ignored.status_code == 200
    assert violations_of(rejected) == [("x", "unknown_field")]
    assert len(crawler.requests) == 1


# --- EP-08 ---


@pytest.mark.parametrize(
    ("released", "failed_job_id"), [(True, "job-9"), (True, None), (False, None)]
)
def test_a_lock_release_returns_the_crawler_result(
    client: TestClient, crawler: FakeCrawlerClient, released: bool, failed_job_id: str | None
) -> None:
    crawler.behavior.inject(
        "release_lock",
        CrawlerSucceeded(
            200, {"source_id": "docs", "released": released, "failed_job_id": failed_job_id}
        ),
    )

    response = client.delete(f"{SOURCES}/docs/lock")

    assert response.status_code == 200
    assert response.json() == {
        "source_id": "docs",
        "released": released,
        "failed_job_id": failed_job_id,
    }
    assert [(r.operation, r.arguments) for r in crawler.requests] == [
        ("release_lock", {"source_id": "docs"})
    ]


def test_a_lock_release_works_without_a_source_configuration(
    client: TestClient, crawler: FakeCrawlerClient, readers: InMemoryReaders
) -> None:
    """設定がなくても解放できる(ソース削除の後に残ったロック)。Admin API は設定を確認しない。"""
    response = client.delete(f"{SOURCES}/gone/lock")

    assert response.status_code == 200
    assert readers.behavior.calls == []


def test_a_lock_release_with_an_invalid_id_or_a_query_is_rejected_and_not_sent(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    bad_id = client.delete(f"{SOURCES}/-bad/lock")
    bad_query = client.delete(f"{SOURCES}/docs/lock?force=1")

    assert violations_of(bad_id) == [("source_id", "format")]
    assert violations_of(bad_query) == [("force", "unknown_field")]
    assert crawler.requests == []


def test_each_endpoint_calls_exactly_its_own_crawler_operation(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    """EP-05(削除ジョブ)・EP-06(クロール)・EP-08(ロック解放)の取り違えがない。"""
    client.post(f"{SOURCES}/docs/delete-jobs")
    client.post(f"{SOURCES}/docs/crawl-jobs")
    client.delete(f"{SOURCES}/docs/lock")
    client.post(f"{JOBS}/job-1/cancel")

    assert [request.operation for request in crawler.requests] == [
        "start_delete_job",
        "start_crawl",
        "release_lock",
        "cancel_job",
    ]


# --- 409 の付随情報(lock_state)。C 11章: 取得が失敗してもステータスと existing_job は変わらない ---

CONFLICT_ENDPOINTS = [
    pytest.param("start_crawl", "post", "/sources/docs/crawl-jobs", "lock_held", id="EP-06"),
    pytest.param("start_delete_job", "post", "/sources/docs/delete-jobs", "lock_held", id="EP-05"),
    pytest.param("release_lock", "delete", "/sources/docs/lock", "lock_in_use", id="EP-08"),
]


@pytest.mark.parametrize(("operation", "method", "path", "code"), CONFLICT_ENDPOINTS)
@pytest.mark.parametrize("lock_state", LOCK_STATES)
def test_a_lock_conflict_reports_the_lock_state_read_from_the_lock_and_the_job(
    client: TestClient,
    crawler: FakeCrawlerClient,
    readers: InMemoryReaders,
    operation: str,
    method: str,
    path: str,
    code: str,
    lock_state: str,
) -> None:
    seed_lock(readers, lock_state)
    crawler.behavior.inject(operation, lock_conflict(code))

    response = getattr(client, method)(f"{ADMIN_PREFIX}{path}")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == code
    assert error["retryable"] is False
    assert error["details"]["existing_job"] == EXISTING_JOB
    assert error["details"]["lock_state"] == lock_state


READ_FAILURES = [
    pytest.param("jobs.get_locks", STORE_UNAVAILABLE, id="lock-unavailable"),
    pytest.param("jobs.get_locks", STORE_TIMEOUT, id="lock-timeout"),
    pytest.param("jobs.get_jobs", STORE_UNAVAILABLE, id="job-unavailable"),
    pytest.param("jobs.get_jobs", STORE_TIMEOUT, id="job-timeout"),
]


@pytest.mark.parametrize(("operation", "method", "path", "code"), CONFLICT_ENDPOINTS)
@pytest.mark.parametrize(("failing_read", "failure"), READ_FAILURES)
def test_a_failed_read_of_the_lock_state_changes_neither_the_status_nor_the_existing_job(
    client: TestClient,
    crawler: FakeCrawlerClient,
    readers: InMemoryReaders,
    operation: str,
    method: str,
    path: str,
    code: str,
    failing_read: str,
    failure: Any,
) -> None:
    seed_lock(readers, "held_crawl")
    readers.behavior.inject(failing_read, failure, times=None)
    crawler.behavior.inject(operation, lock_conflict(code))

    response = getattr(client, method)(f"{ADMIN_PREFIX}{path}")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == code
    assert error["retryable"] is False
    assert error["details"]["existing_job"] == EXISTING_JOB
    assert error["details"]["lock_state"] == "unknown"


def test_the_lock_state_of_a_conflict_is_read_after_the_crawler_answered(
    client: TestClient, crawler: FakeCrawlerClient, readers: InMemoryReaders
) -> None:
    """ロックは Crawler が取るので、その後に読む(送る前に読むと、`none` になる)。"""
    crawler.behavior.inject("start_crawl", lock_conflict())
    crawler.behavior.before("start_crawl", lambda: seed_lock(readers, "held_crawl"))

    response = client.post(f"{SOURCES}/docs/crawl-jobs")

    assert response.json()["error"]["details"]["lock_state"] == "held_crawl"


def test_the_lock_is_read_before_the_job_and_only_for_a_conflict(
    client: TestClient,
    crawler: FakeCrawlerClient,
    readers: InMemoryReaders,
    inline_runner: InlineRunner,
) -> None:
    seed_lock(readers, "held_crawl")

    client.post(f"{SOURCES}/docs/crawl-jobs")

    # 成功のときは、OpenSearch を読まない。Crawler の呼び出しは `crawler` の枠。
    assert readers.behavior.calls == []
    assert inline_runner.categories == ["crawler"]

    crawler.behavior.inject("start_crawl", lock_conflict())
    inline_runner.categories.clear()
    client.post(f"{SOURCES}/docs/crawl-jobs")

    assert [call.operation for call in readers.behavior.calls] == [
        "jobs.get_locks",
        "jobs.get_jobs",
    ]
    assert inline_runner.categories == ["crawler", "opensearch", "opensearch"]


@pytest.mark.parametrize(
    "rejection",
    [
        CrawlerRejected(404, "source_config_not_found", None, None),
        CrawlerRejected(409, "source_deleting", None, None),
        CrawlerRejected(409, "maintenance_enabled", None, None),
        CrawlerRejected(503, "unavailable", None, None),
    ],
)
def test_the_lock_is_not_read_for_a_rejection_other_than_a_lock_conflict(
    client: TestClient,
    crawler: FakeCrawlerClient,
    readers: InMemoryReaders,
    rejection: CrawlerRejected,
) -> None:
    crawler.behavior.inject("start_crawl", rejection)

    client.post(f"{SOURCES}/docs/crawl-jobs")

    assert readers.behavior.calls == []


def test_a_lock_conflict_whose_existing_job_cannot_be_read_is_a_crawler_error(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    crawler.behavior.inject(
        "start_crawl", CrawlerRejected(409, "lock_held", {"existing_job": {"job_id": 1}}, None)
    )

    response = client.post(f"{SOURCES}/docs/crawl-jobs")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "crawler_error"


# --- 成功の本文が読めない(契約外) ---


@pytest.mark.parametrize(
    "broken_body",
    [
        {},
        crawler_accepted_body(force_delete=...),
        crawler_accepted_body(rewrite_mode="false"),
        crawler_accepted_body(job_type="other"),
        crawler_accepted_body(queued_at="never"),
    ],
)
def test_an_accepted_crawl_that_cannot_be_read_is_a_crawler_error(
    client: TestClient, crawler: FakeCrawlerClient, broken_body: dict[str, Any]
) -> None:
    crawler.behavior.inject("start_crawl", CrawlerSucceeded(202, broken_body))

    response = client.post(f"{SOURCES}/docs/crawl-jobs")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "crawler_error"


@pytest.mark.parametrize(
    ("operation", "method", "path", "broken_body", "status"),
    [
        ("cancel_job", "post", "/jobs/job-1/cancel", {"job_id": "job-1"}, 200),
        ("cancel_job", "post", "/jobs/job-1/cancel", {"job_id": "j", "status": "paused"}, 202),
        ("release_lock", "delete", "/sources/docs/lock", {"source_id": "docs"}, 200),
        (
            "release_lock",
            "delete",
            "/sources/docs/lock",
            {"source_id": "docs", "released": "yes", "failed_job_id": None},
            200,
        ),
        (
            "release_lock",
            "delete",
            "/sources/docs/lock",
            {"source_id": "docs", "released": True, "failed_job_id": 5},
            200,
        ),
        (
            "release_lock",
            "delete",
            "/sources/docs/lock",
            {"source_id": "docs", "released": True},
            200,
        ),
    ],
)
def test_a_cancel_or_release_result_that_cannot_be_read_is_a_crawler_error(
    client: TestClient,
    crawler: FakeCrawlerClient,
    operation: str,
    method: str,
    path: str,
    broken_body: dict[str, Any],
    status: int,
) -> None:
    crawler.behavior.inject(operation, CrawlerSucceeded(status, broken_body))

    response = getattr(client, method)(f"{ADMIN_PREFIX}{path}")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "crawler_error"


# --- 入力値・秘密を出さない(C 11章 12) ---


def test_ids_and_input_values_are_in_neither_the_responses_nor_the_logs(
    client: TestClient, crawler: FakeCrawlerClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    crawler.behavior.inject("cancel_job", CrawlerRejected(404, "job_not_found", None, None))
    crawler.behavior.inject("start_crawl", lock_conflict())

    responses = [
        client.post(f"{SOURCES}/{SENTINEL}!/crawl-jobs"),  # 不正な source_id
        client.post(f"{SOURCES}/docs/crawl-jobs", json={"force_delete": SENTINEL}),
        client.post(f"{SOURCES}/docs/crawl-jobs", content=SENTINEL.encode(), headers=JSON_HEADERS),
        client.post(f"{JOBS}/{SENTINEL}%00/cancel"),  # 不正な job_id(制御文字)
        client.post(f"{JOBS}/{SENTINEL}/cancel"),  # 有効な job_id(Crawler が 404 を返す)
        client.delete(f"{SOURCES}/{SENTINEL}!/lock"),
    ]

    assert [response.status_code for response in responses] == [400, 400, 400, 400, 404, 400]
    assert_secret_absent(
        SENTINEL,
        response_text="".join(response.text for response in responses),
        records=caplog.records,
    )
