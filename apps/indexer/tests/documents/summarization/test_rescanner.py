"""`pending` の再走査(arch 7.4、P15。C-24、E-45b(b))。"""

from dataclasses import replace

import pytest

from loreley_indexer.common.errors import UnavailableError
from loreley_indexer.documents.summarization import (
    SummarizationConfig,
    SummaryRequestQueue,
    SummaryRescanner,
)
from loreley_indexer.infrastructure.opensearch import OpenSearchUnavailableError
from tests.documents.summarization.conftest import (
    MAX_RESCAN_INTERVAL_SECONDS,
    MIN_RESCAN_INTERVAL_SECONDS,
    pending_source,
    seed_pending,
)
from tests.fakes import in_memory_search_index as ops
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_search_index import InMemorySearchIndex


def drain(requests: SummaryRequestQueue) -> list[str]:
    drained = []
    while (document_id := requests.take()) is not None:
        drained.append(document_id)
    return drained


def test_only_pending_documents_are_requested_across_pages(
    rescanner: SummaryRescanner,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
) -> None:
    """C-24(a)、E-45b(b): `pending` だけを列挙する(`disabled`・`generated` は対象外)。"""
    for number in range(1, 6):  # 1 ページ 2 件なので 3 ページにまたがる
        seed_pending(search_index, f"pending-{number}")
    seed_pending(search_index, "generated", summary_status="generated", summary="s")
    seed_pending(search_index, "disabled", summary_status="disabled")
    extract_failed = pending_source("extract-failed", index_status="extract_failed")
    extract_failed.update(summary_status="disabled")
    del extract_failed["content"], extract_failed["text_hash"]
    search_index.seed("extract-failed", extract_failed)
    rescanner.request()

    accepted = rescanner.run_if_due()

    assert accepted == 5
    assert drain(summary_requests) == [f"pending-{number}" for number in range(1, 6)]


def test_nothing_is_scanned_without_a_request(
    rescanner: SummaryRescanner,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
) -> None:
    seed_pending(search_index)

    assert rescanner.run_if_due() == 0
    assert search_index.behavior.calls == []
    assert len(summary_requests) == 0


def test_one_request_causes_one_scan(
    rescanner: SummaryRescanner,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
) -> None:
    seed_pending(search_index)
    rescanner.request()
    assert rescanner.run_if_due() == 1
    drain(summary_requests)

    assert rescanner.run_if_due() == 0
    assert len(summary_requests) == 0


def test_documents_already_waiting_are_not_requested_twice(
    rescanner: SummaryRescanner,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
    clock: FixedClock,
) -> None:
    seed_pending(search_index)
    rescanner.request()
    rescanner.run_if_due()
    clock.advance(seconds=MIN_RESCAN_INTERVAL_SECONDS)
    rescanner.request()

    assert rescanner.run_if_due() == 0
    assert len(summary_requests) == 1


def test_scans_are_spaced_by_the_minimum_interval(
    rescanner: SummaryRescanner,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
    clock: FixedClock,
) -> None:
    """間隔の下限: 失敗し続ける LLM を叩き続けない。要請は残り、間隔が過ぎたら走査する。"""
    seed_pending(search_index)
    rescanner.request()
    rescanner.run_if_due()
    drain(summary_requests)
    rescanner.request()

    clock.advance(seconds=MIN_RESCAN_INTERVAL_SECONDS - 0.1)
    assert rescanner.run_if_due() == 0
    assert len(summary_requests) == 0

    clock.advance(seconds=0.1)
    assert rescanner.run_if_due() == 1


def test_full_queue_stops_the_scan_and_the_rest_is_picked_up_by_the_next_scan(
    config: SummarizationConfig,
    search_index: InMemorySearchIndex,
    clock: FixedClock,
) -> None:
    """キューが満杯なら残りは `pending` のまま、次の走査に委ねる。"""
    requests = SummaryRequestQueue(max_size=2)
    rescanner = SummaryRescanner(
        config=config, search_index=search_index, requests=requests, clock=clock
    )
    for number in range(1, 5):
        seed_pending(search_index, f"pending-{number}")
    rescanner.request()

    assert rescanner.run_if_due() == 2
    assert drain(requests) == ["pending-1", "pending-2"]
    for done in ("pending-1", "pending-2"):  # 処理されて `pending` でなくなった
        seed_pending(search_index, done, summary_status="generated", summary="s")

    clock.advance(seconds=MIN_RESCAN_INTERVAL_SECONDS)
    assert rescanner.run_if_due() == 2
    assert drain(requests) == ["pending-3", "pending-4"]


def test_failed_scan_is_retried_at_the_next_opportunity(
    rescanner: SummaryRescanner,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
    clock: FixedClock,
) -> None:
    seed_pending(search_index)
    search_index.behavior.inject(ops.SEARCH_IDS, OpenSearchUnavailableError("http_503"))
    rescanner.request()

    with pytest.raises(UnavailableError):
        rescanner.run_if_due()

    clock.advance(seconds=MIN_RESCAN_INTERVAL_SECONDS)
    assert rescanner.run_if_due() == 1


