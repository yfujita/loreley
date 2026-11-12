"""Status API の応答の組み立て(arch 9.5、api 4.5。K43)。

D-31・D-32・D-46・D-91(l) と、受理の有無の読み方の表(arch 9.5)を確認する。
"""

from datetime import UTC, datetime, timedelta

import pytest

from loreley_indexer.common.errors import CrawlNotFoundError
from loreley_indexer.crawl_runs import CrawlRuns, FinishOutcome
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionReason,
    DeletionStatus,
    deletion_record_id,
)
from tests.crawl_runs.factories import (
    CRAWL_ID,
    SOURCE_ID,
    hex_id,
    make_failed_finish,
    make_finish,
    make_generation,
    make_result,
    seed_result,
)
from tests.fakes.clock import DEFAULT_NOW
from tests.fakes.in_memory_store import InMemoryStore

T0 = datetime(2026, 11, 9, 1, 20, 5, tzinfo=UTC)


def received(crawl_id: str, offset_seconds: int = 0, **overrides: object):
    """終了通知を受理済みで `running`(待機中・判定中・実行中のいずれか)の結果。"""
    return make_result(
        crawl_id=crawl_id,
        finish_received_at=T0 + timedelta(seconds=offset_seconds),
        finish_request_digest="d" * 64,
        **overrides,
    )


# --- 404 ---


def test_unknown_crawl_is_not_found(crawl_runs: CrawlRuns) -> None:  # D-16
    with pytest.raises(CrawlNotFoundError):
        crawl_runs.crawl_status("job-unknown")


def test_a_generation_record_alone_is_not_found(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    deletions_store.seed(deletion_record_id(SOURCE_ID), make_generation().to_body())
    with pytest.raises(CrawlNotFoundError):
        crawl_runs.crawl_status(CRAWL_ID)


# --- 項目の写し ---


def test_a_running_result_before_the_finish_notification(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result(ttl=3600, ratio_threshold=0.3, min_delete_count=7))

    status = crawl_runs.crawl_status(CRAWL_ID)

    assert (status.crawl_id, status.source_id) == (CRAWL_ID, SOURCE_ID)
    assert status.status is DeletionStatus.RUNNING
    assert status.finish_received_at is None  # 受理前
    assert status.waiting_for is None
    assert status.reason is None
    assert (status.ttl, status.ratio_threshold, status.min_delete_count) == (3600, 0.3, 7)
    assert status.forced is False
    assert (status.target_count, status.denominator, status.deleted_count) == (None, None, None)
    assert deletions_store.write_calls() == []  # 読み取りのみ


def test_a_deleted_result_carries_the_counts_and_times(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    ended_at = T0 + timedelta(seconds=50)
    seed_result(
        deletions_store,
        received(
            CRAWL_ID,
            status=DeletionStatus.DELETED,
            forced=True,
            enumerated_count=1203,
            n_seen=1202,
            e_missing=1,
            target_count=12,
            denominator=1215,
            deleted_count=12,
            deletion_started_at=T0 + timedelta(seconds=35),
            ended_at=ended_at,
        ),
    )

    status = crawl_runs.crawl_status(CRAWL_ID)

    assert status.status is DeletionStatus.DELETED
    assert status.forced is True
    assert (status.enumerated_count, status.n_seen, status.e_missing) == (1203, 1202, 1)
    assert (status.target_count, status.denominator, status.deleted_count) == (12, 1215, 12)
    assert status.finish_received_at == T0
    assert status.deletion_started_at == T0 + timedelta(seconds=35)
    assert status.finished_at == ended_at
    assert status.waiting_for is None


# --- 受理の有無の読み方(arch 9.5 の表。D-91(l)) ---


def test_enumeration_completed_accepted_shows_finish_received_at_and_running(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result())
    crawl_runs.finish_crawl(make_finish())

    status = crawl_runs.crawl_status(CRAWL_ID)

    assert status.status is DeletionStatus.RUNNING
    assert status.finish_received_at == DEFAULT_NOW


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        (FinishOutcome.FAILED, DeletionReason.OUTCOME_FAILED),
        (FinishOutcome.CANCELLED, DeletionReason.OUTCOME_CANCELLED),
    ],
)
def test_failed_or_cancelled_accepted_shows_failed_with_the_reason_and_no_finish_received_at(
    crawl_runs: CrawlRuns,
    deletions_store: InMemoryStore,
    outcome: FinishOutcome,
    reason: DeletionReason,
) -> None:
    seed_result(deletions_store, make_result())
    crawl_runs.finish_crawl(make_failed_finish(outcome))

    status = crawl_runs.crawl_status(CRAWL_ID)

    assert status.status is DeletionStatus.FAILED
    assert status.reason is reason
    assert status.finish_received_at is None
    assert status.finished_at == DEFAULT_NOW


