import threading
import time

import pytest

from loreley_indexer.documents.summarization import SubmitResult, SummaryRequestQueue
from tests.documents.summarization.conftest import signal_when_a_taker_waits


def test_requests_are_taken_in_arrival_order() -> None:
    queue = SummaryRequestQueue(max_size=3)
    for document_id in ("a", "b", "c"):
        assert queue.submit(document_id) is SubmitResult.ACCEPTED

    assert [queue.take(), queue.take(), queue.take(), queue.take()] == ["a", "b", "c", None]


def test_a_document_already_waiting_is_not_queued_twice() -> None:
    queue = SummaryRequestQueue(max_size=3)
    queue.submit("a")

    assert queue.submit("a") is SubmitResult.ALREADY_QUEUED
    assert len(queue) == 1


def test_a_document_taken_for_processing_can_be_queued_again() -> None:
    """処理中に本文が変わった文書は、新しい本文のために改めて依頼できる(C-1)。"""
    queue = SummaryRequestQueue(max_size=3)
    queue.submit("a")
    queue.take()

    assert queue.submit("a") is SubmitResult.ACCEPTED


def test_full_queue_refuses_and_remembers_the_overflow_once() -> None:
    queue = SummaryRequestQueue(max_size=2)
    queue.submit("a")
    queue.submit("b")

    assert queue.submit("c") is SubmitResult.FULL
    assert len(queue) == 2
    assert queue.take_overflow_flag() is True
    assert queue.take_overflow_flag() is False


def test_space_frees_up_after_a_take() -> None:
    queue = SummaryRequestQueue(max_size=1)
    queue.submit("a")
    queue.take()

    assert queue.submit("b") is SubmitResult.ACCEPTED


def test_take_on_an_empty_queue_returns_none_without_waiting() -> None:
    assert SummaryRequestQueue(max_size=1).take() is None


def test_take_waits_for_a_request_submitted_by_another_thread() -> None:
    queue = SummaryRequestQueue(max_size=1)
    ready = threading.Event()

    def submit_later() -> None:
        ready.wait(5.0)
        queue.submit("a")

    thread = threading.Thread(target=submit_later, daemon=True)
    thread.start()
    ready.set()

    assert queue.take(wait_seconds=5.0) == "a"
    thread.join(5.0)


def test_submit_wakes_a_waiting_taker() -> None:
    """待ちに入ったあとの `submit` が待ち手を起こす(`notify()`)。起こされなければ 30 秒待つ。"""
    queue = SummaryRequestQueue(max_size=1)
    waiting = signal_when_a_taker_waits(queue)
    taken: list[str | None] = []
    started_at = time.monotonic()
    thread = threading.Thread(
        target=lambda: taken.append(queue.take(wait_seconds=30.0)), daemon=True
    )
    thread.start()
    assert waiting.wait(5.0)

    queue.submit("a")
    thread.join(5.0)

    assert not thread.is_alive()
    assert taken == ["a"]
    assert time.monotonic() - started_at < 5.0


def test_close_wakes_a_waiting_taker() -> None:
    queue = SummaryRequestQueue(max_size=1)
    waiting = signal_when_a_taker_waits(queue)
    taken: list[str | None] = []
    thread = threading.Thread(
        target=lambda: taken.append(queue.take(wait_seconds=30.0)), daemon=True
    )
    thread.start()
    assert waiting.wait(5.0)

    queue.close()
    thread.join(5.0)  # 起こされなければ、30 秒の待ちが終わるまで戻らない

    assert not thread.is_alive()
    assert taken == [None]


def test_take_after_close_does_not_wait() -> None:
    queue = SummaryRequestQueue(max_size=1)
    queue.close()
    started_at = time.monotonic()

    assert queue.take(wait_seconds=30.0) is None

    assert time.monotonic() - started_at < 5.0


def test_size_must_be_positive() -> None:
    with pytest.raises(ValueError):
        SummaryRequestQueue(max_size=0)
