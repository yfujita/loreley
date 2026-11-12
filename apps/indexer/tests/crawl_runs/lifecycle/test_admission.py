"""登録の受理条件の照会(arch 9.5、K23)。

D-77、D-78、D-81、D-82 と、C-27(a)(b) の `rewrite_mode` の取得元を確認する。
"""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from loreley_indexer.common.errors import (
    AdmissionRejectedError,
    CrawlAlreadyClosedError,
    CrawlFinishedError,
    CrawlNotStartedError,
    CrawlSourceMismatchError,
    CrawlStartedAtMismatchError,
    UnavailableError,
)
from loreley_indexer.crawl_runs import Admission, AdmissionChecker
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionReason,
    DeletionStatus,
    FinishOutcome,
    MalformedRecordError,
    deletion_record_id,
)
from tests.crawl_runs.factories import (
    CRAWL_ID,
    CRAWL_STARTED_AT,
    SOURCE_ID,
    make_generation,
    make_result,
    seed_result,
)
from tests.fakes import in_memory_store
from tests.fakes.in_memory_store import InMemoryStore

RECEIVED_AT = datetime(2026, 11, 9, 2, 0, 0, tzinfo=UTC)


@pytest.fixture
def checker(deletions_store: InMemoryStore) -> AdmissionChecker:
    return AdmissionChecker(deletions_store)


def check(
    checker: AdmissionChecker,
    *,
    source_id: str = SOURCE_ID,
    crawl_id: str = CRAWL_ID,
    crawl_started_at: datetime = CRAWL_STARTED_AT,
) -> Admission:
    return checker.check(source_id=source_id, crawl_id=crawl_id, crawl_started_at=crawl_started_at)


# --- 受理 ---


def test_running_result_without_finish_is_admitted(
    checker: AdmissionChecker, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result())
    assert check(checker) == Admission(rewrite_mode=False)


@pytest.mark.parametrize("rewrite_mode", [True, False])
def test_rewrite_mode_comes_from_the_copied_deletion_result(  # C-27(a)(b)
    checker: AdmissionChecker, deletions_store: InMemoryStore, rewrite_mode: bool
) -> None:
    seed_result(deletions_store, make_result(rewrite_mode=rewrite_mode))
    assert check(checker).rewrite_mode is rewrite_mode


@pytest.mark.parametrize(
    "requested",
    [
        datetime(2026, 11, 9, 1, 0, 0, 0, tzinfo=UTC),
        datetime(2026, 11, 9, 1, 0, 0, 999, tzinfo=UTC),  # ミリ秒未満は比べない
        datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone(timedelta(hours=9))),  # 同じ時刻の別表記
    ],
)
def test_crawl_started_at_is_compared_as_an_instant_in_milliseconds(
    checker: AdmissionChecker, deletions_store: InMemoryStore, requested: datetime
) -> None:
    seed_result(deletions_store, make_result())
    assert check(checker, crawl_started_at=requested) == Admission(rewrite_mode=False)


def test_the_check_only_reads(checker: AdmissionChecker, deletions_store: InMemoryStore) -> None:
    seed_result(deletions_store, make_result())
    check(checker)
    assert deletions_store.write_calls() == []


def test_the_check_reads_only_the_requested_crawl(
    checker: AdmissionChecker, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result(crawl_id="job-old", rewrite_mode=True))
    seed_result(deletions_store, make_result(rewrite_mode=False))
    assert check(checker).rewrite_mode is False


# --- 拒否の 5 種 ---


def test_missing_result_is_rejected_as_not_started(  # D-78
    checker: AdmissionChecker, deletions_store: InMemoryStore
) -> None:
    with pytest.raises(CrawlNotStartedError):
        check(checker)


def test_generation_record_alone_does_not_count_as_a_result(
    checker: AdmissionChecker, deletions_store: InMemoryStore
) -> None:
    deletions_store.seed(deletion_record_id(SOURCE_ID), make_generation().to_body())
    with pytest.raises(CrawlNotStartedError):
        check(checker)


def test_different_source_id_is_rejected(  # D-77(a)
    checker: AdmissionChecker, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result())
    with pytest.raises(CrawlSourceMismatchError):
        check(checker, source_id="src-other")


@pytest.mark.parametrize(
    "requested",
    [CRAWL_STARTED_AT + timedelta(seconds=1), CRAWL_STARTED_AT - timedelta(milliseconds=1)],
)
def test_different_crawl_started_at_is_rejected(  # D-77(b)
    checker: AdmissionChecker, deletions_store: InMemoryStore, requested: datetime
) -> None:
    seed_result(deletions_store, make_result())
    with pytest.raises(CrawlStartedAtMismatchError):
        check(checker, crawl_started_at=requested)


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (DeletionStatus.DISCARDED, DeletionReason.SUPERSEDED),
        (DeletionStatus.DISCARDED, DeletionReason.SOURCE_DELETED),
        (DeletionStatus.FAILED, DeletionReason.INDEXER_RESTART),
        (DeletionStatus.FAILED, DeletionReason.MAINTENANCE),
        (DeletionStatus.DELETED, None),
        (DeletionStatus.SKIPPED_BY_RATIO, None),
        (DeletionStatus.VALIDATION_FAILED, DeletionReason.COUNT_MISMATCH),
    ],
)
def test_terminal_result_is_rejected_even_when_crawl_started_at_matches(  # D-81
    checker: AdmissionChecker,
    deletions_store: InMemoryStore,
    status: DeletionStatus,
    reason: DeletionReason | None,
) -> None:
    seed_result(deletions_store, make_result(status=status, reason=reason))
    with pytest.raises(CrawlAlreadyClosedError):
        check(checker)


