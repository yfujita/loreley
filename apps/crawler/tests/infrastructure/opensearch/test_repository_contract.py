"""Repository の契約テスト。同じテストを、2 つの実装に流す。

- `in_memory`: `InMemoryRepository`(tests/fakes)
- `opensearch`: `OpenSearchRepository`。通信層だけをメモリ上のエミュレータ
  (`FakeOpenSearchTransport`)に差し替えた、実際の `OpenSearch` クライアントで動かす
  (リクエストの組み立てと応答の解釈を通す)

どちらも同じ契約・同じ結果区分に従うことを確かめる(完了条件 7)。実機の OpenSearch との一致
(10,001 件以上・PIT・refresh の遅れ・`create` と版条件の原子性。architecture 12章 #37)は
統合テストで確認する。
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import islice
from typing import Any

import pytest
from opensearchpy import OpenSearch
from opensearchpy.exceptions import ConnectionTimeout

from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.infrastructure.opensearch import (
    LIST_MAX_SIZE,
    AlreadyExists,
    BulkDeleteResult,
    Conflict,
    Deleted,
    OpenSearchRepository,
    RecordFilter,
    Repository,
    RepositorySettings,
    SortKey,
    StoredRecord,
    Written,
)
from tests.fakes import fake_opensearch, in_memory_repository
from tests.fakes.fake_opensearch import FakeOpenSearchTransport
from tests.fakes.in_memory_repository import InMemoryRepository

INDEX = "loreley-jobs-test"
PAGE_SIZE = 3
BULK_BATCH_SIZE = 3
SETTINGS = RepositorySettings(scan_page_size=PAGE_SIZE, bulk_delete_batch_size=BULK_BATCH_SIZE)
BY_DOCUMENT_ID = [SortKey("document_id")]


@dataclass
class Harness:
    """契約テストが使う、実装ごとの差し込み口。"""

    repository: Repository
    fail_bulk_delete_of: Callable[[Sequence[str]], None]
    fail_scan_page_after: Callable[[int], None]  # n ページ読んだ後の次のページで、全体の異常にする
    fail_scan_start: Callable[[], None]
    fail_scan_refresh: Callable[[], None]  # 走査の開始前の refresh を、全体の異常にする
    open_scan_count: Callable[[], int]  # 開いたままの走査(PIT)の数
    refresh_index: Callable[[], None]  # 検索に見える状態を最新にする(実機の refresh。fake は不要)


def make_in_memory_harness() -> Harness:
    repository = InMemoryRepository(SETTINGS)

    def fail_scan_page_after(pages: int) -> None:
        for _ in range(pages):
            repository.behavior.before(in_memory_repository.SCAN_PAGE, lambda: None)

        def fail() -> None:
            raise StoreUnavailableError("connection_timeout")

        repository.behavior.before(in_memory_repository.SCAN_PAGE, fail)

    return Harness(
        repository=repository,
        fail_bulk_delete_of=repository.fail_bulk_delete_of,
        fail_scan_page_after=fail_scan_page_after,
        fail_scan_start=lambda: repository.behavior.inject(
            in_memory_repository.SCAN, StoreUnavailableError("connection_timeout")
        ),
        # fake には refresh がない。走査を始められない失敗として同じに扱う。
        fail_scan_refresh=lambda: repository.behavior.inject(
            in_memory_repository.SCAN, StoreUnavailableError("connection_timeout")
        ),
        open_scan_count=lambda: repository.open_scan_count,
        refresh_index=lambda: None,
    )


def make_opensearch_harness() -> Harness:
    transport = FakeOpenSearchTransport()
    client = OpenSearch(hosts=["http://opensearch.invalid:9200"])
    client.transport = transport
    repository = OpenSearchRepository(client, INDEX, SETTINGS)
    timeout = ConnectionTimeout("TIMEOUT", "timed out", Exception("x"))
    return Harness(
        repository=repository,
        fail_bulk_delete_of=transport.fail_bulk_items,
        fail_scan_page_after=lambda pages: transport.fail_on(
            fake_opensearch.SEARCH, timeout, skip=pages
        ),
        fail_scan_start=lambda: transport.fail_on(fake_opensearch.CREATE_PIT, timeout),
        fail_scan_refresh=lambda: transport.fail_on(fake_opensearch.REFRESH, timeout),
        open_scan_count=lambda: len(transport.open_pit_ids),
        refresh_index=lambda: transport.refresh(INDEX),
    )


@pytest.fixture(params=["in_memory", "opensearch"])
def harness(request: pytest.FixtureRequest) -> Harness:
    return make_in_memory_harness() if request.param == "in_memory" else make_opensearch_harness()


@pytest.fixture
def repository(harness: Harness) -> Repository:
    return harness.repository


def put(repository: Repository, record_id: str, **fields: Any) -> Written:
    outcome = repository.create(record_id, fields)
    assert isinstance(outcome, Written)
    return outcome


def put_documents(repository: Repository, document_ids: Sequence[str]) -> None:
    for document_id in document_ids:
        put(repository, f"skip-s1-{document_id}", source_id="s1", document_id=document_id)


# 走査のページ数の上限。実装の不具合(同じページを読み続けるなど)で、テストがハングしないように。
MAX_PAGES = 100


def scan_ids(repository: Repository, record_filter: RecordFilter | None = None) -> list[str]:
    with repository.scan(record_filter or RecordFilter(), sort=BY_DOCUMENT_ID) as pages:
        return [record.id for page in islice(pages, MAX_PAGES) for record in page]


def scan_pages(repository: Repository, record_filter: RecordFilter | None = None) -> list[int]:
    with repository.scan(record_filter or RecordFilter(), sort=BY_DOCUMENT_ID) as pages:
        return [len(page) for page in islice(pages, MAX_PAGES)]


# --- 取得・作成 ---


def test_fetching_a_missing_record_returns_none(repository: Repository) -> None:
    assert repository.fetch("job-1") is None


def test_fetching_an_empty_id_returns_none_in_both_implementations(
    repository: Repository,
) -> None:
    """実クライアントは空の ID を `ValueError` にする。形式不正のロック文書の `job_id`(空)で
    ジョブを引いても、メモリ上の実装と同じく、記録なしとして扱えること。"""
    put(repository, "job-1")

    assert repository.fetch("") is None


def test_create_stores_the_record_and_fetch_returns_it_with_the_version(
    repository: Repository,
) -> None:
    written = put(repository, "job-1", status="queued")

    record = repository.fetch("job-1")

    assert record == StoredRecord(
        id="job-1",
        source={"status": "queued"},
        seq_no=written.seq_no,
        primary_term=written.primary_term,
    )


def test_create_of_an_existing_id_is_already_exists_and_keeps_the_first_record(
    repository: Repository,
) -> None:
    put(repository, "job-1", status="queued")

    assert repository.create("job-1", {"status": "other"}) == AlreadyExists()
    assert repository.fetch("job-1").source == {"status": "queued"}


# --- 版条件つきの置き換え・削除 ---


def test_replace_with_the_read_version_writes_and_returns_the_next_version(
    repository: Repository,
) -> None:
    put(repository, "lock-s1", owner="a")
    read = repository.fetch("lock-s1")
    assert read is not None

    outcome = repository.replace_if_unchanged(
        "lock-s1",
        {"owner": "a", "heartbeat": 1},
        seq_no=read.seq_no,
        primary_term=read.primary_term,
    )

    assert isinstance(outcome, Written)
    assert outcome.seq_no != read.seq_no
    assert repository.fetch("lock-s1") == StoredRecord(
        "lock-s1", {"owner": "a", "heartbeat": 1}, outcome.seq_no, outcome.primary_term
    )


def test_replace_with_a_stale_version_is_a_conflict_and_does_not_write(
    repository: Repository,
) -> None:
    put(repository, "lock-s1", owner="a")
    stale = repository.fetch("lock-s1")
    assert stale is not None
    repository.replace_if_unchanged(
        "lock-s1", {"owner": "b"}, seq_no=stale.seq_no, primary_term=stale.primary_term
    )

    outcome = repository.replace_if_unchanged(
        "lock-s1", {"owner": "c"}, seq_no=stale.seq_no, primary_term=stale.primary_term
    )

    assert outcome == Conflict()
    assert repository.fetch("lock-s1").source == {"owner": "b"}


def test_replace_and_delete_of_a_missing_record_are_conflicts(repository: Repository) -> None:
    # 実 OpenSearch 3.9.0 は、記録がない場合の版条件つきの書き込み・削除も 409 で拒否する。
    replaced = repository.replace_if_unchanged("lock-s1", {"owner": "a"}, seq_no=0, primary_term=1)
    deleted = repository.delete_if_unchanged("lock-s1", seq_no=0, primary_term=1)

    assert replaced == Conflict()
    assert deleted == Conflict()
    assert repository.fetch("lock-s1") is None


def test_delete_with_the_read_version_deletes_the_record(repository: Repository) -> None:
    put(repository, "lock-s1", owner="a")
    read = repository.fetch("lock-s1")
    assert read is not None

    outcome = repository.delete_if_unchanged(
        "lock-s1", seq_no=read.seq_no, primary_term=read.primary_term
    )

    assert outcome == Deleted()
    assert repository.fetch("lock-s1") is None


def test_delete_with_a_stale_version_is_a_conflict_and_keeps_the_record(
    repository: Repository,
) -> None:
    put(repository, "lock-s1", owner="a")
    stale = repository.fetch("lock-s1")
    assert stale is not None
    repository.replace_if_unchanged(
        "lock-s1", {"owner": "b"}, seq_no=stale.seq_no, primary_term=stale.primary_term
    )

    outcome = repository.delete_if_unchanged(
        "lock-s1", seq_no=stale.seq_no, primary_term=stale.primary_term
    )

    assert outcome == Conflict()
    assert repository.fetch("lock-s1") is not None


# --- 一覧 ---


@pytest.fixture
def jobs(repository: Repository) -> Repository:
    put(repository, "job-1", record_type="job", status="queued", queued_at="2026-11-13T00:00:03Z")
    put(repository, "job-2", record_type="job", status="running", queued_at="2026-11-13T00:00:01Z")
    put(repository, "job-3", record_type="job", status="queued", queued_at="2026-11-13T00:00:02Z")
    put(repository, "lock-s1", record_type="lock", status="queued")
    put(repository, "job-4", record_type="job", status="queued")  # queued_at がない
    return repository


def list_ids(
    repository: Repository,
    record_filter: RecordFilter,
    sort: Sequence[SortKey] = (),
    limit: int = 100,
) -> list[str]:
    return [record.id for record in repository.list_records(record_filter, sort, limit=limit)]


def test_list_filters_by_equal_values_and_sorts_ascending_with_missing_values_last(
    jobs: Repository,
) -> None:
    record_filter = RecordFilter(equals={"record_type": "job", "status": "queued"})

    assert list_ids(jobs, record_filter, [SortKey("queued_at")]) == ["job-3", "job-1", "job-4"]


def test_list_sorts_descending_with_missing_values_still_last(jobs: Repository) -> None:
    record_filter = RecordFilter(equals={"record_type": "job", "status": "queued"})

    sort = [SortKey("queued_at", descending=True)]
    assert list_ids(jobs, record_filter, sort) == ["job-1", "job-3", "job-4"]


def test_list_supports_one_of_exists_and_missing(jobs: Repository) -> None:
    assert sorted(list_ids(jobs, RecordFilter(one_of={"status": ["running", "queued"]}))) == [
        "job-1",
        "job-2",
        "job-3",
        "job-4",
        "lock-s1",
    ]
    assert sorted(list_ids(jobs, RecordFilter(exists=("queued_at",)))) == [
        "job-1",
        "job-2",
        "job-3",
    ]
    assert sorted(list_ids(jobs, RecordFilter(missing=("queued_at",)))) == ["job-4", "lock-s1"]


def test_list_returns_at_most_the_limit(jobs: Repository) -> None:
    ids = list_ids(jobs, RecordFilter(equals={"record_type": "job"}), [SortKey("queued_at")], 2)

    assert ids == ["job-2", "job-3"]


@pytest.mark.parametrize("limit", [0, LIST_MAX_SIZE + 1])
def test_list_rejects_a_limit_outside_the_range(repository: Repository, limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        repository.list_records(RecordFilter(), [], limit=limit)


def test_list_sees_a_record_written_just_before(repository: Repository) -> None:
    put(repository, "job-1", record_type="job")

    assert list_ids(repository, RecordFilter(equals={"record_type": "job"})) == ["job-1"]


# --- 全件走査 ---


def test_scan_reads_all_matching_records_page_by_page_in_the_sort_order(
    repository: Repository,
) -> None:
    put_documents(repository, ["d7", "d3", "d1", "d5", "d2", "d6", "d4"])

    assert scan_pages(repository) == [3, 3, 1]
    assert scan_ids(repository) == [f"skip-s1-d{n}" for n in range(1, 8)]


def test_scan_of_no_matching_record_yields_no_page(repository: Repository) -> None:
    put_documents(repository, ["d1"])

    assert scan_pages(repository, RecordFilter(equals={"source_id": "other"})) == []


def test_scan_reads_only_the_records_matching_the_filter(repository: Repository) -> None:
    put_documents(repository, ["d1", "d2"])
    put(repository, "oversize-s1-d1", source_id="s1", document_id="d1", record_type="oversize")
    put(repository, "skip-s2-d1", source_id="s2", document_id="d1", record_type="skip")

    # 同じ `document_id` の記録が種類をまたいで共存するので、`record_type` ごとに走査する。
    assert scan_ids(
        repository, RecordFilter(equals={"source_id": "s1", "record_type": "oversize"})
    ) == ["oversize-s1-d1"]


def test_scan_sees_the_records_written_just_before_it_starts(repository: Repository) -> None:
    # 検索は refresh するまで書き込みが見えない。走査が開始前に refresh することの確認。
    put_documents(repository, ["d1", "d2", "d3", "d4"])
    assert scan_ids(repository) == [f"skip-s1-d{n}" for n in range(1, 5)]

    put_documents(repository, ["d5"])

    assert scan_ids(repository)[-1] == "skip-s1-d5"


def test_scan_reads_the_state_at_its_start_even_if_records_are_deleted_while_reading(
    repository: Repository,
) -> None:
    put_documents(repository, [f"d{n}" for n in range(1, 8)])
    read_ids: list[str] = []

    with repository.scan(RecordFilter(), sort=BY_DOCUMENT_ID) as pages:
        for page in pages:
            read_ids += [record.id for record in page]
            assert repository.delete_ids([record.id for record in page]).failed_ids == ()

    assert read_ids == [f"skip-s1-d{n}" for n in range(1, 8)]
    assert scan_ids(repository) == []


def test_scan_closes_the_point_in_time_when_it_is_read_to_the_end(
    harness: Harness,
) -> None:
    put_documents(harness.repository, ["d1", "d2"])

    with harness.repository.scan(RecordFilter(), sort=BY_DOCUMENT_ID) as pages:
        assert harness.open_scan_count() == 1
        assert [len(page) for page in pages] == [2]

    assert harness.open_scan_count() == 0


def test_scan_closes_the_point_in_time_when_the_caller_stops_midway(harness: Harness) -> None:
    put_documents(harness.repository, [f"d{n}" for n in range(1, 8)])

    with harness.repository.scan(RecordFilter(), sort=BY_DOCUMENT_ID) as pages:
        next(pages)

    assert harness.open_scan_count() == 0


def test_scan_closes_the_point_in_time_when_the_caller_raises(harness: Harness) -> None:
    put_documents(harness.repository, [f"d{n}" for n in range(1, 8)])

    with (
        pytest.raises(RuntimeError, match="stop"),
        harness.repository.scan(RecordFilter(), sort=BY_DOCUMENT_ID) as pages,
    ):
        for _ in pages:
            raise RuntimeError("stop")

    assert harness.open_scan_count() == 0


def test_scan_closes_the_point_in_time_when_reading_a_page_fails(harness: Harness) -> None:
    put_documents(harness.repository, [f"d{n}" for n in range(1, 8)])
    harness.fail_scan_page_after(1)
    read_pages: list[int] = []

    with (
        pytest.raises(StoreUnavailableError),
        harness.repository.scan(RecordFilter(), sort=BY_DOCUMENT_ID) as pages,
    ):
        for page in pages:
            read_pages.append(len(page))

    assert read_pages == [3]
    assert harness.open_scan_count() == 0


def test_scan_that_fails_to_start_leaves_no_point_in_time(harness: Harness) -> None:
    put_documents(harness.repository, ["d1"])
    harness.fail_scan_start()

    with (
        pytest.raises(StoreUnavailableError),
        harness.repository.scan(RecordFilter(), sort=BY_DOCUMENT_ID),
    ):
        pytest.fail("the scan must not start")

    assert harness.open_scan_count() == 0


def test_scan_requires_a_sort_with_a_tiebreaker(repository: Repository) -> None:
    with pytest.raises(ValueError, match="sort"):
        repository.scan(RecordFilter(), sort=[])


def test_scan_reads_the_snapshot_at_its_start_even_after_a_refresh_during_the_scan(
    harness: Harness,
) -> None:
    """走査中に記録が削除・追加され、検索に見える状態が更新(refresh)されても、影響を受けない。

    PIT が、開いた時点の状態のコピーであることの確認。
    """
    repository = harness.repository
    put_documents(repository, [f"d{n}" for n in range(1, 8)])
    read_ids: list[str] = []

    with repository.scan(RecordFilter(), sort=BY_DOCUMENT_ID) as pages:
        for page in islice(pages, MAX_PAGES):
            read_ids += [record.id for record in page]
            if len(read_ids) == len(page):  # 最初のページの処理の後に、走査の外で書き換える
                repository.delete_ids(["skip-s1-d5", "skip-s1-d6"])
                put_documents(repository, ["d0", "d9"])
                harness.refresh_index()

    assert read_ids == [f"skip-s1-d{n}" for n in range(1, 8)]
    # 走査の外(新しい走査)からは、書き換えた後の状態が見える。
    assert scan_ids(repository) == [
        "skip-s1-d0",
        "skip-s1-d1",
        "skip-s1-d2",
        "skip-s1-d3",
        "skip-s1-d4",
        "skip-s1-d7",
        "skip-s1-d9",
    ]


def test_scan_sorts_by_several_keys_in_priority_order(repository: Repository) -> None:
    # 1 番目のキー(group)の昇順が優先で、同じ group の中で 2 番目のキー(document_id)の降順。
    # 優先順位が逆(document_id が先)だと、結果が r2・r3・r4・r1 になって変わる。
    put(repository, "r1", group="a", document_id="d1")
    put(repository, "r2", group="b", document_id="d9")
    put(repository, "r3", group="a", document_id="d5")
    put(repository, "r4", group="b", document_id="d2")
    sort = [SortKey("group"), SortKey("document_id", descending=True)]

    with repository.scan(RecordFilter(), sort=sort) as pages:
        ids = [record.id for page in islice(pages, MAX_PAGES) for record in page]

    assert ids == ["r3", "r1", "r2", "r4"]


def test_scan_that_fails_to_refresh_leaves_no_point_in_time(harness: Harness) -> None:
    put_documents(harness.repository, ["d1"])
    harness.fail_scan_refresh()

    with (
        pytest.raises(StoreUnavailableError),
        harness.repository.scan(RecordFilter(), sort=BY_DOCUMENT_ID),
    ):
        pytest.fail("the scan must not start")

    assert harness.open_scan_count() == 0


# --- ID のバルク削除 ---


def test_delete_ids_removes_the_records_and_treats_missing_ids_as_success(
    repository: Repository,
) -> None:
    put_documents(repository, ["d1", "d2"])

    result = repository.delete_ids(["skip-s1-d1", "skip-s1-never-existed", "skip-s1-d2"])

    assert result == BulkDeleteResult(failed_ids=())
    assert scan_ids(repository) == []


def test_delete_ids_of_nothing_succeeds_and_deleting_again_is_idempotent(
    repository: Repository,
) -> None:
    put_documents(repository, ["d1"])

    assert repository.delete_ids([]) == BulkDeleteResult()
    assert repository.delete_ids(["skip-s1-d1"]) == BulkDeleteResult()
    assert repository.delete_ids(["skip-s1-d1"]) == BulkDeleteResult()


def test_delete_ids_deletes_more_ids_than_one_batch_and_ignores_duplicates(
    repository: Repository,
) -> None:
    put_documents(repository, [f"d{n}" for n in range(1, 11)])
    ids = [f"skip-s1-d{n}" for n in range(1, 11)]

    result = repository.delete_ids([*ids, *ids[:2]])

    assert result == BulkDeleteResult()
    assert scan_ids(repository) == []


def test_delete_ids_returns_the_failed_ids_of_a_partial_failure_and_deletes_the_others(
    harness: Harness,
) -> None:
    put_documents(harness.repository, [f"d{n}" for n in range(1, 8)])
    ids = [f"skip-s1-d{n}" for n in range(1, 8)]
    harness.fail_bulk_delete_of(["skip-s1-d2", "skip-s1-d6"])

    result = harness.repository.delete_ids(ids)

    assert result == BulkDeleteResult(failed_ids=("skip-s1-d2", "skip-s1-d6"))
    assert scan_ids(harness.repository) == ["skip-s1-d2", "skip-s1-d6"]


def test_a_duplicated_failing_id_is_reported_once(harness: Harness) -> None:
    put_documents(harness.repository, ["d1", "d2"])
    harness.fail_bulk_delete_of(["skip-s1-d1"])

    result = harness.repository.delete_ids(["skip-s1-d1", "skip-s1-d2", "skip-s1-d1"])

    assert result.failed_ids == ("skip-s1-d1",)


def test_only_the_failed_ids_are_retried_and_then_succeed(harness: Harness) -> None:
    put_documents(harness.repository, ["d1", "d2", "d3"])
    harness.fail_bulk_delete_of(["skip-s1-d2"])
    first = harness.repository.delete_ids(["skip-s1-d1", "skip-s1-d2", "skip-s1-d3"])

    second = harness.repository.delete_ids(list(first.failed_ids))

    assert first.failed_ids == ("skip-s1-d2",)
    assert second == BulkDeleteResult()
    assert scan_ids(harness.repository) == []


def test_the_cleanup_pattern_scan_then_bulk_delete_removes_exactly_the_scanned_records(
    repository: Repository,
) -> None:
    put_documents(repository, [f"d{n}" for n in range(1, 8)])
    put(repository, "lock-s1", record_type="lock")

    with repository.scan(RecordFilter(equals={"source_id": "s1"}), sort=BY_DOCUMENT_ID) as pages:
        for page in pages:
            repository.delete_ids([record.id for record in page])

    assert list_ids(repository, RecordFilter()) == ["lock-s1"]
