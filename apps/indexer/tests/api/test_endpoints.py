"""8 つの API の契約(api 1章、3.4、4.1〜4.8)を、HTTP からドメイン(インメモリの fake)まで通す。

テストと設計書の対応は、各テストの名前の後ろの注記(節・ID)。
"""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from loreley_indexer.crawl_runs.lifecycle import DeletionReason, DeletionStatus
from loreley_indexer.documents.document_id import compute_document_id
from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    OpenSearchUnavailableError,
    OpenSearchUnexpectedResponseError,
)
from tests.api.factories import (
    BATCH_PATH,
    DELETE_DOCUMENTS_PATH,
    DELETE_RECORDS_PATH,
    DISCARD_PATH,
    FINISH_PATH,
    LAST_SEEN_PATH,
    START_PATH,
    STATUS_PATH,
    batch_json,
    document_json,
    finish_json,
    last_seen_json,
    lock_json,
    locked_json,
    start_json,
)
from tests.crawl_runs.deletion.scenario import ids, seed_documents
from tests.crawl_runs.factories import (
    CRAWL_ID,
    CRAWL_STARTED_AT,
    MALFORMED_VALUE,
    SOURCE_ID,
    hex_id,
    make_result,
    seed_malformed_result,
    seed_result,
    stored_generation,
    stored_result,
)
from tests.documents.factories import seed_lock
from tests.fakes import in_memory_search_index as index_ops
from tests.fakes import in_memory_store as store_ops
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore
from tests.fakes.waiting import wait_until


def error_of(response: Any) -> dict[str, Any]:
    """共通のエラー形式(api 3.4)の `error`。形も確認する。"""
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "retryable"}
    assert isinstance(body["error"]["message"], str)
    assert isinstance(body["error"]["retryable"], bool)
    return body["error"]


def delete(client: TestClient, path: str, body: dict[str, Any]) -> Any:
    return client.request("DELETE", path, json=body)


@pytest.fixture
def running_crawl(deletions_store: InMemoryStore, jobs_store: InMemoryStore) -> None:
    """開始通知の受理済み(`running`)で、Crawler がロックを持っている。"""
    seed_result(deletions_store, make_result())
    seed_lock(jobs_store)


# --- 開始通知 4.1 ---


def test_start_returns_the_crawl_id_and_running_and_creates_the_result(  # 4.1
    client: TestClient, deletions_store: InMemoryStore
) -> None:
    response = client.post(START_PATH, json=start_json())

    assert response.status_code == 200
    assert response.json() == {"crawl_id": CRAWL_ID, "status": "running"}
    result = stored_result(deletions_store)
    assert (result.status, result.source_id, result.ttl) == (
        DeletionStatus.RUNNING,
        SOURCE_ID,
        86_400,
    )
    assert stored_generation(deletions_store).crawl_id == CRAWL_ID


def test_start_accepts_an_omitted_force_delete_and_rewrite_mode_as_false(  # 4.1、K37
    client: TestClient, deletions_store: InMemoryStore
) -> None:
    body = start_json()
    del body["force_delete"]

    assert client.post(START_PATH, json=body).status_code == 200

    result = stored_result(deletions_store)
    assert (result.forced, result.rewrite_mode) == (False, False)


def test_start_accepts_the_rewrite_mode_and_the_integer_ratio_threshold(  # 4.1、D-94
    client: TestClient, deletions_store: InMemoryStore
) -> None:
    response = client.post(START_PATH, json=start_json(rewrite_mode=True, ratio_threshold=1))

    assert response.status_code == 200
    assert stored_result(deletions_store).rewrite_mode is True


def test_a_resent_start_succeeds_without_changing_the_state(  # 4.1(冪等)
    client: TestClient, deletions_store: InMemoryStore
) -> None:
    client.post(START_PATH, json=start_json())
    before = stored_result(deletions_store)

    response = client.post(START_PATH, json=start_json())

    assert response.status_code == 200
    assert stored_result(deletions_store) == before


