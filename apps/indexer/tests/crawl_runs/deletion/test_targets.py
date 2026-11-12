"""削除対象の取り込み(arch 9.8、K47、D-76)。"""

import pytest

from loreley_indexer.crawl_runs.deletion.targets import TargetCollector, TargetLimitExceeded
from tests.crawl_runs.deletion.scenario import (
    EXPIRED_AT,
    SEEN_AT,
    ids,
    seed_documents,
)
from tests.crawl_runs.factories import SOURCE_ID
from tests.fakes import in_memory_search_index as ops
from tests.fakes.in_memory_search_index import InMemorySearchIndex

CUTOFF = SEEN_AT  # EXPIRED_AT の文書だけが対象


def collector(search_index: InMemorySearchIndex, *, page_size: int = 4, max_targets: int = 50):
    return TargetCollector(search_index, page_size=page_size, max_targets=max_targets)


def test_collects_every_target_in_document_id_order_across_pages() -> None:  # D-76(a)
    search_index = InMemorySearchIndex()
    expired = ids(2_000, 10)  # ページサイズ 4 で 3 ページ(4、4、2)
    seed_documents(search_index, expired, last_seen_at=EXPIRED_AT)
    seed_documents(search_index, ids(1_000, 3), last_seen_at=SEEN_AT)

    targets = collector(search_index).collect(source_id=SOURCE_ID, cutoff=CUTOFF, excluded=())

    assert targets == list(expired)
    assert len(search_index.behavior.calls_of(ops.SEARCH_IDS)) == 3


def test_an_exact_multiple_of_the_page_size_ends_with_an_empty_page() -> None:
    search_index = InMemorySearchIndex()
    seed_documents(search_index, ids(2_000, 8), last_seen_at=EXPIRED_AT)

    targets = collector(search_index).collect(source_id=SOURCE_ID, cutoff=CUTOFF, excluded=())

    assert len(targets) == 8
    assert len(search_index.behavior.calls_of(ops.SEARCH_IDS)) == 3


def test_excluded_ids_are_removed_in_memory_and_other_sources_are_not_collected() -> None:
    search_index = InMemorySearchIndex()
    expired = ids(2_000, 6)
    seed_documents(search_index, expired, last_seen_at=EXPIRED_AT)
    seed_documents(search_index, ids(9_000, 2), last_seen_at=EXPIRED_AT, source_id="other")

    targets = collector(search_index).collect(
        source_id=SOURCE_ID, cutoff=CUTOFF, excluded={expired[0], expired[3]}
    )

    assert targets == [expired[1], expired[2], expired[4], expired[5]]


def test_more_targets_than_the_limit_is_an_error_even_when_the_excluded_fall_under_it() -> None:
    search_index = InMemorySearchIndex()
    expired = ids(2_000, 6)
    seed_documents(search_index, expired, last_seen_at=EXPIRED_AT)

    assert (
        len(
            collector(search_index, max_targets=6).collect(
                source_id=SOURCE_ID, cutoff=CUTOFF, excluded=()
            )
        )
        == 6
    )
    with pytest.raises(TargetLimitExceeded):
        collector(search_index, max_targets=5).collect(
            source_id=SOURCE_ID, cutoff=CUTOFF, excluded=()
        )
    # 除外した分は、上限に数えない。
    assert (
        len(
            collector(search_index, max_targets=5).collect(
                source_id=SOURCE_ID, cutoff=CUTOFF, excluded={expired[0]}
            )
        )
        == 5
    )


def test_documents_without_last_seen_at_are_never_targets() -> None:
    search_index = InMemorySearchIndex()
    search_index.seed("no-last-seen", {"source_id": SOURCE_ID})

    assert collector(search_index).collect(source_id=SOURCE_ID, cutoff=CUTOFF, excluded=()) == []
