"""起動時の整理(arch 9.8、案 3、M-12)。D-20・D-34・D-93(再起動側)を確認する。"""

import logging
from datetime import UTC, datetime, timedelta

import pytest

from loreley_indexer.common.errors import UnavailableError
from loreley_indexer.crawl_runs import CrawlRuns
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionReason,
    DeletionStatus,
    FinishOutcome,
    deletion_result_record_id,
    restart,
    results,
)
from loreley_indexer.infrastructure.opensearch import Conflict
from tests.crawl_runs.factories import (
    MALFORMED_VALUE,
    hex_id,
    make_result,
    seed_malformed_result,
    seed_result,
    snapshot,
    stored_result,
)
from tests.fakes import in_memory_store as ops
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.in_memory_store import InMemoryStore

T0 = datetime(2026, 11, 9, 1, 20, 5, tzinfo=UTC)


def received(crawl_id: str, **overrides: object):
    return make_result(
        crawl_id=crawl_id,
        finish_received_at=T0,
        finish_request_digest="d" * 64,
        outcome=FinishOutcome.ENUMERATION_COMPLETED,
        enumerated_count=10,
        skipped_document_ids=(hex_id(1), hex_id(2)),
        oversize_document_ids=(hex_id(3),),
        skip_and_oversize_id_count=3,
        skip_and_oversize_id_limit_exceeded=False,
        **overrides,
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {},  # 待機中
        {"deletion_started_at": T0},  # 判定中
        {"deletion_started_at": T0, "target_count": 10, "denominator": 100, "deleted_count": 4},
    ],
    ids=["waiting", "judging", "executing"],
)
def test_received_unfinished_results_become_failed_by_restart(  # D-20、D-34
    crawl_runs: CrawlRuns,
    deletions_store: InMemoryStore,
    clock: FixedClock,
    overrides: dict[str, object],
) -> None:
    seed_result(deletions_store, received("job-a", **overrides))

    failed_count = crawl_runs.fail_unfinished_crawls_after_restart()

    result = stored_result(deletions_store, "job-a")
    assert failed_count == 1
    assert result.status is DeletionStatus.FAILED
    assert result.reason is DeletionReason.INDEXER_RESTART
    assert result.ended_at == DEFAULT_NOW
    # 保存した ID 一覧は同じ書き込みで消え、ダイジェストと受理の事実・記録済みの件数は残る(K35)。
    assert result.skipped_document_ids is None
    assert result.oversize_document_ids is None
    assert result.finish_request_digest == "d" * 64
    assert result.finish_received_at == T0
    # 削除が 1 件も実行されていなければ 0(D-93)。実行中だったものは、記録済みの件数のまま。
    assert result.deleted_count == overrides.get("deleted_count", 0)
    assert deletions_store.write_calls() == [ops.REPLACE]


def test_a_waiting_deletion_is_failed_without_being_run(  # D-93
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, received("job-a", deletion_started_at=T0, deleted_count=4))
    seed_result(deletions_store, received("job-b"))

    crawl_runs.fail_unfinished_crawls_after_restart()

    result_b = stored_result(deletions_store, "job-b")
    assert result_b.status is DeletionStatus.FAILED
    assert result_b.reason is DeletionReason.INDEXER_RESTART
    assert result_b.deleted_count == 0  # 削除は 1 件も実行されない(D-93)
    assert result_b.skipped_document_ids is None
    assert result_b.finish_request_digest == "d" * 64
    result_a = stored_result(deletions_store, "job-a")
    assert result_a.reason is DeletionReason.INDEXER_RESTART
    assert result_a.deleted_count == 4  # 実行中だった結果の記録済みの件数は、減らさない


def test_a_malformed_record_does_not_stop_the_cleanup_of_the_others(  # 再起動ループの防止
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, caplog: pytest.LogCaptureFixture
) -> None:
    seed_result(deletions_store, received("job-a"))
    bad_record_id = seed_malformed_result(
        deletions_store, crawl_id="job-bad", finish_received_at=T0, finish_request_digest="d" * 64
    )
    bad_body = deletions_store.body_of(bad_record_id)
    seed_result(deletions_store, received("job-b", source_id="src-2"))

    with caplog.at_level(logging.WARNING):
        failed_count = crawl_runs.fail_unfinished_crawls_after_restart()

    assert failed_count == 2
    for crawl_id in ("job-a", "job-b"):
        assert stored_result(deletions_store, crawl_id).status is DeletionStatus.FAILED
    assert deletions_store.body_of(bad_record_id) == bad_body  # 不正な記録は書き換えない
    assert bad_record_id in caplog.text
    assert MALFORMED_VALUE not in caplog.text