def test_a_resent_start_with_different_values_is_a_409_crawl_start_conflict(  # 4.1、K24
    client: TestClient, deletions_store: InMemoryStore
) -> None:
    client.post(START_PATH, json=start_json())

    response = client.post(START_PATH, json=start_json(ttl=1))

    assert response.status_code == 409
    assert error_of(response) == {
        "code": "crawl_start_conflict",
        "message": "the start notification differs from the one already accepted for the crawl",
        "retryable": False,
    }
    assert stored_result(deletions_store).ttl == 86_400


def test_start_for_a_finished_crawl_is_a_409_crawl_already_finished(  # 4.1
    client: TestClient, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result(status=DeletionStatus.DELETED))

    response = client.post(START_PATH, json=start_json())

    assert response.status_code == 409
    assert error_of(response)["code"] == "crawl_already_finished"


def test_start_older_than_the_current_generation_is_a_409_stale_crawl_started_at(  # 4.1
    client: TestClient,
) -> None:
    client.post(START_PATH, json=start_json())

    response = client.post(
        START_PATH, json=start_json(crawl_id="job-older", crawl_started_at="2026-11-08T00:00:00Z")
    )

    assert response.status_code == 409
    assert error_of(response)["code"] == "stale_crawl_started_at"


def test_start_normalizes_timestamps_with_an_offset_to_utc(  # 3.6
    client: TestClient, deletions_store: InMemoryStore
) -> None:
    client.post(START_PATH, json=start_json(crawl_started_at="2026-11-09T10:00:00+09:00"))

    assert stored_result(deletions_store).crawl_started_at == CRAWL_STARTED_AT


# --- バッチ登録 4.3 ---


def test_a_batch_registers_documents_and_returns_per_document_results(  # 4.3、C-1
    client: TestClient, search_index: InMemorySearchIndex, running_crawl: None
) -> None:
    documents = [document_json("docs/a.txt"), document_json("page-10024", text="two")]

    response = client.post(BATCH_PATH, json=batch_json(documents))

    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {
                "external_id": external_id,
                "document_id": compute_document_id(SOURCE_ID, external_id),
                "status": "ok",
                "change": "created",
                "extract_failed": False,
            }
            for external_id in ("docs/a.txt", "page-10024")
        ]
    }
    stored = search_index.source_of(compute_document_id(SOURCE_ID, "docs/a.txt"))
    assert stored is not None
    assert stored["content"] == "hello\nworld\n"
    assert stored["last_seen_at"] == "2026-11-09T01:00:00.000Z"


def test_a_resent_batch_reports_unchanged(  # 4.3(冪等)、C-6
    client: TestClient, running_crawl: None
) -> None:
    client.post(BATCH_PATH, json=batch_json())

    response = client.post(BATCH_PATH, json=batch_json())

    assert [result["change"] for result in response.json()["results"]] == ["unchanged"]


def test_the_response_returns_the_external_id_as_sent(  # 4.3
    client: TestClient, running_crawl: None
) -> None:
    sent = (
        "docs\\sub/e\u0301.txt"  # `\` 区切りと結合文字。ID の算出では正規化されるが、応答は送った値
    )

    response = client.post(BATCH_PATH, json=batch_json([document_json(sent)]))

    [result] = response.json()["results"]
    assert result["external_id"] == sent
    assert result["document_id"] == compute_document_id(SOURCE_ID, sent)


def test_an_unextractable_document_is_ok_with_extract_failed(  # 4.3、K30
    client: TestClient, running_crawl: None
) -> None:
    unknown_type = document_json(mime_type="application/x-unknown")

    response = client.post(BATCH_PATH, json=batch_json([unknown_type]))

    [result] = response.json()["results"]
    assert (result["status"], result["extract_failed"]) == ("ok", True)