def test_running_result_with_finish_received_is_rejected(  # D-82(1)
    checker: AdmissionChecker, deletions_store: InMemoryStore
) -> None:
    seed_result(
        deletions_store,
        make_result(
            finish_received_at=RECEIVED_AT,
            finish_request_digest="d" * 64,
            outcome=FinishOutcome.ENUMERATION_COMPLETED,
        ),
    )
    with pytest.raises(CrawlFinishedError):
        check(checker)


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        (FinishOutcome.FAILED, DeletionReason.OUTCOME_FAILED),
        (FinishOutcome.CANCELLED, DeletionReason.OUTCOME_CANCELLED),
    ],
)
def test_result_closed_by_a_failed_or_cancelled_finish_is_closed_not_finished(  # D-82(4)
    checker: AdmissionChecker,
    deletions_store: InMemoryStore,
    outcome: FinishOutcome,
    reason: DeletionReason,
) -> None:
    # `finish_received_at` は記録されず、`status=failed` だけで拒否される。
    seed_result(
        deletions_store,
        make_result(
            status=DeletionStatus.FAILED,
            reason=reason,
            outcome=outcome,
            finish_request_digest="d" * 64,
        ),
    )
    with pytest.raises(CrawlAlreadyClosedError):
        check(checker)


def test_rejection_leaves_the_store_untouched(
    checker: AdmissionChecker, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result(status=DeletionStatus.DELETED))
    before = deletions_store.body_of(f"deletion_result-{CRAWL_ID}")
    with pytest.raises(AdmissionRejectedError):
        check(checker)
    assert deletions_store.write_calls() == []
    assert deletions_store.body_of(f"deletion_result-{CRAWL_ID}") == before


# --- 判定の順序(結果なし → source_id → crawl_started_at → 状態 → 終了通知。arch 9.5 の条件順) ---


def seed_finished_closed(store: InMemoryStore) -> None:
    seed_result(
        store,
        make_result(status=DeletionStatus.DELETED, finish_received_at=RECEIVED_AT),
    )


def test_source_mismatch_is_reported_before_started_at_mismatch(
    checker: AdmissionChecker, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result())
    with pytest.raises(CrawlSourceMismatchError):
        check(
            checker,
            source_id="src-other",
            crawl_started_at=CRAWL_STARTED_AT + timedelta(hours=1),
        )


def test_mismatch_is_reported_before_the_closed_state(
    checker: AdmissionChecker, deletions_store: InMemoryStore
) -> None:
    seed_finished_closed(deletions_store)
    with pytest.raises(CrawlSourceMismatchError):
        check(checker, source_id="src-other")
    with pytest.raises(CrawlStartedAtMismatchError):
        check(checker, crawl_started_at=CRAWL_STARTED_AT + timedelta(hours=1))


def test_closed_state_is_reported_before_finish_received(
    checker: AdmissionChecker, deletions_store: InMemoryStore
) -> None:
    seed_finished_closed(deletions_store)
    with pytest.raises(CrawlAlreadyClosedError):
        check(checker)


# --- 契約上のエラー表現(api 3.4) ---


@pytest.mark.parametrize(
    ("error_type", "code"),
    [
        (CrawlNotStartedError, "crawl_not_started"),
        (CrawlSourceMismatchError, "crawl_source_mismatch"),
        (CrawlStartedAtMismatchError, "crawl_started_at_mismatch"),
        (CrawlAlreadyClosedError, "crawl_already_closed"),
        (CrawlFinishedError, "crawl_finished"),
    ],
)
def test_each_rejection_is_a_non_retryable_409_with_its_own_code(
    error_type: type[AdmissionRejectedError], code: str
) -> None:
    error = error_type()
    assert isinstance(error, AdmissionRejectedError)
    assert (error.status_code, error.code, error.retryable) == (409, code, False)


# --- 下位の異常 ---


def test_store_outage_propagates_as_unavailable(
    checker: AdmissionChecker, deletions_store: InMemoryStore
) -> None:
    deletions_store.behavior.inject(in_memory_store.FETCH, UnavailableError("http_503"))
    with pytest.raises(UnavailableError):
        check(checker)


def test_malformed_stored_result_is_not_treated_as_a_rejection(
    checker: AdmissionChecker, deletions_store: InMemoryStore
) -> None:
    body: dict[str, Any] = make_result().to_body() | {"status": "paused"}
    deletions_store.seed(f"deletion_result-{CRAWL_ID}", body)
    with pytest.raises(MalformedRecordError):
        check(checker)
