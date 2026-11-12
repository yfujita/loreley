"""終了通知の受理(arch 9.5、9.9、api 4.4。K25・K31・K32・K34・K35・K36・K38・K40)。

D-11・D-15・D-16・D-17・D-39・D-43・D-75(a)・D-91(a)〜(j)(m)〜(q)・D-92(a)(c) の保存側を確認する。
D-91(k)(並行する受理)は `test_serialization.py`。判定・実行(D-92(b) など)は P4。
「状態が変わらない」は、保存内容の比較(`snapshot`)と `write_calls()` で確かめる。
"""

import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from loreley_indexer.common.errors import (
    FinishContentMismatchError,
    FinishSourceMismatchError,
    UnavailableError,
)
from loreley_indexer.crawl_runs import CrawlRuns, FinishNotification
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionReason,
    DeletionStatus,
    FinishOutcome,
    deletion_result_record_id,
)
from loreley_indexer.infrastructure.opensearch import Conflict, OpenSearchUnavailableError
from tests.crawl_runs.factories import (
    CRAWL_ID,
    CRAWL_STARTED_AT,
    hex_id,
    make_failed_finish,
    make_finish,
    make_result,
    make_start,
    seed_result,
    snapshot,
    stored_result,
)
from tests.crawl_runs.lifecycle.conftest import ID_LIMIT, MAX_REREADS
from tests.fakes import in_memory_store as ops
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.in_memory_store import InMemoryStore

RESULT_ID = deletion_result_record_id(CRAWL_ID)
EARLIER = datetime(2026, 11, 9, 2, 0, 0, tzinfo=UTC)


@pytest.fixture
def running(deletions_store: InMemoryStore) -> None:
    """開始通知を受理済み(`running`、終了通知なし)の結果。"""
    seed_result(deletions_store, make_result())


def accept_enumeration(crawl_runs: CrawlRuns, **overrides: object) -> FinishNotification:
    notification = make_finish(**overrides)
    crawl_runs.finish_crawl(notification)
    return notification


# --- 受理(分岐 4: enumeration_completed) ---


@pytest.mark.usefixtures("running")
def test_enumeration_completed_is_recorded_in_one_write(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, wakes: list[str]
) -> None:
    notification = make_finish(
        skipped_document_ids=(hex_id(2), hex_id(1)), oversize_document_ids=(hex_id(9),)
    )

    crawl_runs.finish_crawl(notification)

    result = stored_result(deletions_store)
    assert result.status is DeletionStatus.RUNNING  # K43: 削除中も running のまま
    assert result.outcome is FinishOutcome.ENUMERATION_COMPLETED
    assert result.enumerated_count == 1203
    assert result.finish_received_at == DEFAULT_NOW
    assert result.finish_request_digest == notification.digest()
    assert result.skipped_document_ids == (hex_id(1), hex_id(2))  # ソート済み
    assert result.oversize_document_ids == (hex_id(9),)
    assert (result.skip_and_oversize_id_count, result.skip_and_oversize_id_limit_exceeded) == (
        3,
        False,
    )
    # ダイジェスト・受理時刻・ID 一覧は同じ 1 回の書き込みで保存する(K31)。
    assert deletions_store.write_calls() == [ops.REPLACE]
    assert wakes == ["wake"]