def test_fetched_at_metadata_and_unknown_fields_are_ignored(  # 4.3、案 7、K45
    client: TestClient, running_crawl: None, search_index: InMemorySearchIndex
) -> None:
    extra = {"fetched_at": "2026-11-09T01:00:00Z", "metadata": {"k": "v"}, "unknown": 1}
    body = batch_json([document_json(**extra)], future_field=True)

    response = client.post(BATCH_PATH, json=body)

    assert response.status_code == 200
    stored = search_index.source_of(compute_document_id(SOURCE_ID, "docs/a.txt"))
    assert stored is not None
    assert not {"fetched_at", "metadata", "unknown"} & set(stored)


@pytest.mark.parametrize(
    ("setup", "code"),
    [
        ("no_result", "crawl_not_started"),
        ("other_source", "crawl_source_mismatch"),
        ("other_started_at", "crawl_started_at_mismatch"),
        ("terminal", "crawl_already_closed"),
        ("finish_received", "crawl_finished"),
    ],
)
def test_a_batch_rejected_by_the_admission_rules_is_a_409_and_writes_nothing(  # 3.2、D-77〜82
    client: TestClient,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    setup: str,
    code: str,
) -> None:
    seed_lock(jobs_store)
    overrides: dict[str, Any] = {
        "no_result": None,
        "other_source": {"source_id": "another"},
        "other_started_at": {"crawl_started_at": CRAWL_STARTED_AT + timedelta(hours=1)},
        "terminal": {"status": DeletionStatus.DISCARDED},
        "finish_received": {"finish_received_at": CRAWL_STARTED_AT + timedelta(hours=1)},
    }
    if overrides[setup] is not None:
        seed_result(deletions_store, make_result(**overrides[setup]))

    response = client.post(BATCH_PATH, json=batch_json())

    assert response.status_code == 409
    assert error_of(response)["code"] == code
    assert error_of(response)["retryable"] is False
    assert search_index.write_calls() == []


def test_a_batch_whose_lock_is_not_owned_returns_lock_not_owned_per_document(  # 3.4、API-U-13
    client: TestClient, search_index: InMemorySearchIndex, running_crawl: None
) -> None:
    response = client.post(BATCH_PATH, json=batch_json(lock=lock_json(owner="someone-else")))

    assert response.status_code == 200
    [result] = response.json()["results"]
    assert (result["status"], result["failure_type"]) == ("failed", "lock_not_owned")
    assert search_index.write_calls() == []


def test_an_oversize_document_fails_with_oversize_and_the_others_are_registered(  # 案 1、4.9
    client: TestClient, running_crawl: None, search_index: InMemorySearchIndex
) -> None:
    oversize = document_json("big", text="x" * 2_000)  # 上限 1,024 バイト

    response = client.post(BATCH_PATH, json=batch_json([oversize, document_json("small")]))

    assert response.status_code == 200
    big, small = response.json()["results"]
    assert (big["status"], big["failure_type"]) == ("failed", "oversize")
    assert small["status"] == "ok"
    assert search_index.source_of(compute_document_id(SOURCE_ID, "big")) is None


def test_an_external_id_with_a_newline_is_registered_and_echoed_escaped(  # 4.3、0016 A2
    client: TestClient, running_crawl: None, search_index: InMemorySearchIndex
) -> None:
    external_id = "docs/a\nb\tc.txt"

    response = client.post(BATCH_PATH, json=batch_json([document_json(external_id)]))

    assert response.status_code == 200
    [result] = response.json()["results"]
    assert (result["external_id"], result["status"]) == (external_id, "ok")
    assert "\n" not in response.text  # 改行は JSON のエスケープ(`\\n`)で返る
    assert search_index.source_of(compute_document_id(SOURCE_ID, external_id)) is not None


def test_an_external_id_with_nul_rejects_the_whole_batch_and_names_the_document(  # 4.3
    client: TestClient, running_crawl: None, search_index: InMemorySearchIndex
) -> None:
    body = batch_json([document_json("good"), document_json("bad\x00name")])

    response = client.post(BATCH_PATH, json=body)

    assert response.status_code == 400
    error = error_of(response)
    assert error["code"] == "invalid_request"
    assert error["message"] == "invalid request: documents.1.external_id (id_invalid_character)"
    assert search_index.write_calls() == []