def test_a_running_result_without_a_finish_is_not_touched(  # 案 3
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    """終了通知が届いていない `running` は、次の開始通知で `superseded` になるので触れない。"""
    seed_result(deletions_store, make_result(crawl_id="job-unfinished"))
    before = snapshot(deletions_store)

    assert crawl_runs.fail_unfinished_crawls_after_restart() == 0

    assert snapshot(deletions_store) == before
    assert deletions_store.write_calls() == []


def test_terminal_results_are_not_touched(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(
        deletions_store,
        received("job-done", status=DeletionStatus.DELETED, ended_at=T0 + timedelta(minutes=1)),
    )
    seed_result(
        deletions_store,
        make_result(
            crawl_id="job-failed",
            status=DeletionStatus.FAILED,
            reason=DeletionReason.OUTCOME_FAILED,
            finish_request_digest="f" * 64,
        ),
    )
    before = snapshot(deletions_store)

    assert crawl_runs.fail_unfinished_crawls_after_restart() == 0

    assert snapshot(deletions_store) == before


def test_all_sources_are_cleaned_up(crawl_runs: CrawlRuns, deletions_store: InMemoryStore) -> None:
    seed_result(deletions_store, received("job-1", source_id="src-1"))
    seed_result(deletions_store, received("job-2", source_id="src-2"))

    assert crawl_runs.fail_unfinished_crawls_after_restart() == 2

    for crawl_id in ("job-1", "job-2"):
        assert stored_result(deletions_store, crawl_id).status is DeletionStatus.FAILED


def test_cleanup_is_idempotent(crawl_runs: CrawlRuns, deletions_store: InMemoryStore) -> None:
    seed_result(deletions_store, received("job-a"))
    crawl_runs.fail_unfinished_crawls_after_restart()
    before = snapshot(deletions_store)
    writes = len(deletions_store.write_calls())

    assert crawl_runs.fail_unfinished_crawls_after_restart() == 0

    assert snapshot(deletions_store) == before
    assert len(deletions_store.write_calls()) == writes


def test_empty_store_needs_no_writes(crawl_runs: CrawlRuns, deletions_store: InMemoryStore) -> None:
    assert crawl_runs.fail_unfinished_crawls_after_restart() == 0
    assert deletions_store.write_calls() == []


def test_old_terminal_results_are_pruned_after_the_cleanup(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    """保持件数 N(3)。整理で終端状態が増えたら、古いものから消える。"""
    for number in range(3):
        seed_result(
            deletions_store,
            make_result(
                crawl_id=f"job-done-{number}",
                status=DeletionStatus.DELETED,
                ended_at=T0 - timedelta(days=number + 1),
            ),
        )
    seed_result(deletions_store, received("job-a"))

    crawl_runs.fail_unfinished_crawls_after_restart()

    assert deletions_store.body_of(deletion_result_record_id("job-done-2")) is None
    assert deletions_store.body_of(deletion_result_record_id("job-a")) is not None


# --- 書き込みの 409 ---


def test_conflict_rereads_and_still_fails_the_result(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, received("job-a"))
    record_id = deletion_result_record_id("job-a")
    deletions_store.behavior.before(
        ops.REPLACE,
        lambda: deletions_store.seed(
            record_id, received("job-a", deletion_started_at=T0).to_body()
        ),
        key=record_id,
    )

    crawl_runs.fail_unfinished_crawls_after_restart()

    result = stored_result(deletions_store, "job-a")
    assert result.reason is DeletionReason.INDEXER_RESTART
    assert result.deletion_started_at == T0  # 読み直した版を元にしている


def test_a_result_that_became_terminal_during_the_cleanup_is_left_as_it_is(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, received("job-a"))
    record_id = deletion_result_record_id("job-a")
    discarded = received(
        "job-a", status=DeletionStatus.DISCARDED, reason=DeletionReason.SOURCE_DELETED
    )
    deletions_store.behavior.before(
        ops.REPLACE, lambda: deletions_store.seed(record_id, discarded.to_body()), key=record_id
    )

    assert crawl_runs.fail_unfinished_crawls_after_restart() == 0

    assert stored_result(deletions_store, "job-a").reason is DeletionReason.SOURCE_DELETED


def test_conflicts_beyond_the_reread_limit_stop_the_cleanup(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, received("job-a"))
    deletions_store.behavior.inject(
        ops.REPLACE, Conflict(), key=deletion_result_record_id("job-a"), times=None
    )

    with pytest.raises(UnavailableError):
        crawl_runs.fail_unfinished_crawls_after_restart()

    assert stored_result(deletions_store, "job-a").status is DeletionStatus.RUNNING


def test_cleanup_continues_while_the_listing_is_full(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """一覧が上限いっぱいなら、残りがありうるので全部が `failed` になるまで繰り返す。"""
    monkeypatch.setattr(results, "LIST_MAX_SIZE", 2)
    monkeypatch.setattr(restart, "LIST_MAX_SIZE", 2)
    for number in range(5):
        seed_result(deletions_store, received(f"job-{number}", source_id=f"src-{number}"))

    assert crawl_runs.fail_unfinished_crawls_after_restart() == 5

    for number in range(5):
        assert stored_result(deletions_store, f"job-{number}").status is DeletionStatus.FAILED
