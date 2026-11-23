"""EP-03 `POST /sources`・EP-04 `PUT /sources/{source_id}`・EP-05 `POST …/delete-jobs`(アプリ全体)。

Crawler は `FakeCrawlerClient`(HTTP を通した確認は `test_write_eps_over_http.py`)。
C 11章 1(EP 経由)・4・12。入力の検証の順序(A 5.3)と、違反した要求を送らないことも確かめる。
"""

import json
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from loreley_api.infrastructure.crawler_client import (
    ConfigInvalidMessage,
    ConfigViolation,
    CrawlerRejected,
    CrawlerSourceSettings,
    CrawlerSucceeded,
)
from tests.admin.factories import ADMIN_PREFIX, SENTINEL, errors_of
from tests.admin.write_requests import (
    crawler_accepted_body,
    crawler_source_body,
    register_body,
    update_body,
)
from tests.fakes.fake_crawler_client import FakeCrawlerClient
from tests.fakes.in_memory_readers import InMemoryReaders
from tests.secret_assertions import assert_secret_absent

SOURCES = f"{ADMIN_PREFIX}/sources"
JSON_HEADERS = {"Content-Type": "application/json"}


def post_register(client: TestClient, body: Any) -> Any:
    return client.post(SOURCES, json=body)


def put_update(client: TestClient, body: Any, source_id: str = "docs-share") -> Any:
    return client.put(f"{SOURCES}/{source_id}", json=body)


def send_valid_write(client: TestClient, operation: str) -> Any:
    """`operation`(`register_source`・`update_source`)の EP に、有効な本文を送る。"""
    if operation == "register_source":
        return post_register(client, register_body())
    return put_update(client, update_body())


# --- EP-03: 成功 ---


