"""開始通知の受理(arch 9.5、9.9、api 4.1)。

D-12・D-29・D-36・D-40(開始側)・D-79・D-80・D-94(a)〜(e)・C-27(c)(開始通知の再送側)を確認する。
「状態が変わらない」は、保存内容の比較と `write_calls()` で確かめる。
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from loreley_indexer.common.errors import (
    CrawlAlreadyFinishedError,
    CrawlStartConflictError,
    StaleCrawlStartedAtError,
    UnavailableError,
)
from loreley_indexer.crawl_runs import CrawlRuns
from loreley_indexer.crawl_runs.lifecycle import (
    AdmissionChecker,
    DeletionReason,
    DeletionStatus,
    FinishOutcome,
    deletion_record_id,
    deletion_result_record_id,
)
from loreley_indexer.infrastructure.opensearch import Conflict, OpenSearchUnavailableError
from tests.crawl_runs.factories import (
    CRAWL_ID,
    CRAWL_STARTED_AT,
    SOURCE_ID,
    make_generation,
    make_result,
    make_start,
    seed_result,
    snapshot,
    stored_generation,
    stored_result,
)
from tests.crawl_runs.lifecycle.conftest import MAX_REREADS
from tests.fakes import in_memory_store as ops
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.in_memory_store import InMemoryStore

RECEIVED_AT = datetime(2026, 11, 9, 2, 0, 0, tzinfo=UTC)
NEWER = CRAWL_STARTED_AT + timedelta(days=1)
GENERATION_ID = deletion_record_id(SOURCE_ID)


def seed_generation(store: InMemoryStore, **overrides: object) -> None:
    store.seed(GENERATION_ID, make_generation(**overrides).to_body())


# --- 受理 ---


def test_first_start_creates_a_running_result_with_the_copied_settings(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, clock: FixedClock
) -> None:
    crawl_runs.start_crawl(
        make_start(ttl=3600, ratio_threshold=0.3, min_delete_count=7, force_delete=True)
    )

    result = stored_result(deletions_store)
    assert result.status is DeletionStatus.RUNNING
    assert result.source_id == SOURCE_ID
    assert result.crawl_started_at == CRAWL_STARTED_AT
    assert (result.ttl, result.ratio_threshold, result.min_delete_count) == (3600, 0.3, 7)
    assert result.forced is True
    assert result.rewrite_mode is False
    assert result.started_at == DEFAULT_NOW
    assert result.finish_received_at is None
    assert result.finish_request_digest is None
    assert result.skipped_document_ids is None


@pytest.mark.parametrize("rewrite_mode", [True, False])
def test_rewrite_mode_is_copied_and_later_read_by_the_admission_check(  # C-27(c)
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, rewrite_mode: bool
) -> None:
    crawl_runs.start_crawl(make_start(rewrite_mode=rewrite_mode))

    assert stored_result(deletions_store).rewrite_mode is rewrite_mode
    admission = AdmissionChecker(deletions_store).check(
        source_id=SOURCE_ID, crawl_id=CRAWL_ID, crawl_started_at=CRAWL_STARTED_AT
    )
    assert admission.rewrite_mode is rewrite_mode


def test_first_start_updates_the_current_generation(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    crawl_runs.start_crawl(make_start(ttl=3600, ratio_threshold=0.3, force_delete=True))

    generation = stored_generation(deletions_store)
    assert generation.crawl_id == CRAWL_ID
    assert generation.crawl_started_at == CRAWL_STARTED_AT
    assert (generation.ttl, generation.ratio_threshold, generation.force_delete) == (
        3600,
        0.3,
        True,
    )
    assert generation.updated_at == DEFAULT_NOW


def test_a_new_start_replaces_the_generation_of_the_source(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_generation(deletions_store, crawl_id="job-old")

    crawl_runs.start_crawl(make_start(crawl_started_at=NEWER))

    assert stored_generation(deletions_store).crawl_id == CRAWL_ID
    assert stored_generation(deletions_store).crawl_started_at == NEWER


def test_a_start_with_the_same_crawl_started_at_as_the_generation_is_accepted(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_generation(deletions_store, crawl_id="job-old")

    crawl_runs.start_crawl(make_start())

    assert stored_generation(deletions_store).crawl_id == CRAWL_ID


def test_other_sources_are_independent(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    deletions_store.seed(
        deletion_record_id("src-other"),
        make_generation(source_id="src-other", crawl_started_at=NEWER).to_body(),
    )

    crawl_runs.start_crawl(make_start())

    assert stored_result(deletions_store).status is DeletionStatus.RUNNING


def test_start_does_not_wake_the_deletion_worker(crawl_runs: CrawlRuns, wakes: list[str]) -> None:
    crawl_runs.start_crawl(make_start())
    assert wakes == []


# --- 世代の判定(判定 3。D-29) ---


def test_older_crawl_started_at_than_the_generation_is_rejected(  # D-29
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_generation(deletions_store, crawl_id="job-newer", crawl_started_at=NEWER)
    before = snapshot(deletions_store)

    with pytest.raises(StaleCrawlStartedAtError):
        crawl_runs.start_crawl(make_start())

    assert snapshot(deletions_store) == before
    assert deletions_store.write_calls() == []


@pytest.mark.parametrize(
    ("started_at", "is_stale"),
    [
        (datetime(2026, 11, 9, 1, 0, 0, 99_000, tzinfo=UTC), True),  # 1 ミリ秒以上前
        (datetime(2026, 11, 9, 1, 0, 0, 100_999, tzinfo=UTC), False),  # 同じミリ秒
    ],
)
def test_staleness_is_judged_in_milliseconds(
    crawl_runs: CrawlRuns,
    deletions_store: InMemoryStore,
    started_at: datetime,
    is_stale: bool,
) -> None:
    seed_generation(
        deletions_store,
        crawl_id="job-newer",
        crawl_started_at=datetime(2026, 11, 9, 1, 0, 0, 100_000, tzinfo=UTC),
    )

    if is_stale:
        with pytest.raises(StaleCrawlStartedAtError):
            crawl_runs.start_crawl(make_start(crawl_started_at=started_at))
    else:
        crawl_runs.start_crawl(make_start(crawl_started_at=started_at))


def test_a_stale_start_supersedes_nothing(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_generation(deletions_store, crawl_id="job-newer", crawl_started_at=NEWER)
    seed_result(deletions_store, make_result(crawl_id="job-unfinished"))

    with pytest.raises(StaleCrawlStartedAtError):
        crawl_runs.start_crawl(make_start())

    assert stored_result(deletions_store, "job-unfinished").status is DeletionStatus.RUNNING


# --- 終端状態の結果(判定 1。D-29) ---


@pytest.mark.parametrize(
    "status",
    [
        DeletionStatus.DELETED,
        DeletionStatus.SKIPPED_BY_RATIO,
        DeletionStatus.VALIDATION_FAILED,
        DeletionStatus.DISCARDED,
        DeletionStatus.FAILED,
    ],
)
def test_a_start_for_a_finished_crawl_is_rejected(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, status: DeletionStatus
) -> None:  # D-29
    seed_result(deletions_store, make_result(status=status))
    seed_generation(deletions_store)
    before = snapshot(deletions_store)

    with pytest.raises(CrawlAlreadyFinishedError):
        crawl_runs.start_crawl(make_start())

    assert snapshot(deletions_store) == before
    assert deletions_store.write_calls() == []


def test_finished_check_comes_before_the_resend_comparison_and_the_stale_check(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    """終端なら、内容が違っても世代が古くても `crawl_already_finished`(判定の順序)。"""
    seed_result(deletions_store, make_result(status=DeletionStatus.DELETED, ttl=1))
    seed_generation(deletions_store, crawl_id="job-newer", crawl_started_at=NEWER)

    with pytest.raises(CrawlAlreadyFinishedError):
        crawl_runs.start_crawl(make_start(ttl=999))


# --- 再送(判定 2。D-79、D-80、D-94、C-27(c)) ---


@pytest.mark.parametrize("rewrite_mode", [True, False])
def test_identical_resend_succeeds_without_changing_anything(  # D-79(a)、C-27(c)
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, rewrite_mode: bool
) -> None:
    crawl_runs.start_crawl(make_start(rewrite_mode=rewrite_mode, force_delete=True))
    before = snapshot(deletions_store)
    writes_before = len(deletions_store.write_calls())

    crawl_runs.start_crawl(make_start(rewrite_mode=rewrite_mode, force_delete=True))

    assert snapshot(deletions_store) == before
    assert len(deletions_store.write_calls()) == writes_before


def test_resend_of_an_old_crawl_after_the_generation_moved_on_is_idempotent(  # D-79(b)
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    """判定 2 が判定 3 より先に働く。世代は巻き戻らず、旧い結果は止まらない。"""
    seed_result(deletions_store, make_result(finish_received_at=RECEIVED_AT))
    seed_generation(deletions_store, crawl_id="job-newer", crawl_started_at=NEWER)
    before = snapshot(deletions_store)

    crawl_runs.start_crawl(make_start())  # CRAWL_STARTED_AT は現行世代より古い

    assert snapshot(deletions_store) == before
    assert stored_generation(deletions_store).crawl_id == "job-newer"
    assert deletions_store.write_calls() == []


def test_a_differing_resend_is_a_conflict_not_a_stale_rejection(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result())
    seed_generation(deletions_store, crawl_id="job-newer", crawl_started_at=NEWER)

    with pytest.raises(CrawlStartConflictError):
        crawl_runs.start_crawl(make_start(ttl=1))


@pytest.mark.parametrize(
    "overrides",
    [
        {"crawl_started_at": datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone(timedelta(hours=9)))},
        {"crawl_started_at": datetime(2026, 11, 9, 1, 0, 0, 999, tzinfo=UTC)},  # ミリ秒未満
        {"ratio_threshold": 0.2},
    ],
)
def test_resend_with_another_notation_of_the_same_values_is_idempotent(  # D-79(c)
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, overrides: dict[str, object]
) -> None:
    """比較は正規化後の値の完全一致。表記だけの違いでは 409 にしない(案 14。寛容側に倒した)。"""
    seed_result(deletions_store, make_result())

    crawl_runs.start_crawl(make_start(**overrides))

    assert deletions_store.write_calls() == []


def test_an_integer_ratio_threshold_equals_the_same_stored_number(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result(ratio_threshold=1.0))

    crawl_runs.start_crawl(make_start(ratio_threshold=1))

    assert deletions_store.write_calls() == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_id": "src-other"},
        {"crawl_started_at": CRAWL_STARTED_AT + timedelta(milliseconds=1)},
        {"ttl": 86_401},
        {"ratio_threshold": 0.21},
        {"min_delete_count": 11},
        {"force_delete": True},
    ],
    ids=["source_id", "crawl_started_at", "ttl", "ratio_threshold", "min_delete_count", "force"],
)
def test_resend_with_one_differing_item_is_a_conflict(  # D-80
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, overrides: dict[str, object]
) -> None:
    seed_result(deletions_store, make_result())
    seed_generation(deletions_store)
    before = snapshot(deletions_store)

    with pytest.raises(CrawlStartConflictError):
        crawl_runs.start_crawl(make_start(**overrides))

    assert snapshot(deletions_store) == before
    assert deletions_store.write_calls() == []


@pytest.mark.parametrize(
    ("first", "resent"),
    [
        (True, False),  # (a)
        (False, True),  # (b)
        (None, True),  # (c) 最初が指定なし
        (True, None),  # (d) 再送が指定なし
    ],
    ids=["true-to-false", "false-to-true", "omitted-to-true", "true-to-omitted"],
)
def test_resend_with_a_different_rewrite_mode_is_a_conflict(  # D-94(a)〜(d)
    crawl_runs: CrawlRuns,
    deletions_store: InMemoryStore,
    first: bool | None,
    resent: bool | None,
) -> None:
    """省略は `false` に正規化されるので、省略と `true` の違いも 409 になる(K37)。"""
    crawl_runs.start_crawl(_with_rewrite_mode(first))
    before = snapshot(deletions_store)

    with pytest.raises(CrawlStartConflictError):
        crawl_runs.start_crawl(_with_rewrite_mode(resent))

    assert snapshot(deletions_store) == before
    # 同じ crawl_id のバッチ登録は、最初の rewrite_mode のまま処理される。
    admission = AdmissionChecker(deletions_store).check(
        source_id=SOURCE_ID, crawl_id=CRAWL_ID, crawl_started_at=CRAWL_STARTED_AT
    )
    assert admission.rewrite_mode is bool(first)


def test_omitted_and_false_rewrite_modes_are_the_same_value(  # D-94(e)
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    crawl_runs.start_crawl(_with_rewrite_mode(None))
    before = snapshot(deletions_store)

    crawl_runs.start_crawl(_with_rewrite_mode(False))

    assert snapshot(deletions_store) == before
    assert stored_result(deletions_store).rewrite_mode is False


def _with_rewrite_mode(rewrite_mode: bool | None):
    return make_start() if rewrite_mode is None else make_start(rewrite_mode=rewrite_mode)


# --- 旧い結果の整理(D-12、D-40(開始側)) ---


def test_an_unfinished_old_result_is_superseded(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, clock: FixedClock
) -> None:
    seed_result(deletions_store, make_result(crawl_id="job-old", started_at=RECEIVED_AT))
    clock.advance(seconds=30)

    crawl_runs.start_crawl(make_start())

    old = stored_result(deletions_store, "job-old")
    assert old.status is DeletionStatus.DISCARDED
    assert old.reason is DeletionReason.SUPERSEDED
    assert old.ended_at == DEFAULT_NOW + timedelta(seconds=30)
    assert stored_result(deletions_store).status is DeletionStatus.RUNNING


def test_a_result_with_a_received_finish_is_not_stopped_or_discarded(  # D-12、9.9 項4
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    """待機中・判定中・実行中の旧い削除は、新しい開始通知で止まらない。"""
    waiting = make_result(crawl_id="job-waiting", finish_received_at=RECEIVED_AT)
    seed_result(deletions_store, waiting)
    old_body = deletions_store.body_of(deletion_result_record_id("job-waiting"))

    crawl_runs.start_crawl(make_start(crawl_started_at=NEWER))

    assert deletions_store.body_of(deletion_result_record_id("job-waiting")) == old_body
    assert stored_result(deletions_store, "job-waiting").status is DeletionStatus.RUNNING


def test_only_the_unfinished_result_is_superseded_among_three_generations(  # D-40
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    """A(受理済みで実行中)は変わらず、B(終了通知なし)だけが `superseded` になる。"""
    seed_result(deletions_store, make_result(crawl_id="job-a", finish_received_at=RECEIVED_AT))
    seed_result(deletions_store, make_result(crawl_id="job-b"))

    crawl_runs.start_crawl(make_start(crawl_id="job-c", crawl_started_at=NEWER))

    assert stored_result(deletions_store, "job-a").status is DeletionStatus.RUNNING
    assert stored_result(deletions_store, "job-b").status is DeletionStatus.DISCARDED
    assert stored_result(deletions_store, "job-c").status is DeletionStatus.RUNNING


def test_results_that_are_already_terminal_or_failed_by_outcome_are_left_alone(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    failed = make_result(
        crawl_id="job-failed",
        status=DeletionStatus.FAILED,
        reason=DeletionReason.OUTCOME_FAILED,
        outcome=FinishOutcome.FAILED,
        finish_request_digest="d" * 64,
    )
    deleted = make_result(crawl_id="job-deleted", status=DeletionStatus.DELETED)
    seed_result(deletions_store, failed)
    seed_result(deletions_store, deleted)
    before = snapshot(deletions_store)

    crawl_runs.start_crawl(make_start(crawl_started_at=NEWER))

    for crawl_id in ("job-failed", "job-deleted"):
        record_id = deletion_result_record_id(crawl_id)
        assert deletions_store.body_of(record_id) == before[record_id]


def test_results_of_other_sources_are_not_superseded(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result(crawl_id="job-other", source_id="src-other"))

    crawl_runs.start_crawl(make_start())

    assert stored_result(deletions_store, "job-other").status is DeletionStatus.RUNNING


def test_old_results_are_pruned_to_the_retention_count_after_superseding(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, clock: FixedClock
) -> None:
    """`superseded` も終端状態なので、保持件数 N(3)を超えた古い終端状態の結果が消える。"""
    for number in range(3):
        seed_result(
            deletions_store,
            make_result(
                crawl_id=f"job-done-{number}",
                status=DeletionStatus.DELETED,
                ended_at=RECEIVED_AT + timedelta(minutes=number),
            ),
        )
    seed_result(deletions_store, make_result(crawl_id="job-old"))
    clock.advance(seconds=10)

    crawl_runs.start_crawl(make_start())

    remaining = {record_id for record_id in deletions_store.record_ids() if "job-done" in record_id}
    assert remaining == {
        deletion_result_record_id("job-done-1"),
        deletion_result_record_id("job-done-2"),
    }
    assert stored_result(deletions_store, "job-old").status is DeletionStatus.DISCARDED


# --- 失敗からの再送(書き込みの順序) ---


def test_a_start_that_failed_before_the_result_was_created_succeeds_when_resent(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    """結果の作成が最後のコミット点。途中で落ちても、再送で世代の更新と整理が済む。"""
    seed_result(deletions_store, make_result(crawl_id="job-old"))
    deletions_store.behavior.inject(
        ops.SAVE,
        OpenSearchUnavailableError("connection_error"),
        key=deletion_result_record_id(CRAWL_ID),
    )

    with pytest.raises(OpenSearchUnavailableError):
        crawl_runs.start_crawl(make_start())
    assert deletions_store.body_of(deletion_result_record_id(CRAWL_ID)) is None

    crawl_runs.start_crawl(make_start())

    assert stored_result(deletions_store).status is DeletionStatus.RUNNING
    assert stored_generation(deletions_store).crawl_id == CRAWL_ID
    assert stored_result(deletions_store, "job-old").status is DeletionStatus.DISCARDED


# --- 書き込みの 409(読み直して再判定する) ---


def test_generation_conflict_rereads_and_succeeds(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_generation(deletions_store, crawl_id="job-old")
    deletions_store.behavior.before(
        ops.REPLACE,
        lambda: seed_generation(deletions_store, crawl_id="job-other-writer"),
        key=GENERATION_ID,
    )

    crawl_runs.start_crawl(make_start())

    assert stored_generation(deletions_store).crawl_id == CRAWL_ID
    assert stored_result(deletions_store).status is DeletionStatus.RUNNING


def test_generation_is_judged_again_after_a_conflict(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    """読み直した世代が新しければ、古い通知として拒否する(判定 3 を読み直しのたびにやり直す)。"""
    seed_generation(deletions_store, crawl_id="job-old")
    deletions_store.behavior.before(
        ops.REPLACE,
        lambda: seed_generation(deletions_store, crawl_id="job-newer", crawl_started_at=NEWER),
        key=GENERATION_ID,
    )

    with pytest.raises(StaleCrawlStartedAtError):
        crawl_runs.start_crawl(make_start())

    assert stored_generation(deletions_store).crawl_id == "job-newer"
    assert deletions_store.body_of(deletion_result_record_id(CRAWL_ID)) is None


def test_generation_conflicts_beyond_the_reread_limit_write_nothing_and_are_retryable(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_generation(deletions_store, crawl_id="job-old")
    deletions_store.behavior.inject(ops.REPLACE, Conflict(), key=GENERATION_ID, times=None)

    with pytest.raises(UnavailableError) as error:
        crawl_runs.start_crawl(make_start())

    assert error.value.reason == "write_conflict"
    replace_calls = deletions_store.behavior.calls_of(ops.REPLACE)
    assert len(replace_calls) == 1 + MAX_REREADS
    assert deletions_store.body_of(deletion_result_record_id(CRAWL_ID)) is None


def test_supersede_conflict_with_a_source_deletion_leaves_the_discarded_result(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    """`superseded` にする書き込みが 409 でも、読み直して終端状態なら上書きしない。"""
    seed_result(deletions_store, make_result(crawl_id="job-old"))
    discarded = make_result(
        crawl_id="job-old", status=DeletionStatus.DISCARDED, reason=DeletionReason.SOURCE_DELETED
    )
    deletions_store.behavior.before(
        ops.REPLACE,
        lambda: seed_result(deletions_store, discarded),
        key=deletion_result_record_id("job-old"),
    )

    crawl_runs.start_crawl(make_start())

    assert stored_result(deletions_store, "job-old").reason is DeletionReason.SOURCE_DELETED


def test_supersede_is_skipped_when_the_finish_was_accepted_before_the_reread(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    """読み直したら終了通知を受理済みの結果は、`superseded` にしない(arch 9.9 項4)。"""
    seed_result(deletions_store, make_result(crawl_id="job-old"))
    accepted = replace(make_result(crawl_id="job-old"), finish_received_at=RECEIVED_AT)
    deletions_store.behavior.before(
        ops.REPLACE,
        lambda: seed_result(deletions_store, accepted),
        key=deletion_result_record_id("job-old"),
    )

    crawl_runs.start_crawl(make_start())

    assert stored_result(deletions_store, "job-old").status is DeletionStatus.RUNNING
    assert stored_result(deletions_store, "job-old").finish_received_at == RECEIVED_AT


def test_supersede_conflicts_beyond_the_reread_limit_do_not_create_the_result(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result(crawl_id="job-old"))
    deletions_store.behavior.inject(
        ops.REPLACE, Conflict(), key=deletion_result_record_id("job-old"), times=None
    )

    with pytest.raises(UnavailableError):
        crawl_runs.start_crawl(make_start())

    assert deletions_store.body_of(deletion_result_record_id(CRAWL_ID)) is None