def test_a_document_with_a_lone_surrogate_title_is_rejected_alone(  # 4.3、0008 A3
    client: TestClient, running_crawl: None
) -> None:
    body = batch_json([document_json("bad", title="x"), document_json("good")])
    # JSON の `\ud800` は、Python の `json` で孤立サロゲートの文字列になる。
    raw = client.build_request("POST", BATCH_PATH, json=body)
    payload = raw.content.replace(b'"title":"x"', b'"title":"\\ud800"')
    assert b"\\ud800" in payload

    response = client.post(
        BATCH_PATH, content=payload, headers={"content-type": "application/json"}
    )

    assert response.status_code == 200
    bad, good = response.json()["results"]
    assert (bad["status"], bad["failure_type"]) == ("failed", "document_rejected")
    assert good["status"] == "ok"


def test_a_failed_document_message_does_not_contain_the_document(  # R9
    client: TestClient, running_crawl: None
) -> None:
    body = batch_json([document_json("secret-name-SENTINEL", text="x" * 2_000)])

    response = client.post(BATCH_PATH, json=body)

    [result] = response.json()["results"]
    assert result["message"] == "the raw content exceeds the size limit"


# --- last-seen 4.2 ---


def test_last_seen_returns_a_result_per_document_in_order(  # 4.2
    client: TestClient, search_index: InMemorySearchIndex, running_crawl: None
) -> None:
    [found] = ids(1_000, 1)
    missing = hex_id(9_999)
    seed_documents(search_index, (found,), last_seen_at=CRAWL_STARTED_AT - timedelta(days=1))

    response = client.post(LAST_SEEN_PATH, json=last_seen_json([missing, found]))

    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {"document_id": missing, "result": "not_found"},
            {"document_id": found, "result": "updated"},
        ]
    }
    again = client.post(LAST_SEEN_PATH, json=last_seen_json([found]))
    assert again.json()["results"][0]["result"] == "unchanged"


def test_last_seen_update_conflict_is_a_per_document_result(  # 4.2、K51
    client: TestClient, search_index: InMemorySearchIndex, running_crawl: None
) -> None:
    [found] = ids(1_000, 1)
    seed_documents(search_index, (found,), last_seen_at=CRAWL_STARTED_AT - timedelta(days=1))
    search_index.behavior.inject(index_ops.RAISE_LAST_SEEN_AT, Conflict())

    response = client.post(LAST_SEEN_PATH, json=last_seen_json([found]))

    assert response.status_code == 200
    assert response.json()["results"] == [{"document_id": found, "result": "update_conflict"}]


def test_last_seen_with_a_lock_not_owned_returns_lock_not_owned_per_document(  # 4.2
    client: TestClient, running_crawl: None
) -> None:
    found = hex_id(1)

    response = client.post(
        LAST_SEEN_PATH, json=last_seen_json([found], lock=lock_json(job_id="other-job"))
    )

    assert response.status_code == 200
    assert response.json()["results"] == [{"document_id": found, "result": "lock_not_owned"}]


def test_last_seen_for_a_crawl_that_was_not_started_is_a_409(  # 4.2、D-78
    client: TestClient,
) -> None:
    response = client.post(LAST_SEEN_PATH, json=last_seen_json([hex_id(1)]))

    assert response.status_code == 409
    assert error_of(response)["code"] == "crawl_not_started"


# --- 終了通知 4.4 ---


def test_finish_is_accepted_with_202_and_no_body_and_queues_the_deletion(  # 4.4
    client: TestClient, deletions_store: InMemoryStore
) -> None:
    client.post(START_PATH, json=start_json())

    response = client.post(FINISH_PATH, json=finish_json())

    assert response.status_code == 202
    assert response.content == b""
    result = stored_result(deletions_store)
    assert result.finish_received_at is not None
    assert result.enumerated_count == 3


