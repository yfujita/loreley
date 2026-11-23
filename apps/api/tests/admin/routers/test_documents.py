"""EP-11 `GET /sources/{source_id}/documents`(アプリ全体。C 11章 6・7・12)。"""

import logging
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from loreley_api.common.results import Failed
from loreley_api.common.timestamps import format_instant
from tests.admin.factories import ADMIN_PREFIX
from tests.fakes.clock import DEFAULT_NOW as NOW
from tests.fakes.in_memory_readers import STORE_UNAVAILABLE, InMemoryReaders
from tests.secret_assertions import assert_secret_absent

DOCUMENTS = f"{ADMIN_PREFIX}/sources/docs/documents"
SENTINEL = "SENTINEL-INPUT-VALUE"
SEARCH_UNAVAILABLE = Failed(
    kind="unavailable", target="search_index", error_class_name="ConnectionError"
)


def at(seconds_from_now: float) -> str:
    return format_instant(NOW + timedelta(seconds=seconds_from_now))


@pytest.fixture(autouse=True)
def source(readers: InMemoryReaders) -> None:
    readers.put_source("docs")


def errors_of(response: Any) -> list[dict[str, str]]:
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    return error["details"]["errors"]


def seed_skips(readers: InMemoryReaders, count: int) -> None:
    for number in range(count):
        readers.put_skip(
            "docs",
            f"doc-{number:03d}",
            external_id=f"f{number}.pdf",
            stage="fetch",
            reason="fetch_permission_denied: 取得の権限がなかった",
            attempts=1,
            consecutive_skips=1,
            first_skipped_at=at(-1000),
            last_skipped_at=at(-number),
            last_job_id="job-1",
        )


# --- 形 ---