def test_a_late_finish_leaves_the_superseded_result_without_an_acceptance_trace(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(
        deletions_store,
        make_result(status=DeletionStatus.DISCARDED, reason=DeletionReason.SUPERSEDED),
    )
    crawl_runs.finish_crawl(make_finish())

    status = crawl_runs.crawl_status(CRAWL_ID)

    assert status.status is DeletionStatus.DISCARDED
    assert status.reason is DeletionReason.SUPERSEDED
    assert status.finish_received_at is None


def test_a_restart_failure_is_distinguished_from_an_outcome_failure_by_the_reason(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result())
    crawl_runs.finish_crawl(make_finish())
    crawl_runs.fail_unfinished_crawls_after_restart()

    status = crawl_runs.crawl_status(CRAWL_ID)

    assert status.status is DeletionStatus.FAILED
    assert status.reason is DeletionReason.INDEXER_RESTART
    assert status.finish_received_at == DEFAULT_NOW  # 受理の事実は残る


# --- 「削除中」(K43) ---


def test_deleting_is_still_running_and_progress_is_only_what_was_recorded(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, received(CRAWL_ID, deletion_started_at=T0 + timedelta(seconds=9)))

    status = crawl_runs.crawl_status(CRAWL_ID)

    assert status.status is DeletionStatus.RUNNING
    assert status.deletion_started_at == T0 + timedelta(seconds=9)
    assert status.deleted_count is None  # 未記録の進捗は推測しない


def test_recorded_progress_is_returned_while_running(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(
        deletions_store,
        received(
            CRAWL_ID,
            deletion_started_at=T0 + timedelta(seconds=9),
            target_count=10,
            deleted_count=4,
        ),
    )

    status = crawl_runs.crawl_status(CRAWL_ID)

    assert status.status is DeletionStatus.RUNNING
    assert (status.target_count, status.deleted_count) == (10, 4)


# --- waiting_for(案 17。D-31、D-32、D-46) ---


def test_a_result_behind_a_running_deletion_waits_for_it(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:  # D-31
    seed_result(deletions_store, received("job-a", 0, deletion_started_at=T0))
    seed_result(deletions_store, received("job-b", 60))

    assert crawl_runs.crawl_status("job-b").waiting_for == "job-a"
    assert crawl_runs.crawl_status("job-b").status is DeletionStatus.RUNNING  # 状態は増えない
    assert crawl_runs.crawl_status("job-a").waiting_for is None


def test_three_generations_wait_in_a_chain_on_the_immediate_predecessor(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:  # D-32
    for offset, crawl_id in enumerate(["job-a", "job-b", "job-c"]):
        seed_result(deletions_store, received(crawl_id, offset * 60))

    assert crawl_runs.crawl_status("job-a").waiting_for is None
    assert crawl_runs.crawl_status("job-b").waiting_for == "job-a"
    assert crawl_runs.crawl_status("job-c").waiting_for == "job-b"


def test_waiting_ends_when_the_predecessor_becomes_terminal_even_if_it_failed(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(
        deletions_store,
        received(
            "job-a",
            0,
            status=DeletionStatus.FAILED,
            reason=DeletionReason.MAINTENANCE,
            ended_at=T0,
        ),
    )
    seed_result(deletions_store, received("job-b", 60))
    seed_result(deletions_store, received("job-c", 120))

    assert crawl_runs.crawl_status("job-b").waiting_for is None
    assert crawl_runs.crawl_status("job-c").waiting_for == "job-b"


def test_equal_finish_received_at_is_ordered_by_crawl_id(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:  # D-46(a)
    seed_result(deletions_store, received("job-2", 0))
    seed_result(deletions_store, received("job-1", 0))

    assert crawl_runs.crawl_status("job-1").waiting_for is None
    assert crawl_runs.crawl_status("job-2").waiting_for == "job-1"


def test_several_results_with_the_same_finish_received_at_wait_in_crawl_id_order(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:  # D-46(a)
    for crawl_id in ("job-3", "job-1", "job-2"):
        seed_result(deletions_store, received(crawl_id, 0))

    assert crawl_runs.crawl_status("job-1").waiting_for is None
    assert crawl_runs.crawl_status("job-2").waiting_for == "job-1"
    assert crawl_runs.crawl_status("job-3").waiting_for == "job-2"


def test_a_running_result_without_finish_is_not_a_predecessor_and_does_not_wait(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:  # D-46(b)
    seed_result(deletions_store, make_result(crawl_id="job-unfinished"))
    seed_result(deletions_store, received("job-b", 60))

    assert crawl_runs.crawl_status("job-b").waiting_for is None
    assert crawl_runs.crawl_status("job-unfinished").waiting_for is None


def test_unfinished_results_of_other_sources_are_not_predecessors(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, received("job-other", 0, source_id="src-other"))
    seed_result(deletions_store, received("job-b", 60))

    assert crawl_runs.crawl_status("job-b").waiting_for is None


def test_waiting_for_is_not_given_to_terminal_results(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, received("job-a", 0))
    seed_result(
        deletions_store,
        received("job-b", 60, status=DeletionStatus.DELETED, ended_at=T0 + timedelta(minutes=5)),
    )

    assert crawl_runs.crawl_status("job-b").waiting_for is None


def test_status_does_not_expose_the_saved_id_lists(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(
        deletions_store,
        received(CRAWL_ID, skipped_document_ids=(hex_id(1),), oversize_document_ids=()),
    )

    assert hex_id(1) not in repr(crawl_runs.crawl_status(CRAWL_ID))