def test_a_resent_finish_is_202_and_a_different_one_is_a_409(  # 4.4、K25
    client: TestClient,
) -> None:
    client.post(START_PATH, json=start_json())
    client.post(FINISH_PATH, json=finish_json())

    same = client.post(FINISH_PATH, json=finish_json())
    different = client.post(FINISH_PATH, json=finish_json(enumerated_count=4))

    assert same.status_code == 202
    assert different.status_code == 409
    assert error_of(different)["code"] == "finish_content_mismatch"


def test_finish_with_another_source_id_is_a_409_finish_source_mismatch(  # 4.4、K32
    client: TestClient,
) -> None:
    client.post(START_PATH, json=start_json())

    response = client.post(FINISH_PATH, json=finish_json(source_id="another"))

    assert response.status_code == 409
    assert error_of(response)["code"] == "finish_source_mismatch"


def test_finish_for_an_unknown_crawl_id_is_202_and_creates_nothing(  # 4.4 分岐 2、K7、P16
    client: TestClient, deletions_store: InMemoryStore
) -> None:
    response = client.post("/crawls/unknown/finish", json=finish_json())

    assert response.status_code == 202
    assert deletions_store.record_ids() == []


@pytest.mark.parametrize("outcome", ["failed", "cancelled"])
def test_a_failed_or_cancelled_finish_needs_no_counts_and_fails_the_result(  # 4.4 分岐 3
    client: TestClient, deletions_store: InMemoryStore, outcome: str
) -> None:
    client.post(START_PATH, json=start_json())
    body = {"source_id": SOURCE_ID, "outcome": outcome, "finished_at": "2026-11-09T01:03:10Z"}

    response = client.post(FINISH_PATH, json=body)

    assert response.status_code == 202
    result = stored_result(deletions_store)
    assert result.status is DeletionStatus.FAILED
    assert result.reason is (
        DeletionReason.OUTCOME_FAILED if outcome == "failed" else DeletionReason.OUTCOME_CANCELLED
    )


def test_an_enumeration_completed_finish_without_counts_is_a_400(  # 4.4、K38(形式 400)
    client: TestClient,
) -> None:
    client.post(START_PATH, json=start_json())
    body = finish_json()
    del body["enumerated_count"]

    response = client.post(FINISH_PATH, json=body)

    assert response.status_code == 400
    assert error_of(response)["code"] == "invalid_request"


def test_a_malformed_finish_is_a_400_even_when_the_source_id_differs(  # K38 の順序
    client: TestClient,
) -> None:
    client.post(START_PATH, json=start_json())

    response = client.post(FINISH_PATH, json=finish_json(source_id="another", outcome="bogus"))

    assert response.status_code == 400


def test_skipped_count_is_ignored_even_if_it_differs_from_the_list(  # API-U-12(案: 値は使わない)
    client: TestClient,
) -> None:
    client.post(START_PATH, json=start_json())

    response = client.post(FINISH_PATH, json=finish_json(skipped_count=99))

    assert response.status_code == 202


def test_the_finish_wakes_the_deletion_worker_which_deletes_expired_documents(  # 案 2(wake)
    client: TestClient, search_index: InMemorySearchIndex, deletions_store: InMemoryStore
) -> None:
    """走査の間隔は 30 秒。終了通知の受理で起床して、待たずに処理される(配線の確認)。"""
    seen = ids(1_000, 2)
    expired = ids(2_000, 2)
    seed_documents(search_index, seen, last_seen_at=CRAWL_STARTED_AT)
    seed_documents(search_index, expired, last_seen_at=CRAWL_STARTED_AT - timedelta(days=5))
    client.post(START_PATH, json=start_json(ttl=3 * 86_400))

    client.post(FINISH_PATH, json=finish_json(enumerated_count=2, skipped_document_ids=[]))

    assert wait_until(lambda: client.get(STATUS_PATH).json()["status"] == "deleted")
    assert set(search_index.document_ids()) == set(seen)


