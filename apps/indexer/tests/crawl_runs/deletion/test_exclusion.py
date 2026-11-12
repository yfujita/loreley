"""削除バッチとソース削除の排他(arch 9.8、9.14。P29)。"""

from loreley_indexer.crawl_runs.deletion.exclusion import SourceBatchExclusion
from tests.fakes.concurrency import Background


def test_a_batch_and_a_source_deletion_of_the_same_source_never_overlap() -> None:
    exclusion = SourceBatchExclusion()

    def source_deletion() -> None:
        with exclusion.hold_priority("s1"):
            pass

    with exclusion.hold_batch("s1"):
        waiting = Background(source_deletion)
        assert waiting.is_blocked()  # バッチの間は待たされる
    waiting.join()


def test_different_sources_do_not_block_each_other() -> None:
    exclusion = SourceBatchExclusion()

    def source_deletion_of_another_source() -> None:
        with exclusion.hold_priority("s2"):
            pass

    with exclusion.hold_batch("s1"):
        other = Background(source_deletion_of_another_source)
        other.join()  # 待たされずに終わる


def test_a_waiting_source_deletion_goes_before_the_next_batch() -> None:
    """バッチを終えた側が、待っているソース削除より先に次のバッチを取らない。"""
    exclusion = SourceBatchExclusion()
    order: list[str] = []

    def source_deletion() -> None:
        with exclusion.hold_priority("s1"):
            order.append("source_deletion")

    def next_batch() -> None:
        with exclusion.hold_batch("s1"):
            order.append("next_batch")

    with exclusion.hold_batch("s1"):
        source_deletion_call = Background(source_deletion)
        assert source_deletion_call.is_blocked()  # ソース削除が待ち始めた
        next_batch_call = Background(next_batch)
        assert next_batch_call.is_blocked()
    source_deletion_call.join()
    next_batch_call.join()

    assert order == ["source_deletion", "next_batch"]


def test_the_exclusion_is_released_when_the_body_raises() -> None:
    exclusion = SourceBatchExclusion()
    try:
        with exclusion.hold_batch("s1"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    with exclusion.hold_priority("s1"):  # 待たされない
        pass