def test_a_registration_is_relayed_in_the_crawler_units_and_returns_the_saved_settings(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    response = post_register(client, register_body())

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    # B 3.3 の「Crawler への送信」: ttl は秒、しきい値は 0〜1 の割合。
    [request] = crawler.requests
    assert request.operation == "register_source"
    assert request.arguments == {
        "source_id": "docs-share",
        "connector_type": "file_system",
        "settings": CrawlerSourceSettings(
            connector_config=register_body()["connector_config"],
            ttl_seconds=30 * 86_400,
            ratio_threshold=0.2,
            min_delete_count=10,
            schedule_cron="0 3 * * *",
        ),
    }
    # 応答は、Crawler が返した保存内容を、応答の単位(日・%)に戻したもの。
    assert response.json() == {
        "source_id": "docs-share",
        "connector_type": "file_system",
        "connector_config": register_body()["connector_config"],
        "ttl_seconds": 2_592_000,
        "ttl_days": 30,
        "ratio_threshold_percent": 20,
        "min_delete_count": 10,
        "schedule_cron": "0 3 * * *",
        "status": "active",
        "updated_at": "2026-11-24T00:00:00.000Z",
    }


def test_the_response_of_a_registration_is_strict_and_has_no_nullable_status_fields(
    client: TestClient,
) -> None:
    """EP-03・04 の応答は Crawler の応答由来なので、`connector_type`・`status`・`updated_at` は
    `null` にならない(EP-02 の保存値の読み取りとは違う)。
    """
    body = post_register(client, register_body()).json()

    assert body["connector_type"] == "file_system"
    assert body["status"] == "active"
    assert body["updated_at"] == "2026-11-24T00:00:00.000Z"


def test_an_idempotent_registration_keeps_the_200_of_the_crawler(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    crawler.behavior.inject("register_source", CrawlerSucceeded(200, crawler_source_body()))

    response = post_register(client, register_body())

    assert response.status_code == 200
    assert response.json()["source_id"] == "docs-share"


def test_the_ttl_in_seconds_is_sent_as_it_is_and_a_stored_ttl_that_is_not_whole_days_has_no_days(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    crawler.behavior.inject(
        "register_source", CrawlerSucceeded(201, crawler_source_body(ttl=90_001))
    )

    response = post_register(client, register_body(ttl_days=..., ttl_seconds=90_001))

    assert crawler.requests[0].arguments["settings"].ttl_seconds == 90_001
    assert response.json()["ttl_seconds"] == 90_001
    assert response.json()["ttl_days"] is None


def test_a_ratio_with_two_decimals_is_converted_exactly(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    crawler.behavior.inject(
        "register_source", CrawlerSucceeded(201, crawler_source_body(ratio_threshold=0.29))
    )

    response = post_register(client, register_body(ratio_threshold_percent=0.29))

    # 画面が打ち込んだ `0.29`(%)は 0.0029(割合)になり、応答の保存値 0.29 は 29(%)に戻る。
    assert crawler.requests[0].arguments["settings"].ratio_threshold == 0.0029
    assert response.json()["ratio_threshold_percent"] == 29


def test_a_schedule_cron_that_is_omitted_or_null_is_sent_as_null(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    post_register(client, register_body(schedule_cron=...))
    post_register(client, register_body(schedule_cron=None))

    assert [r.arguments["settings"].schedule_cron for r in crawler.requests] == [None, None]


def test_the_connector_config_and_connector_type_are_relayed_without_inspection(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    config = {"anything": [1, {"nested": None}], "root": ""}

    response = post_register(
        client, register_body(connector_type="not-a-type", connector_config=config)
    )

    assert response.status_code == 201
    assert crawler.requests[0].arguments["connector_type"] == "not-a-type"
    assert crawler.requests[0].arguments["settings"].connector_config == config


def test_the_largest_values_that_fit_in_int64_are_accepted(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    int64_max = 2**63 - 1
    largest_days = int64_max // 86_400

    response = post_register(
        client, register_body(ttl_days=largest_days, min_delete_count=int64_max)
    )

    assert response.status_code == 201
    settings = crawler.requests[0].arguments["settings"]
    assert settings.ttl_seconds == largest_days * 86_400
    assert settings.min_delete_count == int64_max


# --- 検証(EP-03・04 に共通): 違反は Crawler に送らない ---

# (本文の変更, 期待する違反の一覧)。違反は項目名と理由だけ。
VALUE_VIOLATIONS: list[tuple[dict[str, Any], list[tuple[str, str]]]] = [
    ({"ttl_days": ..., "ttl_seconds": ...}, [("ttl_days", "required")]),
    ({"ttl_seconds": 86_400}, [("ttl_days", "exclusive")]),
    ({"ttl_days": 0}, [("ttl_days", "range")]),
    ({"ttl_days": -1}, [("ttl_days", "range")]),
    ({"ttl_days": 2**63 // 86_400 + 1}, [("ttl_days", "range")]),
    ({"ttl_days": 10**30}, [("ttl_days", "range")]),
    ({"ttl_days": ..., "ttl_seconds": 0}, [("ttl_seconds", "range")]),
    ({"ttl_days": ..., "ttl_seconds": 2**63}, [("ttl_seconds", "range")]),
    ({"ratio_threshold_percent": -0.01}, [("ratio_threshold_percent", "range")]),
    ({"ratio_threshold_percent": 100}, [("ratio_threshold_percent", "range")]),
    ({"ratio_threshold_percent": 12.345}, [("ratio_threshold_percent", "format")]),
    ({"ratio_threshold_percent": 0.001}, [("ratio_threshold_percent", "format")]),
    ({"min_delete_count": -1}, [("min_delete_count", "range")]),
    ({"min_delete_count": 2**63}, [("min_delete_count", "range")]),
    # すべての違反を返す(B 3.3 の例: しきい値の範囲と TTL の排他)。
    (
        {"ratio_threshold_percent": 100, "ttl_seconds": 1},
        [("ttl_days", "exclusive"), ("ratio_threshold_percent", "range")],
    ),
    (
        {"ttl_days": 0, "ratio_threshold_percent": -1, "min_delete_count": -1},
        [
            ("ttl_days", "range"),
            ("ratio_threshold_percent", "range"),
            ("min_delete_count", "range"),
        ],
    ),
]

TYPE_VIOLATIONS: list[tuple[dict[str, Any], list[tuple[str, str]]]] = [
    ({"ttl_days": "30"}, [("ttl_days", "type")]),
    ({"ttl_days": 30.0}, [("ttl_days", "type")]),
    ({"ttl_days": True}, [("ttl_days", "type")]),
    ({"ttl_days": None}, [("ttl_days", "type")]),
    ({"ttl_days": ..., "ttl_seconds": "1"}, [("ttl_seconds", "type")]),
    ({"ttl_days": ..., "ttl_seconds": 1.5}, [("ttl_seconds", "type")]),
    ({"ratio_threshold_percent": "20"}, [("ratio_threshold_percent", "type")]),
    ({"ratio_threshold_percent": True}, [("ratio_threshold_percent", "type")]),
    ({"ratio_threshold_percent": None}, [("ratio_threshold_percent", "type")]),
    ({"min_delete_count": "1"}, [("min_delete_count", "type")]),
    ({"min_delete_count": 1.0}, [("min_delete_count", "type")]),
    ({"min_delete_count": False}, [("min_delete_count", "type")]),
    ({"connector_config": []}, [("connector_config", "type")]),
    ({"connector_config": "root"}, [("connector_config", "type")]),
    ({"connector_config": None}, [("connector_config", "type")]),
    ({"schedule_cron": 5}, [("schedule_cron", "type")]),
    ({"schedule_cron": ["0 3 * * *"]}, [("schedule_cron", "type")]),
    ({"unexpected": 1}, [("unexpected", "unknown_field")]),
    # 形の違反があれば、値の範囲は見ない(形 → 範囲の順。B 2.12)。
    ({"ttl_days": "30", "min_delete_count": -1}, [("ttl_days", "type")]),
    (
        {"ratio_threshold_percent": "1", "unexpected": 1},
        [("ratio_threshold_percent", "type"), ("unexpected", "unknown_field")],
    ),
]

REQUIRED_FIELDS = ["connector_config", "ratio_threshold_percent", "min_delete_count"]


def violations_of(response: Any) -> list[tuple[str, str]]:
    return [(error["field"], error["reason"]) for error in errors_of(response)]


@pytest.mark.parametrize(("change", "expected"), VALUE_VIOLATIONS + TYPE_VIOLATIONS)
def test_a_registration_with_an_invalid_body_is_rejected_and_not_sent(
    client: TestClient,
    crawler: FakeCrawlerClient,
    change: dict[str, Any],
    expected: list[tuple[str, str]],
) -> None:
    response = post_register(client, register_body(**change))

    assert sorted(violations_of(response)) == sorted(expected)
    assert crawler.requests == []


@pytest.mark.parametrize(("change", "expected"), VALUE_VIOLATIONS + TYPE_VIOLATIONS)
def test_an_update_with_an_invalid_body_is_rejected_and_not_sent(
    client: TestClient,
    crawler: FakeCrawlerClient,
    change: dict[str, Any],
    expected: list[tuple[str, str]],
) -> None:
    response = put_update(client, update_body(**change))

    assert sorted(violations_of(response)) == sorted(expected)
    assert crawler.requests == []


@pytest.mark.parametrize("name", [*REQUIRED_FIELDS, "source_id", "connector_type"])
def test_a_registration_without_a_required_field_is_rejected(
    client: TestClient, crawler: FakeCrawlerClient, name: str
) -> None:
    response = post_register(client, register_body(**{name: ...}))

    assert violations_of(response) == [(name, "required")]
    assert crawler.requests == []


@pytest.mark.parametrize("name", REQUIRED_FIELDS)
def test_an_update_without_a_required_field_is_rejected(
    client: TestClient, crawler: FakeCrawlerClient, name: str
) -> None:
    """全置換なので、必須の項目を省略できない(B 3.4)。"""
    response = put_update(client, update_body(**{name: ...}))

    assert violations_of(response) == [(name, "required")]
    assert crawler.requests == []


@pytest.mark.parametrize(
    "source_id",
    ["", "-a", ".a", "a b", "a/b", "あ", "a" * 257, "docs\n", "a?b", "a%2Fb", 5, None],
)
def test_a_registration_with_an_invalid_source_id_is_rejected(
    client: TestClient, crawler: FakeCrawlerClient, source_id: object
) -> None:
    response = post_register(client, register_body(source_id=source_id))

    [(field, reason)] = violations_of(response)
    assert field == "source_id"
    assert reason == ("type" if not isinstance(source_id, str) else "format")
    assert crawler.requests == []


def test_a_source_id_of_256_characters_is_accepted(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    long_id = "a" + "b" * 255

    response = post_register(client, register_body(source_id=long_id))

    assert response.status_code == 201
    assert crawler.requests[0].arguments["source_id"] == long_id


def test_the_source_id_and_connector_type_are_not_accepted_in_an_update_body(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    body = {**update_body(), "source_id": "docs-share", "connector_type": "file_system"}

    response = put_update(client, body)

    assert sorted(violations_of(response)) == [
        ("connector_type", "unknown_field"),
        ("source_id", "unknown_field"),
    ]
    assert crawler.requests == []


# --- 本文の形式(EP-03・04・06 で共通の規約。EP 経由の確認) ---


def test_a_body_that_is_not_an_object_is_a_type_error_of_the_body(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    response = post_register(client, [1, 2])

    assert violations_of(response) == [("body", "type")]
    assert crawler.requests == []


@pytest.mark.parametrize(
    ("content", "headers"),
    [
        (b"{not json", JSON_HEADERS),
        (b'{"source_id": NaN}', JSON_HEADERS),
        (b'{"source_id": Infinity}', JSON_HEADERS),
        (b"\xff\xfe", JSON_HEADERS),
        (json.dumps(register_body()).encode(), {"Content-Type": "text/plain"}),
        (json.dumps(register_body()).encode(), {}),
        (b"x" * (1024 * 1024 + 1), JSON_HEADERS),
    ],
    ids=["broken", "nan", "infinity", "not-utf8", "text-plain", "no-content-type", "over-1mib"],
)
def test_an_unreadable_body_is_a_400_without_details_and_is_not_sent(
    client: TestClient,
    crawler: FakeCrawlerClient,
    content: bytes,
    headers: dict[str, str],
) -> None:
    response = client.post(SOURCES, content=content, headers=headers)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert "details" not in error
    assert crawler.requests == []


def test_an_empty_body_of_a_registration_is_every_required_field_missing(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    """EP-03・04 では、空の本文は `{}` で、必須の項目の欠落になる(B 2.12)。"""
    response = client.post(SOURCES)

    assert sorted(violations_of(response)) == sorted(
        [(name, "required") for name in ["source_id", "connector_type", *REQUIRED_FIELDS]]
    )
    assert crawler.requests == []


def test_a_non_finite_number_inside_the_connector_config_is_rejected_and_not_sent(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    """`1e999` は JSON の数値だが `inf` に読まれ、Crawler に送れない(送信の前提)。"""
    raw = (
        json.dumps(register_body(connector_config=...))[:-1]
        + ', "connector_config": {"a": [1e999]}}'
    )

    response = client.post(SOURCES, content=raw, headers=JSON_HEADERS)

    assert violations_of(response) == [("connector_config", "type")]
    assert crawler.requests == []


def test_the_ratio_of_infinity_is_a_range_violation(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    raw = (
        json.dumps(register_body(ratio_threshold_percent=...))[:-1]
        + ', "ratio_threshold_percent": 1e999}'
    )

    response = client.post(SOURCES, content=raw, headers=JSON_HEADERS)

    assert violations_of(response) == [("ratio_threshold_percent", "range")]
    assert crawler.requests == []


# --- 検証の順序: パス → クエリ → 本文(A 5.3) ---


def test_the_path_is_validated_before_the_query_and_the_body(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    response = client.put(f"{SOURCES}/-bad?unknown=1", content=b"{not json", headers=JSON_HEADERS)

    assert violations_of(response) == [("source_id", "format")]
    assert crawler.requests == []


@pytest.mark.parametrize("method", ["post", "put"])
def test_the_query_is_validated_before_the_body(
    client: TestClient, crawler: FakeCrawlerClient, method: str
) -> None:
    path = SOURCES if method == "post" else f"{SOURCES}/docs-share"

    response = getattr(client, method)(
        f"{path}?unknown=1", content=b"{not json", headers=JSON_HEADERS
    )

    assert violations_of(response) == [("unknown", "unknown_field")]
    assert crawler.requests == []


# --- EP-04 ---


def test_an_update_is_relayed_to_the_source_of_the_path(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    crawler.behavior.inject(
        "update_source", CrawlerSucceeded(200, crawler_source_body("other", ttl=86_400))
    )

    response = put_update(client, update_body(ttl_days=1, schedule_cron=...), "other")

    assert response.status_code == 200
    [request] = crawler.requests
    assert request.operation == "update_source"
    assert request.arguments["source_id"] == "other"
    # 省略した `schedule_cron` は `null`(手動のみ)に置き換わる(B 3.4)。
    assert request.arguments["settings"].schedule_cron is None
    assert request.arguments["settings"].ttl_seconds == 86_400
    assert response.json()["source_id"] == "other"
    assert response.json()["ttl_days"] == 1


@pytest.mark.parametrize("source_id", ["-bad", "a b", ".x", "a" * 257])
def test_an_update_with_an_invalid_path_id_is_rejected(
    client: TestClient, crawler: FakeCrawlerClient, source_id: str
) -> None:
    response = put_update(client, update_body(), source_id)

    assert violations_of(response) == [("source_id", "format")]
    assert crawler.requests == []


# --- Crawler が返す項目の違反は、送った TTL の項目名で返す(B 2.6) ---


@pytest.mark.parametrize(
    ("ttl_change", "expected_field"),
    [({}, "ttl_days"), ({"ttl_days": ..., "ttl_seconds": 100}, "ttl_seconds")],
)
def test_a_ttl_violation_of_the_crawler_is_named_after_the_ttl_field_that_was_sent(
    client: TestClient,
    crawler: FakeCrawlerClient,
    ttl_change: dict[str, Any],
    expected_field: str,
) -> None:
    crawler.behavior.inject(
        "register_source",
        CrawlerRejected(
            400,
            "invalid_request",
            {"errors": [{"field": "ttl", "reason": "range"}]},
            None,
        ),
    )

    response = post_register(client, register_body(**ttl_change))

    assert violations_of(response) == [(expected_field, "range")]


# --- config_invalid の分解(C 11章 4。EP 経由) ---


@pytest.mark.parametrize("operation", ["register_source", "update_source"])
def test_a_config_invalid_of_the_crawler_is_decomposed_with_the_crawler_message(
    client: TestClient, crawler: FakeCrawlerClient, operation: str
) -> None:
    message = "include_patterns[2]: `\\` を含む(エスケープはない)"
    crawler.behavior.inject(
        operation,
        CrawlerRejected(
            400,
            "config_invalid",
            None,
            ConfigInvalidMessage(
                message,
                ConfigViolation(
                    "connector_config.include_patterns[2]", "`\\` を含む(エスケープはない)"
                ),
            ),
        ),
    )

    response = send_valid_write(client, operation)

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "config_invalid",
            "message": "connector_config is invalid",
            "retryable": False,
            "details": {
                "errors": [
                    {
                        "field": "connector_config.include_patterns[2]",
                        "reason": "config_invalid",
                        "detail": "`\\` を含む(エスケープはない)",
                    }
                ],
                "crawler_message": message,
            },
        }
    }


def test_a_config_invalid_that_cannot_be_decomposed_has_no_errors_but_the_crawler_message(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    crawler.behavior.inject(
        "register_source",
        CrawlerRejected(400, "config_invalid", None, ConfigInvalidMessage("something odd", None)),
    )

    response = post_register(client, register_body())

    assert response.json()["error"]["details"] == {
        "errors": [],
        "crawler_message": "something odd",
    }


# --- EP-05 ---


def test_a_delete_job_is_started_for_the_source_of_the_path_without_options(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    crawler.behavior.inject(
        "start_delete_job",
        CrawlerSucceeded(
            202,
            crawler_accepted_body("source_delete", with_options=False, source_id="docs-share"),
        ),
    )

    response = client.post(f"{SOURCES}/docs-share/delete-jobs")

    assert response.status_code == 202
    assert response.json() == {
        "job_id": "job-20261124T010203Z-3fa9c2d1",
        "job_type": "source_delete",
        "source_id": "docs-share",
        "status": "queued",
        "trigger": "manual",
        "force_delete": None,
        "rewrite_mode": None,
        "queued_at": "2026-11-24T01:02:03.456Z",
    }
    # 削除ジョブを起動する 1 回だけで、クロールの起動などは呼ばれない。
    assert [(r.operation, r.arguments) for r in crawler.requests] == [
        ("start_delete_job", {"source_id": "docs-share"})
    ]


def test_a_delete_job_ignores_the_body_even_when_it_is_not_json(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    response = client.post(
        f"{SOURCES}/docs/delete-jobs",
        content=b"{not json",
        headers={"Content-Type": "text/plain"},
    )

    assert response.status_code == 202
    assert len(crawler.requests) == 1


def test_a_delete_job_with_an_invalid_id_or_a_query_is_rejected_and_not_sent(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    bad_id = client.post(f"{SOURCES}/-bad/delete-jobs")
    bad_query = client.post(f"{SOURCES}/docs/delete-jobs?force=1")

    assert violations_of(bad_id) == [("source_id", "format")]
    assert violations_of(bad_query) == [("force", "unknown_field")]
    assert crawler.requests == []


def test_a_delete_job_never_sends_force_delete_or_rewrite_mode(
    client: TestClient, crawler: FakeCrawlerClient
) -> None:
    """EP-05 は指定を持たない(データ削除に関わるので、他の EP の指定が混ざらないことを固定する)。"""
    client.post(f"{SOURCES}/docs/delete-jobs", json={"force_delete": True, "rewrite_mode": True})

    [request] = crawler.requests
    assert request.operation == "start_delete_job"
    assert set(request.arguments) == {"source_id"}


def test_the_lock_conflict_of_a_delete_job_has_no_options_applied_or_requested(
    client: TestClient, crawler: FakeCrawlerClient, readers: InMemoryReaders
) -> None:
    existing_job = {
        "job_id": "job-1",
        "job_type": "source_delete",
        "status": "running",
        "trigger": "manual",
        "lease_expires_at": "2026-11-24T00:01:00.000Z",
    }
    crawler.behavior.inject(
        "start_delete_job",
        CrawlerRejected(409, "lock_held", {"existing_job": existing_job}, None),
    )

    response = client.post(f"{SOURCES}/docs/delete-jobs")

    assert response.status_code == 409
    assert response.json()["error"]["details"] == {
        "existing_job": existing_job,
        "lock_state": "none",
    }


# --- 成功の本文が読めない(契約外) ---


@pytest.mark.parametrize(
    "operation",
    ["register_source", "update_source"],
)
@pytest.mark.parametrize(
    "broken_body",
    [
        {},
        crawler_source_body(status="paused"),
        crawler_source_body(ttl="30"),
        crawler_source_body(ttl=True),
        crawler_source_body(ratio_threshold="0.2"),
        crawler_source_body(min_delete_count=None),
        crawler_source_body(connector_config=[]),
        crawler_source_body(connector_type=None),
        crawler_source_body(updated_at="yesterday"),
        crawler_source_body(source_id=""),
    ],
)
def test_a_saved_settings_that_cannot_be_read_is_a_crawler_error(
    client: TestClient,
    crawler: FakeCrawlerClient,
    operation: str,
    broken_body: dict[str, Any],
) -> None:
    status = 201 if operation == "register_source" else 200
    crawler.behavior.inject(operation, CrawlerSucceeded(status, broken_body))

    response = send_valid_write(client, operation)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "crawler_error"


@pytest.mark.parametrize(
    "broken_body",
    [
        {},
        crawler_accepted_body("source_delete", with_options=False, job_id=...),
        crawler_accepted_body("source_delete", with_options=False, status="done"),
        crawler_accepted_body("source_delete", with_options=False, queued_at=None),
        crawler_accepted_body("source_delete", with_options=False, trigger="auto"),
    ],
)
def test_an_accepted_job_that_cannot_be_read_is_a_crawler_error(
    client: TestClient, crawler: FakeCrawlerClient, broken_body: dict[str, Any]
) -> None:
    crawler.behavior.inject("start_delete_job", CrawlerSucceeded(202, broken_body))

    response = client.post(f"{SOURCES}/docs/delete-jobs")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "crawler_error"


# --- 入力値・秘密を出さない(C 11章 12) ---


def test_input_values_are_in_neither_the_error_body_nor_the_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    responses = [
        post_register(client, register_body(source_id=f"{SENTINEL}/x")),
        post_register(client, register_body(ttl_days=f"{SENTINEL}")),
        post_register(client, register_body(connector_type=[SENTINEL])),
        post_register(client, register_body(schedule_cron=[SENTINEL])),
        put_update(client, update_body(ratio_threshold_percent=f"{SENTINEL}"), "docs"),
        put_update(client, update_body(), f"{SENTINEL}!"),
        client.post(f"{SOURCES}/{SENTINEL}!/delete-jobs"),
        client.post(SOURCES, content=f"{{{SENTINEL}".encode(), headers=JSON_HEADERS),
    ]

    assert all(response.status_code == 400 for response in responses)
    assert_secret_absent(
        SENTINEL,
        response_text="".join(response.text for response in responses),
        records=caplog.records,
    )


def test_the_connector_config_of_a_request_is_in_neither_the_response_nor_the_logs(
    client: TestClient, crawler: FakeCrawlerClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    secret_config = {"root": f"/data/{SENTINEL}", "token": SENTINEL}
    crawler.behavior.inject("register_source", CrawlerRejected(500, "internal_error", None, None))
    crawler.behavior.inject("update_source", CrawlerRejected(503, "unavailable", None, None))

    registered = post_register(client, register_body(connector_config=secret_config))
    updated = put_update(client, update_body(connector_config=secret_config))

    assert (registered.status_code, updated.status_code) == (502, 503)
    assert_secret_absent(
        SENTINEL, response_text=registered.text + updated.text, records=caplog.records
    )