# --- Status 4.5 ---


def test_status_of_a_running_crawl_omits_the_unrecorded_fields(client: TestClient) -> None:  # 4.5
    client.post(START_PATH, json=start_json())

    response = client.get(STATUS_PATH)

    assert response.status_code == 200
    assert response.json() == {
        "crawl_id": CRAWL_ID,
        "source_id": SOURCE_ID,
        "status": "running",
        "forced": False,
        "ttl": 86_400,
        "ratio_threshold": 0.2,
        "min_delete_count": 10,
    }


def test_status_of_a_deleted_crawl_returns_the_recorded_numbers_and_times(  # 4.5 の応答例
    client: TestClient, deletions_store: InMemoryStore, clock: FixedClock
) -> None:
    seed_result(
        deletions_store,
        make_result(
            status=DeletionStatus.DELETED,
            enumerated_count=1203,
            n_seen=1202,
            e_missing=1,
            target_count=12,
            denominator=1215,
            deleted_count=12,
            finish_received_at=CRAWL_STARTED_AT + timedelta(minutes=12),
            deletion_started_at=CRAWL_STARTED_AT + timedelta(minutes=13),
            ended_at=CRAWL_STARTED_AT + timedelta(minutes=14),
        ),
    )

    body = client.get(STATUS_PATH).json()

    assert body == {
        "crawl_id": CRAWL_ID,
        "source_id": SOURCE_ID,
        "status": "deleted",
        "forced": False,
        "enumerated_count": 1203,
        "n_seen": 1202,
        "e_missing": 1,
        "target_count": 12,
        "denominator": 1215,
        "ttl": 86_400,
        "ratio_threshold": 0.2,
        "min_delete_count": 10,
        "deleted_count": 12,
        "finish_received_at": "2026-11-09T01:12:00.000Z",
        "deletion_started_at": "2026-11-09T01:13:00.000Z",
        "finished_at": "2026-11-09T01:14:00.000Z",
    }


def test_status_of_a_failed_crawl_returns_the_reason(
    client: TestClient, deletions_store: InMemoryStore
) -> None:  # 4.5
    seed_result(
        deletions_store,
        make_result(status=DeletionStatus.FAILED, reason=DeletionReason.INDEXER_RESTART),
    )

    body = client.get(STATUS_PATH).json()

    assert (body["status"], body["reason"]) == ("failed", "indexer_restart")


def test_status_of_a_waiting_deletion_returns_waiting_for(  # 4.5 の応答例(待機中)
    client: TestClient, deletions_store: InMemoryStore
) -> None:
    received = CRAWL_STARTED_AT + timedelta(minutes=5)
    seed_result(deletions_store, make_result(crawl_id="job-older", finish_received_at=received))
    seed_result(
        deletions_store,
        make_result(finish_received_at=received + timedelta(minutes=1)),
    )

    body = client.get(STATUS_PATH).json()

    assert (body["status"], body["waiting_for"]) == ("running", "job-older")


def test_status_of_an_unknown_crawl_is_a_404_crawl_not_found(client: TestClient) -> None:  # 4.5
    response = client.get("/crawls/unknown")

    assert response.status_code == 404
    assert error_of(response) == {
        "code": "crawl_not_found",
        "message": "the crawl was not found",
        "retryable": False,
    }


# --- ソース削除 4.6〜4.8 ---


@pytest.fixture
def source_with_crawls(deletions_store: InMemoryStore, jobs_store: InMemoryStore) -> None:
    seed_lock(jobs_store, job_id="job-source-delete")
    seed_result(deletions_store, make_result(crawl_id="job-running"))
    seed_result(
        deletions_store,
        make_result(crawl_id="job-deleted", status=DeletionStatus.DELETED),
    )