def test_page_size_follows_the_configuration(
    config: SummarizationConfig,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
    clock: FixedClock,
) -> None:
    for number in range(5):
        seed_pending(search_index, f"p-{number}")
    rescanner = SummaryRescanner(
        config=replace(config, rescan_page_size=5),
        search_index=search_index,
        requests=summary_requests,
        clock=clock,
    )
    rescanner.request()

    rescanner.run_if_due()

    assert len(search_index.behavior.calls_of(ops.SEARCH_IDS)) == 2  # 5 件の次ページが空の確認


# --- 成果のない走査が続いたときの間隔の拡大(K54(3)、案12) ---


def scan_after_waiting(
    rescanner: SummaryRescanner,
    clock: FixedClock,
    summary_requests: SummaryRequestQueue,
    *,
    seconds: float,
) -> None:
    """要請してから `seconds` 秒たつと走査される。それより 0.1 秒早い時点ではまだ走査されない。

    走査して積まれた依頼は取り出す(処理されて、また `pending` で残った状況を再現する)。
    """
    rescanner.request()
    clock.advance(seconds=seconds - 0.1)
    assert rescanner.run_if_due() == 0, f"scanned {seconds - 0.1} seconds after the last scan"
    clock.advance(seconds=0.1)
    assert rescanner.run_if_due() == 1, f"not scanned {seconds} seconds after the last scan"
    drain(summary_requests)


def test_the_first_scan_runs_immediately_whatever_the_maximum_interval(
    rescanner: SummaryRescanner,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
) -> None:
    """起動時の要請は、バックオフの影響を受けず、最初の 1 回は待たずに走査する。"""
    seed_pending(search_index)
    rescanner.request()

    assert rescanner.run_if_due() == 1


def test_the_interval_doubles_after_each_scan_without_a_written_summary_up_to_the_maximum(
    rescanner: SummaryRescanner,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
    clock: FixedClock,
) -> None:
    """書き戻しに成功しない走査が続くたびに、間隔が 2 倍になる。上限(600 秒)で止まる。"""
    seed_pending(search_index)
    rescanner.request()
    assert rescanner.run_if_due() == 1  # 最初の走査
    drain(summary_requests)

    for waited_seconds in (60, 120, 240, 480, MAX_RESCAN_INTERVAL_SECONDS, 600, 600):
        scan_after_waiting(rescanner, clock, summary_requests, seconds=waited_seconds)


def test_a_written_summary_resets_the_interval_to_the_minimum(
    rescanner: SummaryRescanner,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
    clock: FixedClock,
) -> None:
    seed_pending(search_index)
    rescanner.request()
    rescanner.run_if_due()
    drain(summary_requests)
    for waited_seconds in (60, 120, 240):  # 次に必要な間隔は 480 秒まで伸びる
        scan_after_waiting(rescanner, clock, summary_requests, seconds=waited_seconds)

    rescanner.note_summary_written()

    scan_after_waiting(rescanner, clock, summary_requests, seconds=60)


def test_a_summary_written_between_two_scans_keeps_the_interval_at_the_minimum(
    rescanner: SummaryRescanner,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
    clock: FixedClock,
) -> None:
    """走査と走査のあいだに 1 件でも書き戻せていれば、成果があった走査として扱う。"""
    seed_pending(search_index)
    rescanner.request()
    rescanner.run_if_due()
    drain(summary_requests)

    for _ in range(4):
        rescanner.note_summary_written()
        scan_after_waiting(rescanner, clock, summary_requests, seconds=60)


def test_a_written_summary_before_the_first_scan_does_not_hide_the_following_failures(
    rescanner: SummaryRescanner,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
    clock: FixedClock,
) -> None:
    """起動時の走査の前の成功は、その次以降の成果なしの判定には影響しない。"""
    seed_pending(search_index)
    rescanner.note_summary_written()
    rescanner.request()
    rescanner.run_if_due()
    drain(summary_requests)

    for waited_seconds in (60, 120):
        scan_after_waiting(rescanner, clock, summary_requests, seconds=waited_seconds)


def test_a_failed_scan_also_counts_as_a_scan_without_a_written_summary(
    rescanner: SummaryRescanner,
    search_index: InMemorySearchIndex,
    summary_requests: SummaryRequestQueue,
    clock: FixedClock,
) -> None:
    seed_pending(search_index)
    rescanner.request()
    rescanner.run_if_due()
    drain(summary_requests)
    search_index.behavior.inject(ops.SEARCH_IDS, OpenSearchUnavailableError("http_503"))
    rescanner.request()
    clock.advance(seconds=MIN_RESCAN_INTERVAL_SECONDS)
    with pytest.raises(UnavailableError):
        rescanner.run_if_due()  # 2 回目の走査(失敗)

    scan_after_waiting(rescanner, clock, summary_requests, seconds=120)
