"""開始・終了の受理のソース単位の直列化(arch 9.9 項 4、案 19)。D-40、D-91(k)。

直列キューの一時停止の代わりに、処理中の書き込みの直前でゲートを使って 1 つ目の処理を止め、
2 つ目を始めて待たされていることを確かめてから再開する(arch 16.1。実際の競争に頼らない)。
成功の判定に時間は使わない(待たされていることの確認に短い待ちを使うだけ)。
"""

from datetime import UTC, datetime, timedelta

from loreley_indexer.common.errors import FinishContentMismatchError
from loreley_indexer.crawl_runs import CrawlRuns
from loreley_indexer.crawl_runs.lifecycle import DeletionStatus, deletion_result_record_id
from tests.crawl_runs.factories import (
    CRAWL_STARTED_AT,
    hex_id,
    make_finish,
    make_result,
    make_start,
    seed_result,
    stored_result,
)
from tests.fakes import in_memory_store as ops
from tests.fakes.concurrency import Background
from tests.fakes.gate import Gate
from tests.fakes.in_memory_store import InMemoryStore

T0 = datetime(2026, 11, 9, 1, 20, 5, tzinfo=UTC)
NEWER = CRAWL_STARTED_AT + timedelta(days=1)


def pause_before_write(store: InMemoryStore, crawl_id: str) -> Gate:
    """`crawl_id` の結果の次の置き換えの直前で、呼び出し元のスレッドを止める。"""
    gate = Gate()
    store.behavior.before(ops.REPLACE, gate.pass_through, key=deletion_result_record_id(crawl_id))
    return gate


def seed_old_generations(store: InMemoryStore) -> None:
    """A: 終了通知を受理済みで実行中、B: 終了通知が届いていない(D-40 の前提)。"""
    seed_result(
        store,
        make_result(
            crawl_id="job-a",
            finish_received_at=T0,
            finish_request_digest="a" * 64,
            deletion_started_at=T0,
        ),
    )
    seed_result(store, make_result(crawl_id="job-b"))


def test_a_start_waits_for_a_finish_acceptance_in_progress_and_does_not_supersede_it(  # D-40
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, wakes: list[str]
) -> None:
    """B の終了通知の受理の途中に C の開始通知が来ても、受理済みの B は `superseded` にならない。"""
    seed_old_generations(deletions_store)
    gate = pause_before_write(deletions_store, "job-b")
    finish_b = Background(lambda: crawl_runs.finish_crawl(make_finish(crawl_id="job-b")))
    gate.wait_until_arrived()
    start_c = Background(
        lambda: crawl_runs.start_crawl(make_start(crawl_id="job-c", crawl_started_at=NEWER))
    )

    assert start_c.is_blocked()  # B の受理が終わるまで始まらない
    gate.release()
    finish_b.join()
    start_c.join()

    assert finish_b.error is None and start_c.error is None
    result_b = stored_result(deletions_store, "job-b")
    assert result_b.status is DeletionStatus.RUNNING
    assert result_b.finish_received_at is not None  # 受理済みの B は止まらない
    assert stored_result(deletions_store, "job-a").status is DeletionStatus.RUNNING
    assert stored_result(deletions_store, "job-c").status is DeletionStatus.RUNNING
    assert wakes == ["wake"]


def test_a_finish_waits_for_a_start_in_progress_and_then_sees_the_superseded_result(  # D-40
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, wakes: list[str]
) -> None:
    """C の開始通知の処理の途中(B を `superseded` にする直前)に B の終了通知が来た場合。"""
    seed_old_generations(deletions_store)
    gate = pause_before_write(deletions_store, "job-b")
    start_c = Background(
        lambda: crawl_runs.start_crawl(make_start(crawl_id="job-c", crawl_started_at=NEWER))
    )
    gate.wait_until_arrived()
    finish_b = Background(lambda: crawl_runs.finish_crawl(make_finish(crawl_id="job-b")))

    assert finish_b.is_blocked()
    gate.release()
    start_c.join()
    finish_b.join()

    assert finish_b.error is None  # 遅れた通知として 202(何もしない)
    result_b = stored_result(deletions_store, "job-b")
    assert result_b.status is DeletionStatus.DISCARDED
    assert result_b.finish_request_digest is None
    assert result_b.finish_received_at is None
    assert wakes == []
    assert stored_result(deletions_store, "job-a").status is DeletionStatus.RUNNING


def test_concurrent_resends_are_judged_against_the_first_accepted_notification(  # D-91(k)
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore, wakes: list[str]
) -> None:
    """最初の受理の途中に、同内容の再送と違う内容の再送が来る。先に入った通知だけが受理される。"""
    seed_result(deletions_store, make_result())
    gate = pause_before_write(deletions_store, "job-20261109-0001")
    first = make_finish(skipped_document_ids=(hex_id(1),))
    first_call = Background(lambda: crawl_runs.finish_crawl(first))
    gate.wait_until_arrived()
    same_resend = Background(
        lambda: crawl_runs.finish_crawl(make_finish(skipped_document_ids=(hex_id(1),)))
    )
    different_resend = Background(
        lambda: crawl_runs.finish_crawl(make_finish(skipped_document_ids=(hex_id(2),)))
    )

    assert same_resend.is_blocked() and different_resend.is_blocked()
    gate.release()
    for call in (first_call, same_resend, different_resend):
        call.join()

    assert first_call.error is None
    assert same_resend.error is None  # 202
    assert isinstance(different_resend.error, FinishContentMismatchError)  # 409
    result = stored_result(deletions_store)
    assert result.finish_request_digest == first.digest()
    assert result.skipped_document_ids == (hex_id(1),)  # ダイジェストと ID 一覧は同じ通知のもの
    assert wakes == ["wake"]  # 受理は 1 回だけ


def test_different_sources_do_not_wait_for_each_other(
    crawl_runs: CrawlRuns, deletions_store: InMemoryStore
) -> None:
    seed_result(deletions_store, make_result(crawl_id="job-x", source_id="src-x"))
    gate = pause_before_write(deletions_store, "job-x")
    finish_x = Background(
        lambda: crawl_runs.finish_crawl(make_finish(crawl_id="job-x", source_id="src-x"))
    )
    gate.wait_until_arrived()

    other = Background(lambda: crawl_runs.start_crawl(make_start(source_id="src-y")))
    other.join()  # src-x の処理中でも終わる

    assert other.error is None
    gate.release()
    finish_x.join()


def test_background_helper_reports_the_error_of_the_call() -> None:
    call = Background(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    call.join()
    assert isinstance(call.error, RuntimeError)