SOURCE_DELETE_LOCK = lock_json(job_id="job-source-delete")


def test_discard_returns_the_discarded_crawl_ids(  # 4.6
    client: TestClient, deletions_store: InMemoryStore, source_with_crawls: None
) -> None:
    body = {"lock": SOURCE_DELETE_LOCK, "reason": "source_deleted"}

    response = client.post(DISCARD_PATH, json=body)

    assert response.status_code == 200
    assert response.json() == {"discarded_crawl_ids": ["job-running"]}
    result = stored_result(deletions_store, "job-running")
    assert (result.status, result.reason) == (
        DeletionStatus.DISCARDED,
        DeletionReason.SOURCE_DELETED,
    )


def test_discard_does_not_require_the_lock_to_be_owned(  # 案 8(順 1 は確認しない)、4.6
    client: TestClient, source_with_crawls: None
) -> None:
    response = client.post(DISCARD_PATH, json=locked_json(lock=lock_json(owner="expired-owner")))

    assert response.status_code == 200


def test_delete_documents_returns_the_deleted_count_and_removes_only_the_source(  # 4.7
    client: TestClient, search_index: InMemorySearchIndex, source_with_crawls: None
) -> None:
    mine = ids(1_000, 3)
    others = ids(2_000, 2)
    seed_documents(search_index, mine, last_seen_at=CRAWL_STARTED_AT)
    seed_documents(search_index, others, last_seen_at=CRAWL_STARTED_AT, source_id="other")

    response = delete(client, DELETE_DOCUMENTS_PATH, locked_json(lock=SOURCE_DELETE_LOCK))

    assert response.status_code == 200
    assert response.json() == {"deleted_count": 3}
    assert set(search_index.document_ids()) == set(others)


def test_delete_documents_is_idempotent_and_returns_zero_on_a_resend(  # 4.7
    client: TestClient, search_index: InMemorySearchIndex, source_with_crawls: None
) -> None:
    seed_documents(search_index, ids(1_000, 2), last_seen_at=CRAWL_STARTED_AT)
    delete(client, DELETE_DOCUMENTS_PATH, locked_json(lock=SOURCE_DELETE_LOCK))

    response = delete(client, DELETE_DOCUMENTS_PATH, locked_json(lock=SOURCE_DELETE_LOCK))

    assert response.status_code == 200
    assert response.json() == {"deleted_count": 0}


def test_delete_records_returns_true_then_false(  # 4.8
    client: TestClient, deletions_store: InMemoryStore, source_with_crawls: None
) -> None:
    first = delete(client, DELETE_RECORDS_PATH, locked_json(lock=SOURCE_DELETE_LOCK))
    second = delete(client, DELETE_RECORDS_PATH, locked_json(lock=SOURCE_DELETE_LOCK))

    assert (first.status_code, first.json()) == (200, {"deleted": True})
    assert (second.status_code, second.json()) == (200, {"deleted": False})
    assert deletions_store.record_ids() == []


@pytest.mark.parametrize("path", [DELETE_DOCUMENTS_PATH, DELETE_RECORDS_PATH])
@pytest.mark.parametrize(
    "lock",
    [
        lock_json(owner="someone-else", job_id="job-source-delete"),
        lock_json(job_id="another-job"),
    ],
    ids=["other_owner", "other_job"],
)
def test_delete_with_a_lock_not_owned_is_a_409_and_changes_nothing(  # 4.7、4.8、案 8
    client: TestClient,
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    source_with_crawls: None,
    path: str,
    lock: dict[str, Any],
) -> None:
    seed_documents(search_index, ids(1_000, 2), last_seen_at=CRAWL_STARTED_AT)
    records_before = deletions_store.record_ids()

    response = delete(client, path, locked_json(lock=lock))

    assert response.status_code == 409
    assert error_of(response) == {
        "code": "lock_not_owned",
        "message": "the lock for the source is not owned by the requester",
        "retryable": False,
    }
    assert len(search_index.document_ids()) == 2
    assert deletions_store.record_ids() == records_before