def test_the_skipped_tab_has_the_documented_shape_and_headers(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_skips(readers, 1)
    readers.put_document("doc-000", source_id="docs", index_status="indexed")
    readers.put_document("doc-x", source_id="docs", index_status="extract_failed")
    readers.refresh_search()

    response = client.get(DOCUMENTS, params={"tab": "skipped"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "tab": "skipped",
        "items": [
            {
                "document_id": "doc-000",
                "external_id": "f0.pdf",
                "stage": "fetch",
                "reason": "fetch_permission_denied: 取得の権限がなかった",
                "attempts": 1,
                "consecutive_skips": 1,
                "first_skipped_at": at(-1000),
                "last_skipped_at": at(0),
                "last_job_id": "job-1",
                "existence": "existing",
                "unavailable": {},
            }
        ],
        "total": 1,
        "page": 1,
        "items_per_page": 25,
        "window_limit": 10_000,
        "tab_counts": {"skipped": 1, "extract_failed": 1, "oversize": 0, "summary_pending": 0},
        "document_count": 2,
        "unavailable": {},
    }


@pytest.mark.parametrize(
    ("tab", "expected_keys"),
    [
        (
            "extract_failed",
            [
                "document_id",
                "title",
                "external_id",
                "mime_type",
                "size",
                "source_updated_at",
                "last_seen_at",
                "unavailable",
            ],
        ),
        (
            "oversize",
            [
                "document_id",
                "external_id",
                "detected_by",
                "size",
                "first_detected_at",
                "last_detected_at",
                "last_job_id",
                "unavailable",
            ],
        ),
        (
            "summary_pending",
            [
                "document_id",
                "title",
                "external_id",
                "mime_type",
                "source_updated_at",
                "indexed_at",
                "unavailable",
            ],
        ),
    ],
)
def test_every_tab_row_has_its_own_fields_and_an_empty_row_unavailable(
    readers: InMemoryReaders, client: TestClient, tab: str, expected_keys: list[str]
) -> None:
    readers.put_document(
        "doc-1", source_id="docs", index_status="extract_failed", summary_status="pending"
    )
    readers.put_oversize("docs", "doc-2", detected_by="crawler")
    readers.refresh_search()

    body = client.get(DOCUMENTS, params={"tab": tab}).json()

    [row] = body["items"]
    assert list(row) == expected_keys
    assert row["unavailable"] == {}
    assert body["tab"] == tab


def test_the_rows_of_a_tab_keep_the_fields_of_their_own_type(
    readers: InMemoryReaders, client: TestClient
) -> None:
    """行の型はタブごとに違う。ほかのタブの項目(`existence` など)が混ざらない。"""
    readers.put_document("d", source_id="docs", index_status="extract_failed", title="タイトル")
    readers.refresh_search()

    [row] = client.get(DOCUMENTS, params={"tab": "extract_failed"}).json()["items"]

    assert row["title"] == "タイトル"
    assert "existence" not in row


# --- ページング・並び(C 11章 7) ---


def test_the_default_order_is_newest_first_and_sort_can_reverse_it(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_skips(readers, 3)
    readers.refresh_search()

    def ids(**params: str) -> list[str]:
        body = client.get(DOCUMENTS, params={"tab": "skipped", **params}).json()
        return [row["document_id"] for row in body["items"]]

    assert ids() == ["doc-000", "doc-001", "doc-002"]
    assert ids(sort="-last_skipped_at") == ["doc-000", "doc-001", "doc-002"]
    assert ids(sort="last_skipped_at") == ["doc-002", "doc-001", "doc-000"]


@pytest.mark.parametrize(
    ("tab", "sort_field"),
    [
        ("skipped", "last_skipped_at"),
        ("extract_failed", "last_seen_at"),
        ("oversize", "last_detected_at"),
        ("summary_pending", "indexed_at"),
    ],
)
def test_each_tab_sorts_by_its_own_single_field(
    client: TestClient, tab: str, sort_field: str
) -> None:
    assert client.get(DOCUMENTS, params={"tab": tab, "sort": sort_field}).status_code == 200
    assert client.get(DOCUMENTS, params={"tab": tab, "sort": f"-{sort_field}"}).status_code == 200
    others = {"last_skipped_at", "last_seen_at", "last_detected_at", "indexed_at"} - {sort_field}
    for other in sorted(others):
        response = client.get(DOCUMENTS, params={"tab": tab, "sort": other})
        assert errors_of(response) == [{"field": "sort", "reason": "unsupported"}]


def test_the_page_and_the_page_size_choose_the_window(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_skips(readers, 60)
    readers.refresh_search()

    body = client.get(DOCUMENTS, params={"tab": "skipped", "page": 2, "items_per_page": 25}).json()

    assert [row["document_id"] for row in body["items"]][:2] == ["doc-025", "doc-026"]
    assert (body["total"], body["page"], body["items_per_page"]) == (60, 2, 25)
    assert len(body["items"]) == 25


@pytest.mark.parametrize("items_per_page", [25, 50, 100])
def test_the_window_boundary_is_accepted_at_exactly_10000(
    client: TestClient, items_per_page: int
) -> None:
    last_page = 10_000 // items_per_page

    response = client.get(
        DOCUMENTS, params={"tab": "skipped", "page": last_page, "items_per_page": items_per_page}
    )

    assert response.status_code == 200
    assert response.json()["page"] == last_page


@pytest.mark.parametrize("items_per_page", [25, 50, 100])
def test_a_page_beyond_the_window_is_a_400_range_on_page(
    client: TestClient, items_per_page: int
) -> None:
    first_page_over = 10_000 // items_per_page + 1

    response = client.get(
        DOCUMENTS,
        params={"tab": "skipped", "page": first_page_over, "items_per_page": items_per_page},
    )

    assert errors_of(response) == [{"field": "page", "reason": "range"}]


def test_the_total_is_exact_beyond_the_window(readers: InMemoryReaders, client: TestClient) -> None:
    for number in range(10_030):
        readers.put_skip("docs", f"doc-{number:05d}", last_skipped_at=at(-number))
    readers.refresh_search()

    body = client.get(DOCUMENTS, params={"tab": "skipped", "page": 400}).json()

    assert body["total"] == 10_030
    assert body["tab_counts"]["skipped"] == 10_030
    assert body["window_limit"] == 10_000
    assert len(body["items"]) == 25


# --- 入力の検証 ---


def test_a_missing_tab_is_a_required_error(client: TestClient) -> None:
    assert errors_of(client.get(DOCUMENTS)) == [{"field": "tab", "reason": "required"}]


@pytest.mark.parametrize("tab", ["", "unknown", "SKIPPED", "skipped,oversize", "extract-failed"])
def test_an_unsupported_tab_is_an_unsupported_error(client: TestClient, tab: str) -> None:
    response = client.get(DOCUMENTS, params={"tab": tab})

    assert errors_of(response) == [{"field": "tab", "reason": "unsupported"}]


@pytest.mark.parametrize(
    ("params", "field", "reason"),
    [
        ({"page": "0"}, "page", "range"),
        ({"page": "-1"}, "page", "range"),
        ({"page": "abc"}, "page", "type"),
        ({"items_per_page": "10"}, "items_per_page", "unsupported"),
        ({"items_per_page": "abc"}, "items_per_page", "type"),
        ({"sort": "title"}, "sort", "unsupported"),
        ({"sort": "-"}, "sort", "unsupported"),
        ({"sort": ""}, "sort", "unsupported"),
        ({"sort": "last_skipped_at,document_id"}, "sort", "unsupported"),
        ({"unknown": "1"}, "unknown", "unknown_field"),
    ],
)
def test_an_invalid_query_is_a_400_with_the_field_and_the_reason(
    client: TestClient, params: dict[str, str], field: str, reason: str
) -> None:
    response = client.get(DOCUMENTS, params={"tab": "skipped", **params})

    assert errors_of(response) == [{"field": field, "reason": reason}]


def test_tab_and_sort_violations_are_reported_together(client: TestClient) -> None:
    response = client.get(DOCUMENTS, params={"tab": "weird", "sort": "bogus", "items_per_page": 7})

    assert errors_of(response) == [
        {"field": "tab", "reason": "unsupported"},
        {"field": "items_per_page", "reason": "unsupported"},
        {"field": "sort", "reason": "unsupported"},
    ]


def test_a_missing_tab_does_not_hide_a_page_violation(client: TestClient) -> None:
    response = client.get(DOCUMENTS, params={"items_per_page": 7})

    assert errors_of(response) == [
        {"field": "tab", "reason": "required"},
        {"field": "items_per_page", "reason": "unsupported"},
    ]


def test_the_path_is_validated_before_the_query(client: TestClient) -> None:
    response = client.get(f"{ADMIN_PREFIX}/sources/-bad/documents", params={"unknown": "1"})

    assert errors_of(response) == [{"field": "source_id", "reason": "format"}]


def test_an_unknown_query_is_reported_before_the_values_of_the_known_ones(
    client: TestClient,
) -> None:
    response = client.get(DOCUMENTS, params={"unknown": "1", "tab": "weird"})

    assert errors_of(response) == [{"field": "unknown", "reason": "unknown_field"}]


def test_an_invalid_source_id_is_a_400_format_error(client: TestClient) -> None:
    response = client.get(f"{ADMIN_PREFIX}/sources/a%20b/documents", params={"tab": "skipped"})

    assert errors_of(response) == [{"field": "source_id", "reason": "format"}]


def test_an_invalid_value_is_never_echoed_in_the_response_or_the_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    response = client.get(DOCUMENTS, params={"tab": SENTINEL, "sort": SENTINEL, "page": SENTINEL})

    assert response.status_code == 400
    assert_secret_absent(SENTINEL, response_text=response.text, records=caplog.records)


def test_the_documents_accept_only_get(client: TestClient) -> None:
    for method in (client.post, client.put, client.delete):
        assert method(DOCUMENTS).status_code == 405


# --- 404・503・部分失敗 ---


def test_a_missing_source_is_a_404_source_config_not_found(client: TestClient) -> None:
    response = client.get(
        f"{ADMIN_PREFIX}/sources/never-registered/documents", params={"tab": "skipped"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "source_config_not_found"


def test_a_source_being_deleted_still_returns_200(
    readers: InMemoryReaders, client: TestClient
) -> None:
    readers.put_source("going", status="deleting")

    response = client.get(f"{ADMIN_PREFIX}/sources/going/documents", params={"tab": "skipped"})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "operation",
    ["sources.get", "jobs.list_skipped"],
)
def test_a_failed_main_read_is_a_503_not_a_404(
    readers: InMemoryReaders, client: TestClient, operation: str
) -> None:
    readers.behavior.inject(operation, STORE_UNAVAILABLE)

    response = client.get(DOCUMENTS, params={"tab": "skipped"})

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "unavailable",
            "message": "the data store is unavailable",
            "retryable": True,
        }
    }


def test_the_documented_partial_failure_example(
    readers: InMemoryReaders, client: TestClient
) -> None:
    """B 6.1 の例: 検索インデックスの `summary_pending` の件数だけが取れない。"""
    seed_skips(readers, 1)
    readers.put_document("doc-000", source_id="docs", index_status="indexed")
    readers.fail_document("counts.count_for_source", "summary_pending", SEARCH_UNAVAILABLE)
    readers.refresh_search()

    body = client.get(DOCUMENTS, params={"tab": "skipped"}).json()

    assert body["tab_counts"]["summary_pending"] is None
    assert body["unavailable"] == {"tab_counts.summary_pending": "search_index_unavailable"}
    assert body["items"][0]["unavailable"] == {}


def test_a_failed_existence_lookup_is_on_every_row_and_not_at_the_top(
    readers: InMemoryReaders, client: TestClient
) -> None:
    seed_skips(readers, 3)
    readers.behavior.inject("search_index.existing_ids", SEARCH_UNAVAILABLE)
    readers.refresh_search()

    body = client.get(DOCUMENTS, params={"tab": "skipped"}).json()

    assert [row["existence"] for row in body["items"]] == ["unknown"] * 3
    assert [row["unavailable"] for row in body["items"]] == [
        {"existence": "search_index_unavailable"}
    ] * 3
    assert body["unavailable"] == {}
    assert body["total"] == 3