@pytest.mark.usefixtures("running")
def test_saved_id_lists_are_deduplicated_and_sorted(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    accept_enumeration(
        crawl_runs,
        skipped_document_ids=[hex_id(3), hex_id(1), hex_id(3)],
        oversize_document_ids=[hex_id(2), hex_id(2)],
    )

    result = stored_result(deletions_store)
    assert result.skipped_document_ids == (hex_id(1), hex_id(3))
    assert result.oversize_document_ids == (hex_id(2),)


@pytest.mark.usefixtures("running")
def test_empty_id_lists_are_saved_as_empty_not_as_missing(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    accept_enumeration(crawl_runs, skipped_document_ids=(), oversize_document_ids=())

    result = stored_result(deletions_store)
    assert result.skipped_document_ids == ()
    assert result.oversize_document_ids == ()


@pytest.mark.usefixtures("running")
def test_received_time_is_the_time_of_acceptance_not_the_crawler_finished_at(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    accept_enumeration(crawl_runs, finished_at=CRAWL_STARTED_AT + timedelta(days=30))

    assert stored_result(deletions_store).finish_received_at == DEFAULT_NOW


def test_id_lists_of_a_waiting_result_are_kept_apart_from_other_results(  # D-92(a)
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    """待機中の B の ID 一覧は B の結果に保存され、実行中の A のものと混ざらない。"""
    running_a = make_result(
        crawl_id="job-a",
        finish_received_at=EARLIER,
        finish_request_digest="a" * 64,
        skipped_document_ids=(hex_id(100), hex_id(101)),
        oversize_document_ids=(),
    )
    seed_result(deletions_store, running_a)
    seed_result(deletions_store, make_result(crawl_id="job-b"))
    a_before = deletions_store.body_of(deletion_result_record_id("job-a"))

    crawl_runs.finish_crawl(
        make_finish(
            crawl_id="job-b",
            skipped_document_ids=(hex_id(1), hex_id(2), hex_id(3)),
            oversize_document_ids=(hex_id(4),),
        )
    )

    result_b = stored_result(deletions_store, "job-b")
    assert result_b.skipped_document_ids == (hex_id(1), hex_id(2), hex_id(3))
    assert result_b.oversize_document_ids == (hex_id(4),)
    assert deletions_store.body_of(deletion_result_record_id("job-a")) == a_before


# --- ID 一覧の上限(K34。D-92(c) の保存側) ---


@pytest.mark.usefixtures("running")
def test_id_lists_at_the_limit_are_saved(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    accept_enumeration(
        crawl_runs,
        skipped_document_ids=tuple(hex_id(n) for n in range(3)),
        oversize_document_ids=tuple(hex_id(n) for n in range(10, 10 + ID_LIMIT - 3)),
    )

    result = stored_result(deletions_store)
    assert result.skip_and_oversize_id_count == ID_LIMIT
    assert result.skip_and_oversize_id_limit_exceeded is False
    assert result.skipped_document_ids is not None


@pytest.mark.usefixtures("running")
def test_id_lists_over_the_limit_are_accepted_but_not_saved(  # D-92(c)、K34
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, wakes: list[str]
) -> None:
    """合算件数が上限を超えても 202(例外なし)。一覧は保存せず、件数と超過だけを残す。"""
    notification = accept_enumeration(
        crawl_runs,
        skipped_document_ids=tuple(hex_id(n) for n in range(3)),
        oversize_document_ids=tuple(hex_id(n) for n in range(10, 10 + ID_LIMIT - 2)),
    )

    result = stored_result(deletions_store)
    assert result.status is DeletionStatus.RUNNING  # 判定の順番が来るまで running のまま
    assert result.skipped_document_ids is None
    assert result.oversize_document_ids is None
    assert result.skip_and_oversize_id_count == ID_LIMIT + 1
    assert result.skip_and_oversize_id_limit_exceeded is True
    assert result.finish_received_at == DEFAULT_NOW
    assert result.finish_request_digest == notification.digest()
    assert wakes == ["wake"]


@pytest.mark.usefixtures("running")
def test_the_limit_counts_each_list_after_deduplication(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    """重複を除いた件数で数える。重複込みの入力件数が上限を超えても、保存できる。"""
    ids = [hex_id(1)] * (ID_LIMIT + 3)
    accept_enumeration(crawl_runs, skipped_document_ids=ids, oversize_document_ids=())

    result = stored_result(deletions_store)
    assert result.skip_and_oversize_id_count == 1
    assert result.skipped_document_ids == (hex_id(1),)


@pytest.mark.usefixtures("running")
def test_over_limit_resend_is_compared_by_the_digest_even_though_ids_are_not_saved(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    ids = tuple(hex_id(n) for n in range(ID_LIMIT + 1))
    accept_enumeration(crawl_runs, skipped_document_ids=ids)
    before = snapshot(deletions_store)

    crawl_runs.finish_crawl(make_finish(skipped_document_ids=ids))  # 同じ内容
    with pytest.raises(FinishContentMismatchError):
        crawl_runs.finish_crawl(make_finish(skipped_document_ids=ids[:-1]))

    assert snapshot(deletions_store) == before


# --- failed・cancelled(分岐 3。D-17、D-43、K36) ---


@pytest.mark.usefixtures("running")
@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        (FinishOutcome.FAILED, DeletionReason.OUTCOME_FAILED),
        (FinishOutcome.CANCELLED, DeletionReason.OUTCOME_CANCELLED),
    ],
)
def test_failed_and_cancelled_become_failed_at_once_with_only_the_digest(  # D-17、K36
    crawl_runs: CrawlRuns,
    deletions_store: InMemoryStore,
    wakes: list[str],
    outcome: FinishOutcome,
    reason: DeletionReason,
) -> None:
    notification = make_failed_finish(
        outcome,
        # ID 一覧を含めて送られても保存しない。
        skipped_document_ids=(hex_id(1),),
        oversize_document_ids=(hex_id(2),),
        enumerated_count=10,
    )

    crawl_runs.finish_crawl(notification)

    result = stored_result(deletions_store)
    assert result.status is DeletionStatus.FAILED
    assert result.reason is reason
    assert result.outcome is outcome
    assert result.finish_received_at is None  # 受理の根拠は status と reason
    assert result.finish_request_digest == notification.digest()
    assert result.skipped_document_ids is None
    assert result.oversize_document_ids is None
    assert result.skip_and_oversize_id_count is None
    assert result.ended_at == DEFAULT_NOW
    assert deletions_store.write_calls() == [ops.REPLACE]
    assert wakes == []  # 待ち行列に入らない


def test_failed_does_not_wait_for_a_running_deletion_and_leaves_it_alone(  # D-43
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    executing = make_result(
        crawl_id="job-a",
        finish_received_at=EARLIER,
        finish_request_digest="a" * 64,
        deletion_started_at=EARLIER,
    )
    seed_result(deletions_store, executing)
    seed_result(deletions_store, make_result(crawl_id="job-b"))
    a_before = deletions_store.body_of(deletion_result_record_id("job-a"))

    crawl_runs.finish_crawl(make_failed_finish(crawl_id="job-b"))

    assert stored_result(deletions_store, "job-b").status is DeletionStatus.FAILED
    assert deletions_store.body_of(deletion_result_record_id("job-a")) == a_before


# --- 未知の crawl_id(分岐 2。D-16、案 16) ---


@pytest.mark.parametrize("make", [make_finish, make_failed_finish])
def test_unknown_crawl_id_is_discarded_without_creating_a_result(  # D-16
    crawl_runs: CrawlRuns,
    deletions_store: InMemoryStore,
    wakes: list[str],
    caplog: pytest.LogCaptureFixture,
    make,
) -> None:
    with caplog.at_level(logging.DEBUG):
        crawl_runs.finish_crawl(make(crawl_id="job-unknown", source_id="whatever-source"))

    assert deletions_store.record_ids() == []
    assert deletions_store.write_calls() == []
    assert wakes == []
    assert any("job-unknown" in message for message in caplog.messages)


def test_unknown_crawl_log_carries_only_the_id(
    crawl_runs: CrawlRuns, caplog: pytest.LogCaptureFixture
) -> None:
    """R9: ログに出すのは `crawl_id` だけ(ID 一覧・件数・`source_id` は出さない)。"""
    notification = make_finish(
        crawl_id="job-unknown",
        source_id="source-for-log-check",
        skipped_document_ids=(hex_id(77),),
    )

    with caplog.at_level(logging.DEBUG):
        crawl_runs.finish_crawl(notification)

    logged = " ".join(caplog.messages)
    assert "job-unknown" in logged
    assert "source-for-log-check" not in logged
    assert hex_id(77) not in logged
    assert "1203" not in logged


# --- 遅れた通知(分岐 1。D-11、D-91(h)) ---


@pytest.mark.parametrize(
    "terminal",
    [
        make_result(status=DeletionStatus.DISCARDED, reason=DeletionReason.SUPERSEDED),  # h1
        make_result(status=DeletionStatus.DISCARDED, reason=DeletionReason.SOURCE_DELETED),  # h2
    ],
    ids=["superseded", "source-deleted"],
)
@pytest.mark.parametrize("make", [make_finish, make_failed_finish], ids=["completed", "failed"])
def test_late_finish_for_a_result_without_a_digest_changes_nothing(  # D-11、D-91(h)
    crawl_runs: CrawlRuns,
    deletions_store: InMemoryStore,
    wakes: list[str],
    terminal,
    make,
) -> None:
    """最初の通知が未受理(ダイジェストなし)で終端状態なら、内容を問わず 202 で何もしない。"""
    seed_result(deletions_store, terminal)
    before = snapshot(deletions_store)

    crawl_runs.finish_crawl(make())
    crawl_runs.finish_crawl(make(enumerated_count=1) if make is make_finish else make())

    assert snapshot(deletions_store) == before  # ダイジェストも保存されない
    assert deletions_store.write_calls() == []
    assert wakes == []


# --- source_id の事前照合(K32。D-91(m)(p)(q)) ---


def received_states() -> dict[str, object]:
    """`source_id` の照合が、結果の状態にかかわらず行われることの確認用(m1〜m4)。"""
    notification = make_finish()
    return {
        "failed-received": make_result(
            status=DeletionStatus.FAILED,
            reason=DeletionReason.OUTCOME_FAILED,
            finish_request_digest="f" * 64,
        ),
        "completed-received-waiting": make_result(
            finish_received_at=EARLIER, finish_request_digest=notification.digest()
        ),
        "late-terminal": make_result(
            status=DeletionStatus.DISCARDED, reason=DeletionReason.SUPERSEDED
        ),
        "unreceived-running": make_result(),
    }


@pytest.mark.parametrize("state", list(received_states()))
@pytest.mark.parametrize("make", [make_finish, make_failed_finish], ids=["completed", "failed"])
def test_source_id_mismatch_is_rejected_in_every_state_without_any_write(  # D-91(m)(p)
    crawl_runs: CrawlRuns,
    deletions_store: InMemoryStore,
    wakes: list[str],
    state: str,
    make,
) -> None:
    seed_result(deletions_store, received_states()[state])
    before = snapshot(deletions_store)

    with pytest.raises(FinishSourceMismatchError):
        crawl_runs.finish_crawl(make(source_id="src-other"))

    assert snapshot(deletions_store) == before
    assert deletions_store.write_calls() == []
    assert wakes == []


@pytest.mark.usefixtures("running")
def test_correct_finish_is_accepted_after_a_source_id_mismatch(  # D-91(m4)
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    with pytest.raises(FinishSourceMismatchError):
        crawl_runs.finish_crawl(make_finish(source_id="src-other"))
    mismatched = stored_result(deletions_store)
    assert mismatched.finish_request_digest is None
    assert mismatched.finish_received_at is None
    assert mismatched.skipped_document_ids is None

    notification = accept_enumeration(crawl_runs)

    accepted = stored_result(deletions_store)
    assert accepted.finish_request_digest == notification.digest()
    assert accepted.skipped_document_ids == (hex_id(1), hex_id(2))


def test_source_id_mismatch_wins_over_a_content_mismatch(  # D-91(q)
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, received_states()["completed-received-waiting"])

    with pytest.raises(FinishSourceMismatchError):
        crawl_runs.finish_crawl(make_finish(source_id="src-other", enumerated_count=1))


def test_malformed_notification_is_rejected_before_the_source_id_is_looked_at(  # D-91(o)
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    """形式の検証(400)は `source_id` の照合(409)より先。通知を作れず、何も読み書きしない。"""
    seed_result(deletions_store, make_result())
    before = snapshot(deletions_store)

    with pytest.raises(ValueError):
        make_finish(source_id="src-other", enumerated_count=None)

    assert snapshot(deletions_store) == before
    assert deletions_store.behavior.calls == []


# --- 再送(K25、K40。D-15、D-39、D-75(a)、D-91) ---


@pytest.mark.usefixtures("running")
def test_same_resend_is_idempotent_and_ignores_finished_at(  # D-15、D-75(a)、D-91(a)
    crawl_runs: CrawlRuns,
    deletions_store: InMemoryStore,
    clock: FixedClock,
    wakes: list[str],
) -> None:
    accept_enumeration(crawl_runs)
    before = snapshot(deletions_store)
    clock.advance(seconds=60)

    crawl_runs.finish_crawl(make_finish(finished_at=CRAWL_STARTED_AT + timedelta(hours=5)))

    assert snapshot(deletions_store) == before  # finish_received_at も書き換えない
    assert deletions_store.write_calls() == [ops.REPLACE]  # 最初の受理の 1 回だけ
    assert wakes == ["wake"]


@pytest.mark.usefixtures("running")
def test_resend_with_reordered_or_duplicated_ids_has_the_same_digest(  # D-91(f)
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    accept_enumeration(
        crawl_runs, skipped_document_ids=(hex_id(1), hex_id(2)), oversize_document_ids=(hex_id(3),)
    )
    before = snapshot(deletions_store)

    crawl_runs.finish_crawl(
        make_finish(
            skipped_document_ids=[hex_id(2), hex_id(1), hex_id(2)],
            oversize_document_ids=[hex_id(3), hex_id(3)],
        )
    )

    assert snapshot(deletions_store) == before


def accepted_in_state(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, state: str
) -> FinishNotification:
    """`enumeration_completed` を受理済みで、削除結果が待機中・判定中・実行中の状態にする。"""
    seed_result(deletions_store, make_result())
    notification = accept_enumeration(crawl_runs)
    record = stored_result(deletions_store)
    if state == "waiting":
        # 先行する削除(job-a)が実行中。
        seed_result(
            deletions_store,
            make_result(crawl_id="job-a", finish_received_at=EARLIER - timedelta(hours=1)),
        )
    elif state == "judging":
        record = replace(record, deletion_started_at=DEFAULT_NOW)
    elif state == "executing":
        record = replace(record, deletion_started_at=DEFAULT_NOW, target_count=10, deleted_count=4)
    seed_result(deletions_store, record)
    return notification


@pytest.mark.parametrize("state", ["waiting", "judging", "executing"])
@pytest.mark.parametrize(
    "difference",
    [
        {"enumerated_count": 1204},
        {"skipped_document_ids": (hex_id(1),)},
        {"oversize_document_ids": (hex_id(9),)},
    ],
    ids=["enumerated_count", "skipped_document_ids", "oversize_document_ids"],
)
def test_resend_with_different_content_is_rejected_and_the_deletion_keeps_going(  # D-91(b)
    crawl_runs: CrawlRuns,
    deletions_store: InMemoryStore,
    wakes: list[str],
    state: str,
    difference: dict[str, object],
) -> None:
    accepted_in_state(crawl_runs, deletions_store, state)
    # 新しい開始通知のあとの再送。世代は見ず、`discarded` にもならない(D-39(d))。
    crawl_runs.start_crawl(
        make_start(crawl_id="job-new", crawl_started_at=CRAWL_STARTED_AT + timedelta(days=1))
    )
    before = snapshot(deletions_store)
    wakes_before = list(wakes)

    with pytest.raises(FinishContentMismatchError):
        crawl_runs.finish_crawl(make_finish(**difference))

    assert snapshot(deletions_store) == before
    assert stored_result(deletions_store).status is DeletionStatus.RUNNING
    assert wakes == wakes_before


@pytest.mark.parametrize("state", ["waiting", "judging", "executing"])
def test_same_resend_after_a_new_start_does_not_stop_the_accepted_deletion(  # D-39(a)〜(c)
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, state: str
) -> None:
    accepted_in_state(crawl_runs, deletions_store, state)
    crawl_runs.start_crawl(
        make_start(crawl_id="job-new", crawl_started_at=CRAWL_STARTED_AT + timedelta(days=1))
    )
    before = snapshot(deletions_store)

    crawl_runs.finish_crawl(make_finish())

    assert snapshot(deletions_store) == before
    assert stored_result(deletions_store).status is DeletionStatus.RUNNING


@pytest.mark.usefixtures("running")
def test_original_content_is_accepted_again_after_a_rejected_resend(  # D-91(d)
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    accept_enumeration(crawl_runs)
    with pytest.raises(FinishContentMismatchError):
        crawl_runs.finish_crawl(make_finish(enumerated_count=1))
    before = snapshot(deletions_store)

    crawl_runs.finish_crawl(make_finish())

    assert snapshot(deletions_store) == before


@pytest.mark.usefixtures("running")
@pytest.mark.parametrize("outcome", [FinishOutcome.FAILED, FinishOutcome.CANCELLED])
def test_resends_for_a_failed_or_cancelled_finish(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, outcome: FinishOutcome
) -> None:
    crawl_runs.finish_crawl(make_failed_finish(outcome))
    before = snapshot(deletions_store)

    crawl_runs.finish_crawl(make_failed_finish(outcome))  # (e) 同じ内容
    assert snapshot(deletions_store) == before

    different_outcome = (
        FinishOutcome.CANCELLED if outcome is FinishOutcome.FAILED else FinishOutcome.FAILED
    )
    with pytest.raises(FinishContentMismatchError):  # (n) outcome を変えた再送
        crawl_runs.finish_crawl(make_failed_finish(different_outcome))
    with pytest.raises(FinishContentMismatchError):  # (c) 内容が違う
        crawl_runs.finish_crawl(make_failed_finish(outcome, enumerated_count=5))
    with pytest.raises(FinishContentMismatchError):  # (i) enumeration_completed を再送
        crawl_runs.finish_crawl(make_finish())
    assert snapshot(deletions_store) == before


@pytest.mark.usefixtures("running")
def test_failed_resend_to_an_accepted_enumeration_does_not_fail_the_result(  # D-91(j)
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    accept_enumeration(crawl_runs)
    before = snapshot(deletions_store)

    for outcome in (FinishOutcome.FAILED, FinishOutcome.CANCELLED):
        with pytest.raises(FinishContentMismatchError):
            crawl_runs.finish_crawl(make_failed_finish(outcome))

    assert snapshot(deletions_store) == before
    assert stored_result(deletions_store).status is DeletionStatus.RUNNING


@pytest.mark.usefixtures("running")
def test_the_digest_survives_a_restart_so_resends_are_still_judged(  # D-91(g)、D-93
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    accept_enumeration(crawl_runs)
    crawl_runs.fail_unfinished_crawls_after_restart()
    after_restart = stored_result(deletions_store)
    assert after_restart.reason is DeletionReason.INDEXER_RESTART
    assert after_restart.skipped_document_ids is None
    before = snapshot(deletions_store)

    crawl_runs.finish_crawl(make_finish())  # g1: 同じ内容は 202
    with pytest.raises(FinishContentMismatchError):  # g2: 違う内容は 409
        crawl_runs.finish_crawl(make_finish(enumerated_count=1))

    assert snapshot(deletions_store) == before


# --- 受理の書き込みの 409(読み直して再判定する) ---


@pytest.mark.usefixtures("running")
def test_conflict_rereads_and_accepts_with_the_notifications_own_content(  # D-91(k) の読み直し
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, wakes: list[str]
) -> None:
    """別の書き手が先に同じ結果を更新(版が変わる)しても、読み直して同じ結果になる。"""
    notification = make_finish(skipped_document_ids=(hex_id(5), hex_id(4)))
    deletions_store.behavior.before(
        ops.REPLACE,
        lambda: deletions_store.seed(RESULT_ID, make_result(started_at=EARLIER).to_body()),
        key=RESULT_ID,
    )

    crawl_runs.finish_crawl(notification)

    result = stored_result(deletions_store)
    assert result.finish_request_digest == notification.digest()
    assert result.skipped_document_ids == (hex_id(4), hex_id(5))  # ダイジェストと一覧が同じ通知
    assert result.started_at == EARLIER  # 読み直した版に対する更新
    assert len(deletions_store.behavior.calls_of(ops.REPLACE)) == 2
    assert wakes == ["wake"]


@pytest.mark.usefixtures("running")
def test_conflict_on_a_failed_notification_rereads_and_records_failed(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    deletions_store.behavior.inject(ops.REPLACE, Conflict(), key=RESULT_ID, times=2)

    crawl_runs.finish_crawl(make_failed_finish())

    assert stored_result(deletions_store).status is DeletionStatus.FAILED


@pytest.mark.usefixtures("running")
def test_conflicts_beyond_the_reread_limit_write_nothing_and_are_retryable(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, wakes: list[str]
) -> None:
    before = snapshot(deletions_store)
    deletions_store.behavior.inject(ops.REPLACE, Conflict(), key=RESULT_ID, times=None)

    with pytest.raises(UnavailableError) as error:
        crawl_runs.finish_crawl(make_finish())

    assert error.value.reason == "write_conflict"
    assert len(deletions_store.behavior.calls_of(ops.REPLACE)) == 1 + MAX_REREADS
    assert snapshot(deletions_store) == before
    assert wakes == []


@pytest.mark.usefixtures("running")
def test_the_state_is_judged_again_after_a_conflict_when_another_writer_superseded_it(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, wakes: list[str]
) -> None:
    """読み直したら終端状態(`superseded`)なら、遅れた通知として何もしない(分岐 1)。"""
    superseded = make_result(status=DeletionStatus.DISCARDED, reason=DeletionReason.SUPERSEDED)
    deletions_store.behavior.before(
        ops.REPLACE, lambda: deletions_store.seed(RESULT_ID, superseded.to_body()), key=RESULT_ID
    )

    crawl_runs.finish_crawl(make_finish())

    assert stored_result(deletions_store).status is DeletionStatus.DISCARDED
    assert stored_result(deletions_store).finish_request_digest is None
    assert wakes == []


@pytest.mark.usefixtures("running")
def test_a_different_notification_accepted_during_the_conflict_makes_this_one_a_mismatch(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    """読み直したら別の内容がすでに受理されていれば、ダイジェストの不一致として拒否する。"""
    other = make_finish(enumerated_count=1)
    accepted_by_other = make_result(
        finish_received_at=EARLIER, finish_request_digest=other.digest()
    )
    deletions_store.behavior.before(
        ops.REPLACE,
        lambda: deletions_store.seed(RESULT_ID, accepted_by_other.to_body()),
        key=RESULT_ID,
    )

    with pytest.raises(FinishContentMismatchError):
        crawl_runs.finish_crawl(make_finish())

    assert stored_result(deletions_store).finish_request_digest == other.digest()


@pytest.mark.usefixtures("running")
def test_result_deleted_during_the_write_is_treated_as_an_unknown_crawl(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, wakes: list[str]
) -> None:
    deletions_store.behavior.before(
        ops.REPLACE, lambda: deletions_store.delete(RESULT_ID), key=RESULT_ID
    )

    crawl_runs.finish_crawl(make_finish())

    assert deletions_store.record_ids() == []
    assert wakes == []


@pytest.mark.usefixtures("running")
def test_wake_is_called_only_after_the_acceptance_is_persisted(
    lifecycle_config, deletions_store: InMemoryStore, clock: FixedClock
) -> None:
    observed: list[object] = []
    runs = CrawlRuns(
        config=lifecycle_config,
        deletions_store=deletions_store,
        clock=clock,
        wake=lambda: observed.append(stored_result(deletions_store).finish_received_at),
    )

    runs.finish_crawl(make_finish())

    assert observed == [DEFAULT_NOW]


@pytest.mark.usefixtures("running")
def test_a_failing_store_write_does_not_wake_the_worker(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, wakes: list[str]
) -> None:
    deletions_store.behavior.inject(
        ops.REPLACE, OpenSearchUnavailableError("connection_error"), key=RESULT_ID
    )

    with pytest.raises(OpenSearchUnavailableError):
        crawl_runs.finish_crawl(make_finish())

    assert wakes == []
    assert stored_result(deletions_store).finish_received_at is None