def test_delete_with_an_expired_or_missing_lock_is_a_409(
    client: TestClient, source_with_crawls: None, jobs_store: InMemoryStore, clock: FixedClock
) -> None:  # 4.7(リース切れ)
    clock.advance(seconds=2 * 3600)

    expired = delete(client, DELETE_RECORDS_PATH, locked_json(lock=SOURCE_DELETE_LOCK))
    jobs_store.delete("lock-" + SOURCE_ID)
    missing = delete(client, DELETE_RECORDS_PATH, locked_json(lock=SOURCE_DELETE_LOCK))

    assert (expired.status_code, missing.status_code) == (409, 409)


# --- healthz(案 21) ---


def test_healthz_is_200_with_a_minimal_body(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- 503・500 の写像(3.4、案 15) ---


def _unavailable(reason: str = "http_503") -> OpenSearchUnavailableError:
    return OpenSearchUnavailableError(reason)


@pytest.mark.parametrize(
    ("request_arguments"),
    [
        ("POST", START_PATH, start_json()),
        ("POST", FINISH_PATH, finish_json()),
        ("GET", STATUS_PATH, None),
        ("POST", BATCH_PATH, batch_json()),
        ("POST", LAST_SEEN_PATH, last_seen_json([hex_id(1)])),
        ("POST", DISCARD_PATH, locked_json()),
        ("DELETE", DELETE_DOCUMENTS_PATH, locked_json()),
        ("DELETE", DELETE_RECORDS_PATH, locked_json()),
    ],
    ids=[
        "start",
        "finish",
        "status",
        "batch",
        "last_seen",
        "discard",
        "delete_docs",
        "delete_records",
    ],
)
def test_an_opensearch_outage_is_a_503_unavailable_that_is_retryable(  # 3.4、API-U-19
    client: TestClient,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    request_arguments: tuple[str, str, Any],
) -> None:
    method, path, body = request_arguments
    seed_lock(jobs_store)
    deletions_store.behavior.inject(store_ops.FETCH, _unavailable(), times=None)
    deletions_store.behavior.inject(store_ops.LIST, _unavailable(), times=None)
    deletions_store.behavior.inject(store_ops.SAVE, _unavailable(), times=None)
    jobs_store.behavior.inject(store_ops.FETCH, _unavailable(), times=None)

    response = client.request(method, path, json=body)

    assert response.status_code == 503
    assert error_of(response) == {
        "code": "unavailable",
        "message": "the service is temporarily unavailable",
        "retryable": True,
    }


def test_a_search_index_outage_during_a_batch_is_a_503(  # 4.3 5xx
    client: TestClient, search_index: InMemorySearchIndex, running_crawl: None
) -> None:
    search_index.behavior.inject(index_ops.FETCH, _unavailable("connection_timeout"), times=None)

    response = client.post(BATCH_PATH, json=batch_json())

    assert response.status_code == 503
    assert error_of(response)["retryable"] is True


def test_a_malformed_stored_record_is_a_500_internal_error_with_a_fixed_message(  # 案 15
    client: TestClient, deletions_store: InMemoryStore
) -> None:
    seed_malformed_result(deletions_store)

    response = client.get(STATUS_PATH)

    assert response.status_code == 500
    assert error_of(response) == {
        "code": "internal_error",
        "message": "an internal error occurred",
        "retryable": False,
    }
    assert MALFORMED_VALUE not in response.text


def test_an_unexpected_opensearch_response_is_a_500_internal_error(
    client: TestClient, deletions_store: InMemoryStore
) -> None:
    deletions_store.behavior.inject(
        store_ops.FETCH, OpenSearchUnexpectedResponseError("parsing_exception")
    )

    response = client.get(STATUS_PATH)

    assert response.status_code == 500
    assert error_of(response)["code"] == "internal_error"
    assert "parsing_exception" not in response.text
