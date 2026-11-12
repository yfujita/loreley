"""ソース単位の直列化(arch 8章、9.9、plan 案19)。"""

import threading

import pytest

from loreley_indexer.common.source_locks import SourceLocks
from tests.fakes.concurrency import BLOCKED_PROBE_SECONDS, JOIN_TIMEOUT_SECONDS


def test_different_sources_do_not_block_each_other() -> None:
    locks = SourceLocks()

    with locks.hold("source-1"), locks.hold("source-2"):
        pass


def test_same_source_is_held_by_one_user_at_a_time() -> None:
    locks = SourceLocks()
    acquired = threading.Event()

    def hold_same_source() -> None:
        with locks.hold("source-1"):
            acquired.set()

    with locks.hold("source-1"):
        thread = threading.Thread(target=hold_same_source, daemon=True)
        thread.start()
        assert not acquired.wait(BLOCKED_PROBE_SECONDS)
    assert acquired.wait(JOIN_TIMEOUT_SECONDS)
    thread.join(JOIN_TIMEOUT_SECONDS)


def test_lock_is_released_when_the_body_raises() -> None:
    locks = SourceLocks()

    with pytest.raises(RuntimeError), locks.hold("source-1"):
        raise RuntimeError("boom")

    with locks.hold("source-1"):
        pass


def test_separate_instances_do_not_block_each_other() -> None:
    """用途ごとに別のインスタンスを使う(登録と開始・終了通知は互いを待たせない。案19)。"""
    documents_locks = SourceLocks()
    crawl_runs_locks = SourceLocks()

    with documents_locks.hold("source-1"), crawl_runs_locks.hold("source-1"):
        pass
