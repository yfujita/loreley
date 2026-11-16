"""ロック文書の読み書き(architecture 5.1〜5.5。テスト観点 #13 の `create` 衝突と読み直し)。"""

import threading
from datetime import UTC, datetime, timedelta

import pytest

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.infrastructure.opensearch import LIST_MAX_SIZE, AlreadyExists, StoredRecord
from loreley_crawler.jobs.locks import (
    ANCIENT,
    EXPIRED,
    Acquired,
    LeaseSet,
    LockChanged,
    LockDeleted,
    LockDocument,
    LockHeld,
    LockNotOwned,
    LockStore,
    NotReleased,
    Released,
)
from loreley_crawler.jobs.locks.lock_document import parse_lock
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.in_memory_repository import InMemoryRepository
from tests.fakes.lost_response_repository import LostResponseRepository
from tests.jobs.locks.support import (
    JOB_ID,
    LOCK_ID,
    OWNER,
    SOURCE_ID,
    WAIT_TIMEOUT_SECONDS,
    lock_body,
)

NOW_TEXT = "2026-11-13T00:00:00.000Z"


def make_store(repository: InMemoryRepository, clock: FixedClock) -> LockStore:
    return LockStore(repository, clock)


def acquire(store: LockStore, job_id: str = JOB_ID, owner: str = OWNER) -> LockDocument:
    result = store.acquire(source_id=SOURCE_ID, owner=owner, job_id=job_id)
    assert isinstance(result, Acquired)
    return result.lock


def lease(store: LockStore, lock: LockDocument, *, require_active: bool = False) -> LeaseSet:
    result = store.set_lease(lock, lease_seconds=300, require_active_lease=require_active)
    assert isinstance(result, LeaseSet)
    return result


# --- 取得(create) ---


def test_acquire_creates_the_lock_document_with_the_fields_of_architecture_5_1(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()

    lock = acquire(make_store(repository, clock))

    assert repository.body_of(LOCK_ID) == {
        "record_type": "lock",
        "source_id": SOURCE_ID,
        "owner": OWNER,
        "job_id": JOB_ID,
        "lease_expires_at": None,  # `queued` の間は null
        "heartbeat_at": None,
        "acquired_at": NOW_TEXT,
    }
    assert lock.owner == OWNER
    assert lock.job_id == JOB_ID
    assert lock.lease_expires_at is None
    assert lock.acquired_at == DEFAULT_NOW
    assert repository.write_calls() == [ops.CREATE]


def test_acquire_does_not_take_a_lock_that_exists(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    acquire(store, job_id="job-first")
    before = repository.body_of(LOCK_ID)

    result = store.acquire(source_id=SOURCE_ID, owner=OWNER, job_id="job-second")

    assert isinstance(result, LockHeld)
    assert result.holder.job_id == "job-first"
    assert repository.body_of(LOCK_ID) == before
    assert repository.write_calls() == [ops.CREATE, ops.CREATE]  # 上書きの書き込みはない


def test_a_lock_of_another_source_does_not_block_acquire(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    acquire(store)

    other = store.acquire(source_id="other", owner=OWNER, job_id="job-other")

    assert isinstance(other, Acquired)


def test_concurrent_acquires_of_one_source_succeed_exactly_once(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    results: list[object] = []
    start = threading.Barrier(8, timeout=WAIT_TIMEOUT_SECONDS)

    def acquire_concurrently(number: int) -> None:
        start.wait()
        results.append(store.acquire(source_id=SOURCE_ID, owner=OWNER, job_id=f"job-{number}"))

    threads = [
        threading.Thread(target=acquire_concurrently, args=(number,), daemon=True)
        for number in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=WAIT_TIMEOUT_SECONDS)

    winners = [result for result in results if isinstance(result, Acquired)]
    losers = [result for result in results if isinstance(result, LockHeld)]
    assert len(winners) == 1
    assert len(losers) == 7
    assert {loser.holder.job_id for loser in losers} == {winners[0].lock.job_id}


def test_the_retried_acquire_is_a_success_when_the_first_create_had_succeeded(
    clock: FixedClock,
) -> None:
    repository = LostResponseRepository()
    repository.lose_response_of(ops.CREATE)
    store = make_store(repository, clock)

    with pytest.raises(StoreUnavailableError):
        store.acquire(source_id=SOURCE_ID, owner=OWNER, job_id=JOB_ID)  # 応答が失われた
    retried = store.acquire(source_id=SOURCE_ID, owner=OWNER, job_id=JOB_ID)

    # `AlreadyExists` だが、`owner`・`job_id` が自分なので成功。
    assert isinstance(retried, Acquired)
    assert retried.lock.job_id == JOB_ID


@pytest.mark.parametrize(("owner", "job_id"), [("another-crawler", JOB_ID), (OWNER, "job-another")])
def test_the_retried_acquire_is_a_rejection_when_the_lock_is_someone_elses(
    clock: FixedClock, owner: str, job_id: str
) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    acquire(store, job_id=job_id, owner=owner)

    assert isinstance(store.acquire(source_id=SOURCE_ID, owner=OWNER, job_id=JOB_ID), LockHeld)


def test_a_lock_that_vanishes_between_the_conflict_and_the_read_is_acquired_again(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()
    repository.behavior.inject(ops.CREATE, AlreadyExists())  # 競合と返るが、読むと消えている

    result = make_store(repository, clock).acquire(source_id=SOURCE_ID, owner=OWNER, job_id=JOB_ID)

    assert isinstance(result, Acquired)
    assert repository.write_calls() == [ops.CREATE, ops.CREATE]


def test_an_acquire_that_keeps_conflicting_becomes_a_store_failure(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    repository.behavior.inject(ops.CREATE, AlreadyExists(), times=None)

    with pytest.raises(StoreUnavailableError) as raised:
        make_store(repository, clock).acquire(source_id=SOURCE_ID, owner=OWNER, job_id=JOB_ID)

    assert raised.value.reason == "lock_acquire_contention"


# --- 読み取りと、形式不正の扱い ---


def test_read_of_a_missing_lock_is_none(clock: FixedClock) -> None:
    assert make_store(InMemoryRepository(), clock).read(SOURCE_ID) is None


def stored(source: dict[str, object]) -> StoredRecord:
    return StoredRecord(LOCK_ID, source, 1, 1)


def valid_source(**overrides: object) -> dict[str, object]:
    return {
        "record_type": "lock",
        "source_id": SOURCE_ID,
        "owner": OWNER,
        "job_id": JOB_ID,
        "lease_expires_at": "2026-11-13T00:05:00.000Z",
        "heartbeat_at": NOW_TEXT,
        "acquired_at": NOW_TEXT,
        **overrides,
    }


def test_a_valid_lock_document_is_read_with_typed_dates() -> None:
    lock = parse_lock(stored(valid_source()))

    assert lock.lease_expires_at == datetime(2026, 11, 13, 0, 5, 0, tzinfo=UTC)
    assert lock.acquired_at == DEFAULT_NOW
    assert lock.is_held_by(OWNER, JOB_ID)
    assert not lock.is_held_by(OWNER, "other")
    assert not lock.is_held_by("other", JOB_ID)


@pytest.mark.parametrize(
    "lease_expires_at",
    ["tomorrow", "2026-11-13T00:05:00.000", 12345, [], "", True],
)
def test_an_unreadable_lease_counts_as_expired(lease_expires_at: object) -> None:
    lock = parse_lock(stored(valid_source(lease_expires_at=lease_expires_at)))

    assert lock.lease_expires_at == EXPIRED
    assert not lock.has_active_lease(DEFAULT_NOW)


def test_a_missing_or_null_lease_is_unset_and_not_active() -> None:
    null_lease = parse_lock(stored(valid_source(lease_expires_at=None)))
    source = valid_source()
    del source["lease_expires_at"]
    absent_lease = parse_lock(stored(source))

    assert null_lease.lease_expires_at is None
    assert absent_lease.lease_expires_at is None
    assert not null_lease.has_active_lease(DEFAULT_NOW)


@pytest.mark.parametrize("acquired_at", [None, "yesterday", 5, "2026-11-13T00:00:00"])
def test_an_unreadable_acquired_at_counts_as_ancient(acquired_at: object) -> None:
    assert parse_lock(stored(valid_source(acquired_at=acquired_at))).acquired_at == ANCIENT


def test_the_source_id_comes_from_the_record_id_even_if_the_body_is_broken() -> None:
    lock = parse_lock(stored(valid_source(source_id=5)))

    assert lock.source_id == SOURCE_ID


@pytest.mark.parametrize("field", ["owner", "job_id"])
def test_a_missing_or_mistyped_identity_never_matches_a_real_owner(field: str) -> None:
    lock = parse_lock(stored(valid_source(**{field: 5})))

    assert getattr(lock, field) == ""
    assert not lock.is_held_by(OWNER, JOB_ID)


def test_the_lease_is_active_strictly_before_the_expiry() -> None:
    lock = parse_lock(stored(valid_source()))
    expiry = datetime(2026, 11, 13, 0, 5, 0, tzinfo=UTC)

    assert lock.has_active_lease(expiry - timedelta(milliseconds=1))
    assert not lock.has_active_lease(expiry)
    assert not lock.has_active_lease(expiry + timedelta(seconds=1))


# --- リースの設定 ---


def test_set_lease_writes_the_expiry_and_the_heartbeat_time_keeping_the_other_fields(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    queued = acquire(store)
    clock.advance(seconds=10)

    result = lease(store, queued)

    body = lock_body(repository)
    assert body["lease_expires_at"] == "2026-11-13T00:05:10.000Z"
    assert body["heartbeat_at"] == "2026-11-13T00:00:10.000Z"
    assert body["acquired_at"] == NOW_TEXT  # 受付時刻は更新しない(受付途中の判定に使う)
    assert body["owner"] == OWNER
    assert body["job_id"] == JOB_ID
    assert result.lease_expires_at == datetime(2026, 11, 13, 0, 5, 10, tzinfo=UTC)
    assert result.lock.seq_no > queued.seq_no
    assert result.lock.has_active_lease(clock.now())


def test_the_returned_expiry_equals_the_stored_value_at_millisecond_precision(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    clock.set(datetime(2026, 11, 13, 0, 0, 0, 999_999, tzinfo=UTC))

    result = lease(store, acquire(store))

    assert lock_body(repository)["lease_expires_at"] == "2026-11-13T00:05:00.999Z"
    assert result.lease_expires_at == datetime(2026, 11, 13, 0, 5, 0, 999_000, tzinfo=UTC)


def test_set_lease_is_conditioned_on_the_version_it_read(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    queued = acquire(store)

    lease(store, queued)

    assert repository.write_calls() == [ops.CREATE, ops.REPLACE]
    # 同じ(古い)版でもう一度書くと、条件が外れて読み直しになる(2 回目の書き込みで成功)。
    lease(store, queued)
    assert repository.write_calls() == [ops.CREATE, ops.REPLACE, ops.REPLACE, ops.REPLACE]


def test_a_version_conflict_with_our_own_lock_is_retried_from_the_reread_version(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    queued = acquire(store)
    repository.seed(LOCK_ID, {**lock_body(repository), "heartbeat_at": "2026-11-13T00:00:01.000Z"})

    result = store.set_lease(queued, lease_seconds=300, require_active_lease=False)

    assert isinstance(result, LeaseSet)
    assert lock_body(repository)["lease_expires_at"] == "2026-11-13T00:05:00.000Z"


def test_set_lease_reports_a_missing_lock(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    queued = acquire(store)
    repository.delete_ids([LOCK_ID])

    result = store.set_lease(queued, lease_seconds=300, require_active_lease=False)

    assert result == LockNotOwned("lock_missing")
    assert repository.body_of(LOCK_ID) is None  # 作り直さない


@pytest.mark.parametrize(("owner", "job_id"), [("another-crawler", JOB_ID), (OWNER, "job-another")])
def test_set_lease_reports_a_lock_taken_over_by_another_job_without_touching_it(
    clock: FixedClock, owner: str, job_id: str
) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    queued = acquire(store)
    repository.seed(LOCK_ID, {**lock_body(repository), "owner": owner, "job_id": job_id})
    before = repository.body_of(LOCK_ID)

    result = store.set_lease(queued, lease_seconds=300, require_active_lease=False)

    assert result == LockNotOwned("lock_taken_over")
    assert repository.body_of(LOCK_ID) == before


def test_the_start_of_a_job_may_set_the_lease_of_our_lock_whose_old_lease_has_expired(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    queued = acquire(store)
    repository.seed(
        LOCK_ID, {**lock_body(repository), "lease_expires_at": "2026-11-12T00:00:00.000Z"}
    )

    # 回復の後の `queued` のロックは、過去の期限が残っていてもよい(architecture 5.8)。
    result = store.set_lease(queued, lease_seconds=300, require_active_lease=False)

    assert isinstance(result, LeaseSet)


def test_a_heartbeat_does_not_renew_an_expired_lease_of_our_lock(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    leased = lease(store, acquire(store))
    repository.seed(
        LOCK_ID, {**lock_body(repository), "lease_expires_at": "2026-11-12T00:00:00.000Z"}
    )

    result = store.set_lease(leased.lock, lease_seconds=300, require_active_lease=True)

    assert result == LockNotOwned("lease_expired")
    assert lock_body(repository)["lease_expires_at"] == "2026-11-12T00:00:00.000Z"


def test_a_heartbeat_does_not_renew_an_unset_lease(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    leased = lease(store, acquire(store))
    repository.seed(LOCK_ID, {**lock_body(repository), "lease_expires_at": None})

    result = store.set_lease(leased.lock, lease_seconds=300, require_active_lease=True)

    assert result == LockNotOwned("lease_expired")


def test_a_set_lease_that_keeps_conflicting_becomes_a_store_failure(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    queued = acquire(store)
    for _ in range(3):
        repository.behavior.before(
            ops.REPLACE, lambda: repository.seed(LOCK_ID, lock_body(repository))
        )

    with pytest.raises(StoreUnavailableError) as raised:
        store.set_lease(queued, lease_seconds=300, require_active_lease=False)

    assert raised.value.reason == "lease_contention"


def test_a_retried_set_lease_after_a_lost_response_still_succeeds(clock: FixedClock) -> None:
    repository = LostResponseRepository()
    store = make_store(repository, clock)
    queued = acquire(store)
    repository.lose_response_of(ops.REPLACE)

    with pytest.raises(StoreUnavailableError):
        store.set_lease(queued, lease_seconds=300, require_active_lease=False)
    # 古い版のままリトライすると条件が外れるが、読み直すと自分のロックなので、版を更新して成功する。
    retried = store.set_lease(queued, lease_seconds=300, require_active_lease=False)

    assert isinstance(retried, LeaseSet)
    assert lock_body(repository)["lease_expires_at"] == "2026-11-13T00:05:00.000Z"


# --- 版条件つきの削除と解放 ---


def test_delete_unchanged_removes_the_lock_of_the_version_it_read(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    lock = acquire(store)

    assert store.delete_unchanged(lock) == LockDeleted()

    assert repository.body_of(LOCK_ID) is None
    assert repository.write_calls() == [ops.CREATE, ops.DELETE]


def test_delete_unchanged_leaves_a_lock_that_changed_since_it_was_read(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    lock = acquire(store)
    repository.seed(LOCK_ID, {**lock_body(repository), "job_id": "job-new"})

    assert store.delete_unchanged(lock) == LockChanged()

    assert lock_body(repository)["job_id"] == "job-new"


def test_delete_unchanged_of_a_missing_lock_reports_a_change(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    lock = acquire(store)
    repository.delete_ids([LOCK_ID])

    assert store.delete_unchanged(lock) == LockChanged()


def test_release_own_deletes_our_lock(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    leased = lease(store, acquire(store))

    assert store.release_own(leased.lock) == Released()

    assert repository.body_of(LOCK_ID) is None


def test_release_own_of_a_lock_that_is_already_gone_is_done(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    lock = acquire(store)
    repository.delete_ids([LOCK_ID])

    assert store.release_own(lock) == Released()


@pytest.mark.parametrize(("owner", "job_id"), [("another-crawler", JOB_ID), (OWNER, "job-another")])
def test_release_own_never_removes_a_lock_that_became_someone_elses(
    clock: FixedClock, owner: str, job_id: str
) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    lock = acquire(store)
    repository.seed(LOCK_ID, {**lock_body(repository), "owner": owner, "job_id": job_id})

    assert store.release_own(lock) == NotReleased("lock_taken_over")

    assert repository.body_of(LOCK_ID) is not None


def test_release_own_retries_from_the_reread_version_when_our_lock_was_updated(
    clock: FixedClock,
) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    stale = acquire(store)
    lease(store, stale)  # ハートビートの更新で版が進んだ

    assert store.release_own(stale) == Released()

    assert repository.body_of(LOCK_ID) is None


def test_a_release_whose_first_delete_succeeded_but_lost_its_response_is_done_on_retry(
    clock: FixedClock,
) -> None:
    repository = LostResponseRepository()
    store = make_store(repository, clock)
    lock = acquire(store)
    repository.lose_response_of(ops.DELETE)

    with pytest.raises(StoreUnavailableError):
        store.release_own(lock)

    assert store.release_own(lock) == Released()  # 条件が外れるが、ロックがなければ完了


def test_a_release_that_keeps_conflicting_becomes_a_store_failure(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    lock = acquire(store)
    for _ in range(3):
        repository.behavior.before(
            ops.DELETE, lambda: repository.seed(LOCK_ID, lock_body(repository))
        )

    with pytest.raises(StoreUnavailableError) as raised:
        store.release_own(lock)

    assert raised.value.reason == "lock_release_contention"


def test_every_write_is_a_create_or_version_conditioned(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)

    lock = acquire(store)
    leased = lease(store, lock)
    store.release_own(leased.lock)

    assert repository.write_calls() == [ops.CREATE, ops.REPLACE, ops.DELETE]


# --- 一覧(起動時の回復) ---


def test_every_lock_is_listed_with_its_source_id(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    for source_id in ("wiki", "docs"):
        store.acquire(source_id=source_id, owner=OWNER, job_id=f"job-{source_id}")
    repository.seed("job-1", {"record_type": "job", "source_id": "docs"})
    repository.seed("maintenance", {"record_type": "maintenance", "enabled": False})

    locks = store.list_locks()

    assert [(lock.source_id, lock.job_id) for lock in locks] == [
        ("docs", "job-docs"),
        ("wiki", "job-wiki"),
    ]


def test_no_locks_is_an_empty_list(clock: FixedClock) -> None:
    assert make_store(InMemoryRepository(), clock).list_locks() == []


def test_a_truncated_lock_list_is_not_returned_as_a_success(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    full_page = [
        StoredRecord(f"lock-s{i}", {"record_type": "lock", "owner": OWNER}, i, 1)
        for i in range(LIST_MAX_SIZE)
    ]
    repository.behavior.inject(ops.LIST, full_page)

    with pytest.raises(StoreUnexpectedResponseError) as raised:
        make_store(repository, clock).list_locks()

    assert raised.value.error_type == "lock_list_truncated"
