"""`SourceStore`・`SourceReader`: crawler-api 4.4 の登録・更新の分岐、読み取り、削除。"""

import threading
from datetime import timedelta

import pytest

from loreley_crawler.common.errors import StoreUnavailableError, StoreUnexpectedResponseError
from loreley_crawler.infrastructure.opensearch import LIST_MAX_SIZE, AlreadyExists, StoredRecord
from loreley_crawler.sources import (
    AlreadyRegistered,
    MalformedSourceRecord,
    MarkedDeleting,
    Registered,
    RegistrationConflict,
    SourceDeleted,
    SourceIsDeleting,
    SourceNotDeleting,
    SourceNotFound,
    SourceReader,
    SourceRecord,
    SourceStatus,
    Unchanged,
    Updated,
)
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import DEFAULT_NOW, FixedClock
from tests.fakes.in_memory_repository import InMemoryRepository
from tests.fakes.lost_response_repository import LostResponseRepository
from tests.sources.support import SECRET_REFERENCE, make_new_source, make_settings, make_store

JOIN_TIMEOUT_SECONDS = 5.0
STORED_UPDATED_AT = "2026-11-13T00:00:00.000Z"


def stored_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "source_id": "docs",
        "connector_type": "file_system",
        "connector_config": {"root": "/data", "token": SECRET_REFERENCE},
        "ttl": 2_592_000,
        "ratio_threshold": 0.3,
        "min_delete_count": 10,
        "schedule_cron": "0 3 * * *",
        "status": "active",
        "updated_at": STORED_UPDATED_AT,
    }
    body.update(overrides)
    return body


@pytest.fixture
def repository() -> InMemoryRepository:
    return InMemoryRepository()


# --- 登録(crawler-api 4.4.2) ---


def test_registering_a_new_source_creates_an_active_record_with_the_updated_time(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    result = make_store(repository, clock).register(make_new_source("docs"))

    assert isinstance(result, Registered)
    assert result.record.status is SourceStatus.ACTIVE
    assert result.record.updated_at == DEFAULT_NOW
    assert repository.body_of("docs") == stored_body(updated_at="2026-11-13T00:00:00.000Z")


def test_the_registered_record_has_every_field_of_architecture_3_2(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    make_store(repository, clock).register(make_new_source("docs", schedule_cron=None))

    assert set(repository.body_of("docs") or {}) == {
        "source_id",
        "connector_type",
        "connector_config",
        "ttl",
        "ratio_threshold",
        "min_delete_count",
        "schedule_cron",
        "status",
        "updated_at",
    }
    assert (repository.body_of("docs") or {})["schedule_cron"] is None


def test_registration_uses_create_only_and_never_overwrites(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body(ttl=1))

    make_store(repository, clock).register(make_new_source("docs"))

    assert repository.write_calls() == [ops.CREATE]
    assert (repository.body_of("docs") or {})["ttl"] == 1


def test_registering_the_same_content_again_succeeds_as_already_registered(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    store = make_store(repository, clock)
    store.register(make_new_source("docs"))
    clock.advance(seconds=60)

    result = store.register(make_new_source("docs"))

    assert isinstance(result, AlreadyRegistered)
    # 書き換えない(`updated_at` も動かない)。
    assert result.record.updated_at == DEFAULT_NOW
    assert repository.write_calls() == [ops.CREATE, ops.CREATE]
    assert (repository.body_of("docs") or {})["updated_at"] == STORED_UPDATED_AT


def test_registering_different_content_is_a_conflict_carrying_the_existing_status(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    store = make_store(repository, clock)
    store.register(make_new_source("docs"))

    result = store.register(make_new_source("docs", ttl=1))

    assert result == RegistrationConflict(SourceStatus.ACTIVE)
    assert (repository.body_of("docs") or {})["ttl"] == 2_592_000


def test_registering_with_a_different_schedule_cron_is_a_conflict(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body(schedule_cron="0 3 * * *"))

    result = make_store(repository, clock).register(
        make_new_source("docs", schedule_cron="0 4 * * *")
    )

    assert result == RegistrationConflict(SourceStatus.ACTIVE)


def test_registering_with_a_different_connector_type_is_a_conflict(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body(connector_type="web"))

    result = make_store(repository, clock).register(make_new_source("docs"))

    assert result == RegistrationConflict(SourceStatus.ACTIVE)


def test_registering_while_the_source_is_deleting_is_a_conflict_even_with_the_same_content(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body(status="deleting"))

    result = make_store(repository, clock).register(make_new_source("docs"))

    assert result == RegistrationConflict(SourceStatus.DELETING)


def test_registering_over_a_malformed_record_is_a_conflict_with_what_status_can_be_read(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body(ttl="oops"))
    repository.seed("other", stored_body(source_id="other", status=7))

    store = make_store(repository, clock)

    assert store.register(make_new_source("docs")) == RegistrationConflict(SourceStatus.ACTIVE)
    assert store.register(make_new_source("other")) == RegistrationConflict(None)


@pytest.mark.parametrize(
    ("registered", "sent"),
    [
        # schedule_cron の省略は null と同じ(省略は null に正規化される)
        ({"schedule_cron": None}, {"schedule_cron": None}),
        # 数値として比べる(1 と 1.0 は等しい)
        ({"ratio_threshold": 1}, {"ratio_threshold": 1.0}),
        # キーの順を無視する
        (
            {"connector_config": {"a": 1, "b": {"c": [1, 2]}}},
            {"connector_config": {"b": {"c": [1, 2]}, "a": 1}},
        ),
    ],
)
def test_the_comparison_rule_treats_equivalent_values_as_the_same_content(
    repository: InMemoryRepository,
    clock: FixedClock,
    registered: dict[str, object],
    sent: dict[str, object],
) -> None:
    store = make_store(repository, clock)
    store.register(make_new_source("docs", **registered))

    assert isinstance(store.register(make_new_source("docs", **sent)), AlreadyRegistered)


@pytest.mark.parametrize(
    "different_config",
    [{"a": 1.0}, {"a": True}, {"a": "1"}, {"a": [1]}, {"a": 1, "b": 2}, {}],
)
def test_the_comparison_treats_json_type_differences_in_the_connector_config_as_different(
    repository: InMemoryRepository, clock: FixedClock, different_config: dict[str, object]
) -> None:
    store = make_store(repository, clock)
    store.register(make_new_source("docs", connector_config={"a": 1}))

    result = store.register(make_new_source("docs", connector_config=different_config))

    assert isinstance(result, RegistrationConflict)


def test_a_record_that_vanishes_between_the_create_conflict_and_the_read_is_created_again(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    # 1 回目の `create` が `AlreadyExists` と返り、読むとすでに消えている(ソース削除の完了)。
    repository.behavior.inject(ops.CREATE, AlreadyExists())

    result = make_store(repository, clock).register(make_new_source("docs"))

    assert isinstance(result, Registered)
    assert repository.write_calls() == [ops.CREATE, ops.CREATE]


def test_concurrent_registrations_create_exactly_one_record(clock: FixedClock) -> None:
    repository = InMemoryRepository()
    store = make_store(repository, clock)
    results: list[object] = []
    start = threading.Barrier(6, timeout=JOIN_TIMEOUT_SECONDS)

    def register(ttl: int) -> None:
        start.wait()
        results.append(store.register(make_new_source("docs", ttl=ttl)))

    threads = [threading.Thread(target=register, args=(ttl,), daemon=True) for ttl in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=JOIN_TIMEOUT_SECONDS)

    assert [type(result) for result in results].count(Registered) == 1
    assert [type(result) for result in results].count(RegistrationConflict) == 5


def test_registration_retries_a_store_failure_and_the_lost_first_write_is_a_success(
    clock: FixedClock,
) -> None:
    repository = LostResponseRepository()
    repository.lose_response_of(ops.CREATE)

    result = make_store(repository, clock).register(make_new_source("docs"))

    # 最初の `create` は成功していた。リトライの `AlreadyExists` は、同じ内容なので成功(200)。
    assert isinstance(result, AlreadyRegistered)
    assert repository.write_calls() == [ops.CREATE, ops.CREATE]
    assert (repository.body_of("docs") or {})["ttl"] == 2_592_000


def test_registration_gives_up_after_the_retries_with_a_store_failure(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.behavior.inject(ops.CREATE, StoreUnavailableError("timeout"), times=None)

    with pytest.raises(StoreUnavailableError):
        make_store(repository, clock).register(make_new_source("docs"))

    assert repository.write_calls() == [ops.CREATE] * 3  # 試行 3 回


def test_registration_does_not_retry_an_unexpected_response(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.behavior.inject(ops.CREATE, StoreUnexpectedResponseError("http_400"), times=None)

    with pytest.raises(StoreUnexpectedResponseError):
        make_store(repository, clock).register(make_new_source("docs"))

    assert repository.write_calls() == [ops.CREATE]


# --- 更新(crawler-api 4.4.3) ---


def test_updating_replaces_every_changeable_field_and_keeps_the_status_and_connector_type(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body())
    clock.advance(seconds=3600)

    result = make_store(repository, clock).update(
        "docs",
        make_settings(
            connector_config={"root": "/new"},
            ttl=1,
            ratio_threshold=0.5,
            min_delete_count=2,
            schedule_cron=None,
        ),
    )

    assert isinstance(result, Updated)
    assert repository.body_of("docs") == stored_body(
        connector_config={"root": "/new"},
        ttl=1,
        ratio_threshold=0.5,
        min_delete_count=2,
        schedule_cron=None,
        updated_at="2026-11-13T01:00:00.000Z",
    )
    assert result.record.updated_at == DEFAULT_NOW + timedelta(hours=1)


def test_updating_with_the_same_content_does_not_write_and_keeps_the_updated_time(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body())
    clock.advance(seconds=3600)

    result = make_store(repository, clock).update("docs", make_settings())

    assert isinstance(result, Unchanged)
    assert result.record.updated_at == DEFAULT_NOW
    assert repository.write_calls() == []
    assert (repository.body_of("docs") or {})["updated_at"] == STORED_UPDATED_AT


def test_updating_a_missing_source_reports_not_found_without_writing(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    assert make_store(repository, clock).update("docs", make_settings()) == SourceNotFound()
    assert repository.write_calls() == []


def test_updating_a_deleting_source_is_rejected_without_writing(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body(status="deleting"))

    result = make_store(repository, clock).update("docs", make_settings(ttl=1))

    assert result == SourceIsDeleting()
    assert repository.write_calls() == []
    assert (repository.body_of("docs") or {})["status"] == "deleting"


def test_the_update_is_conditioned_on_the_version_it_read(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    seeded = repository.seed("docs", stored_body())

    make_store(repository, clock).update("docs", make_settings(ttl=1))

    # 読んだ版(`seq_no`)の次の版になっている = その版を条件に書いた。
    assert seeded.seq_no < (repository.fetch("docs") or seeded).seq_no
    assert repository.write_calls() == [ops.REPLACE]


def test_a_concurrent_deleting_update_wins_and_the_update_does_not_revert_the_status(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body())
    # 読んだ後・書く前に、ソース削除ジョブが `deleting` に更新する。
    repository.behavior.before(
        ops.REPLACE, lambda: repository.seed("docs", stored_body(status="deleting"))
    )

    result = make_store(repository, clock).update("docs", make_settings(ttl=1))

    # 版が合わず、読み直すと `deleting` なので 409(`active` に戻さない)。
    assert result == SourceIsDeleting()
    assert (repository.body_of("docs") or {})["status"] == "deleting"
    assert (repository.body_of("docs") or {})["ttl"] == 2_592_000


def test_a_conflict_with_another_update_is_retried_from_a_fresh_read(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body())
    repository.behavior.before(ops.REPLACE, lambda: repository.seed("docs", stored_body(ttl=5)))

    result = make_store(repository, clock).update("docs", make_settings(ttl=1))

    assert isinstance(result, Updated)
    assert (repository.body_of("docs") or {})["ttl"] == 1
    assert repository.write_calls() == [ops.REPLACE, ops.REPLACE]


def test_an_update_that_keeps_conflicting_becomes_a_store_failure(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body())
    # 競合が解けない状態(書く直前に毎回別の書き込みが入る)。リトライ 3 回、各 2 回ぶん。
    for _ in range(6):
        repository.behavior.before(
            ops.REPLACE, lambda: repository.seed("docs", stored_body(ttl=5)), key="docs"
        )

    with pytest.raises(StoreUnavailableError) as raised:
        make_store(repository, clock, max_conflict_attempts=2).update("docs", make_settings(ttl=1))

    assert raised.value.reason == "source_update_contention"
    assert repository.write_calls() == [ops.REPLACE] * 6


def test_an_update_whose_record_vanished_during_the_write_reports_not_found(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body())
    # 記録がない場合の版条件つき書き込みは `Conflict`(実 OpenSearch 3.9.0)。読み直して判定する。
    repository.behavior.before(ops.REPLACE, lambda: repository.delete_ids(["docs"]))

    result = make_store(repository, clock).update("docs", make_settings(ttl=1))

    assert result == SourceNotFound()


def test_an_update_whose_first_write_succeeded_but_lost_its_response_is_not_a_conflict(
    clock: FixedClock,
) -> None:
    repository = LostResponseRepository()
    repository.seed("docs", stored_body())
    repository.lose_response_of(ops.REPLACE)

    result = make_store(repository, clock).update("docs", make_settings(ttl=1))

    # リトライは読み直し、すでに同じ内容なので変更なし(200)。書き込みは 1 回だけ。
    assert isinstance(result, Unchanged)
    assert repository.write_calls() == [ops.REPLACE]
    assert (repository.body_of("docs") or {})["ttl"] == 1


def test_an_update_repairs_an_active_record_whose_fields_are_malformed(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body(ttl="oops", min_delete_count=None))

    result = make_store(repository, clock).update("docs", make_settings())

    assert isinstance(result, Updated)
    assert (repository.body_of("docs") or {})["ttl"] == 2_592_000


@pytest.mark.parametrize(
    "bad_field", [{"status": "unknown"}, {"status": None}, {"connector_type": 3}]
)
def test_an_update_refuses_a_record_whose_status_or_connector_type_cannot_be_kept(
    repository: InMemoryRepository, clock: FixedClock, bad_field: dict[str, object]
) -> None:
    repository.seed("docs", stored_body(**bad_field))

    with pytest.raises(StoreUnexpectedResponseError) as raised:
        make_store(repository, clock).update("docs", make_settings(ttl=1))

    assert raised.value.error_type == "malformed_source_record"
    assert repository.write_calls() == []


def test_updating_retries_a_store_failure_in_the_whole_operation(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body())
    repository.behavior.inject(ops.FETCH, StoreUnavailableError("timeout"), times=2)

    result = make_store(repository, clock).update("docs", make_settings(ttl=1))

    assert isinstance(result, Updated)
    assert len(repository.behavior.calls_of(ops.FETCH)) == 3


def test_updating_gives_up_after_three_attempts(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.behavior.inject(ops.FETCH, StoreUnavailableError("timeout"), times=None)

    with pytest.raises(StoreUnavailableError):
        make_store(repository, clock).update("docs", make_settings())

    assert len(repository.behavior.calls_of(ops.FETCH)) == 3


# --- 読み取り・一覧 ---


def test_fetch_returns_the_whole_record_as_one_value(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body())

    record = SourceReader(repository).fetch("docs")

    assert record == SourceRecord(
        source_id="docs",
        connector_type="file_system",
        connector_config={"root": "/data", "token": SECRET_REFERENCE},
        ttl=2_592_000,
        ratio_threshold=0.3,
        min_delete_count=10,
        schedule_cron="0 3 * * *",
        status=SourceStatus.ACTIVE,
        updated_at=DEFAULT_NOW,
    )
    assert len(repository.behavior.calls_of(ops.FETCH)) == 1  # 1 回の読み取り


def test_fetch_of_a_missing_source_is_none(repository: InMemoryRepository) -> None:
    assert SourceReader(repository).fetch("docs") is None


@pytest.mark.parametrize(
    ("overrides", "invalid_fields"),
    [
        ({"ttl": None}, ("ttl",)),
        ({"ttl": 1.5}, ("ttl",)),
        ({"ttl": True}, ("ttl",)),
        ({"ratio_threshold": "0.3"}, ("ratio_threshold",)),
        ({"ratio_threshold": float("nan")}, ("ratio_threshold",)),
        ({"min_delete_count": "10"}, ("min_delete_count",)),
        ({"connector_config": None}, ("connector_config",)),
        ({"connector_config": []}, ("connector_config",)),
        ({"connector_type": None}, ("connector_type",)),
        ({"schedule_cron": "* * * *"}, ("schedule_cron",)),
        ({"schedule_cron": 86_400}, ("schedule_cron",)),
        ({"schedule_cron": "@daily"}, ("schedule_cron",)),
        ({"updated_at": "yesterday"}, ("updated_at",)),
        ({"updated_at": "2026-11-13T00:00:00"}, ("updated_at",)),
        ({"updated_at": 5}, ("updated_at",)),
        ({"source_id": "other"}, ("source_id",)),
        ({"ttl": None, "min_delete_count": None}, ("ttl", "min_delete_count")),
    ],
)
def test_fetch_reports_missing_or_mistyped_fields_by_name_only(
    repository: InMemoryRepository, overrides: dict[str, object], invalid_fields: tuple[str, ...]
) -> None:
    repository.seed("docs", stored_body(**overrides))

    record = SourceReader(repository).fetch("docs")

    assert isinstance(record, MalformedSourceRecord)
    assert record.invalid_fields == invalid_fields
    assert record.status is SourceStatus.ACTIVE


def test_a_missing_field_is_reported_as_malformed(repository: InMemoryRepository) -> None:
    body = stored_body()
    del body["ttl"]
    del body["connector_config"]
    repository.seed("docs", body)

    record = SourceReader(repository).fetch("docs")

    assert isinstance(record, MalformedSourceRecord)
    assert record.invalid_fields == ("connector_config", "ttl")


def test_a_missing_schedule_cron_is_a_manual_only_source(
    repository: InMemoryRepository,
) -> None:
    body = stored_body()
    del body["schedule_cron"]
    repository.seed("docs", body)

    record = SourceReader(repository).fetch("docs")

    assert isinstance(record, SourceRecord)
    assert record.schedule_cron is None


def test_a_malformed_record_keeps_a_readable_status_so_that_deleting_can_be_seen(
    repository: InMemoryRepository,
) -> None:
    repository.seed("docs", stored_body(ttl=None, status="deleting"))
    repository.seed("junk", stored_body(source_id="junk", status="bogus", ttl=None))

    reader = SourceReader(repository)

    deleting = reader.fetch("docs")
    junk = reader.fetch("junk")
    assert isinstance(deleting, MalformedSourceRecord)
    assert deleting.status is SourceStatus.DELETING
    assert isinstance(junk, MalformedSourceRecord)
    assert junk.status is None
    assert junk.invalid_fields == ("ttl", "status")


def test_the_connector_config_never_appears_in_reprs_or_malformed_reports(
    repository: InMemoryRepository,
) -> None:
    repository.seed("docs", stored_body())
    repository.seed("broken", stored_body(source_id="broken", ttl=None))
    reader = SourceReader(repository)

    valid = reader.fetch("docs")
    broken = reader.fetch("broken")

    assert SECRET_REFERENCE not in repr(valid)
    assert SECRET_REFERENCE not in repr(broken)
    assert SECRET_REFERENCE not in repr(make_settings())
    assert SECRET_REFERENCE not in repr(make_new_source())


def test_list_sources_returns_all_records_ordered_by_source_id(
    repository: InMemoryRepository,
) -> None:
    for source_id in ("zeta", "alpha", "mid"):
        repository.seed(source_id, stored_body(source_id=source_id))
    repository.seed("broken", stored_body(source_id="broken", ttl=None))

    sources = SourceReader(repository).list_sources()

    assert [source.source_id for source in sources] == ["alpha", "broken", "mid", "zeta"]
    assert isinstance(sources[1], MalformedSourceRecord)


def test_list_scheduled_active_sources_excludes_manual_only_and_deleting_sources(
    repository: InMemoryRepository,
) -> None:
    repository.seed("scheduled", stored_body(source_id="scheduled"))
    repository.seed("manual", stored_body(source_id="manual", schedule_cron=None))
    repository.seed("deleting", stored_body(source_id="deleting", status="deleting"))

    sources = SourceReader(repository).list_scheduled_active_sources()

    assert [source.source_id for source in sources] == ["scheduled"]


@pytest.mark.parametrize("updated_at", ["9999-12-31T23:59:59-05:00", "0001-01-01T00:00:00+09:00"])
def test_an_out_of_range_updated_at_makes_only_that_record_malformed(
    repository: InMemoryRepository, updated_at: str
) -> None:
    repository.seed("docs", stored_body(updated_at=updated_at))
    repository.seed("wiki", stored_body(source_id="wiki"))

    sources = SourceReader(repository).list_sources()

    assert [type(source) for source in sources] == [MalformedSourceRecord, SourceRecord]
    assert sources[0].invalid_fields == ("updated_at",)  # type: ignore[union-attr]


def test_a_truncated_source_list_is_not_returned_as_a_success(
    repository: InMemoryRepository,
) -> None:
    full_page = [
        StoredRecord(f"s{i}", stored_body(source_id=f"s{i}"), i, 1) for i in range(LIST_MAX_SIZE)
    ]
    repository.behavior.inject(ops.LIST, full_page)

    with pytest.raises(StoreUnexpectedResponseError) as raised:
        SourceReader(repository).list_sources()

    assert raised.value.error_type == "source_list_truncated"


# --- deleting への更新と削除(ソース削除の順 0・5) ---


def test_mark_deleting_changes_only_the_status(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body())
    clock.advance(seconds=3600)

    assert make_store(repository, clock).mark_deleting("docs") == MarkedDeleting()

    assert repository.body_of("docs") == stored_body(status="deleting")  # updated_at も保つ


def test_mark_deleting_twice_is_idempotent_and_writes_once(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body())
    store = make_store(repository, clock)

    assert store.mark_deleting("docs") == MarkedDeleting()
    assert store.mark_deleting("docs") == MarkedDeleting()

    assert repository.write_calls() == [ops.REPLACE]


def test_mark_deleting_a_missing_source_reports_not_found(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    assert make_store(repository, clock).mark_deleting("docs") == SourceNotFound()


def test_mark_deleting_works_on_a_malformed_record_so_that_it_can_be_deleted(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body(ttl=None, status="bogus"))

    assert make_store(repository, clock).mark_deleting("docs") == MarkedDeleting()

    assert (repository.body_of("docs") or {})["status"] == "deleting"


def test_mark_deleting_rereads_after_a_version_conflict_and_keeps_the_new_content(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body())
    repository.behavior.before(ops.REPLACE, lambda: repository.seed("docs", stored_body(ttl=5)))

    assert make_store(repository, clock).mark_deleting("docs") == MarkedDeleting()

    assert repository.body_of("docs") == stored_body(ttl=5, status="deleting")


def test_mark_deleting_whose_first_write_was_lost_is_a_success_without_a_second_write(
    clock: FixedClock,
) -> None:
    repository = LostResponseRepository()
    repository.seed("docs", stored_body())
    repository.lose_response_of(ops.REPLACE)
    store = make_store(repository, clock)

    with pytest.raises(StoreUnavailableError):
        store.mark_deleting("docs")  # 呼び出し側(`JobContext`)がリトライする
    assert store.mark_deleting("docs") == MarkedDeleting()

    assert repository.write_calls() == [ops.REPLACE]


def test_mark_deleting_that_keeps_conflicting_becomes_a_store_failure(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body())
    for _ in range(2):
        repository.behavior.before(
            ops.REPLACE, lambda: repository.seed("docs", stored_body(ttl=5)), key="docs"
        )

    with pytest.raises(StoreUnavailableError) as raised:
        make_store(repository, clock, max_conflict_attempts=2).mark_deleting("docs")

    assert raised.value.reason == "source_update_contention"


def test_delete_removes_a_deleting_record(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body(status="deleting"))

    assert make_store(repository, clock).delete("docs") == SourceDeleted()

    assert repository.body_of("docs") is None
    assert repository.write_calls() == [ops.DELETE]


def test_delete_of_a_missing_record_is_a_success(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    assert make_store(repository, clock).delete("docs") == SourceDeleted()
    assert repository.write_calls() == []


def test_delete_refuses_a_record_that_is_not_deleting(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body())

    assert make_store(repository, clock).delete("docs") == SourceNotDeleting()

    assert repository.body_of("docs") is not None
    assert repository.write_calls() == []


def test_delete_does_not_remove_a_record_that_became_active_after_it_was_read(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    repository.seed("docs", stored_body(status="deleting"))
    repository.behavior.before(ops.DELETE, lambda: repository.seed("docs", stored_body()))

    result = make_store(repository, clock).delete("docs")

    # 版が合わず、読み直すと `active`。消さない。
    assert result == SourceNotDeleting()
    assert repository.body_of("docs") is not None


def test_delete_whose_first_write_was_lost_is_a_success_on_the_retry(clock: FixedClock) -> None:
    repository = LostResponseRepository()
    repository.seed("docs", stored_body(status="deleting"))
    repository.lose_response_of(ops.DELETE)
    store = make_store(repository, clock)

    with pytest.raises(StoreUnavailableError):
        store.delete("docs")
    assert store.delete("docs") == SourceDeleted()  # すでにない = 成功


def test_a_deleted_source_can_be_registered_again(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    store = make_store(repository, clock)
    store.register(make_new_source("docs"))
    store.mark_deleting("docs")
    store.delete("docs")

    assert isinstance(store.register(make_new_source("docs", ttl=1)), Registered)


# --- R7: 書き込みは create か読んだ版を条件にした操作だけ ---


def test_every_write_is_a_create_or_version_conditioned(
    repository: InMemoryRepository, clock: FixedClock
) -> None:
    store = make_store(repository, clock)
    store.register(make_new_source("docs"))
    store.update("docs", make_settings(ttl=1))
    store.mark_deleting("docs")
    store.delete("docs")

    assert repository.write_calls() == [ops.CREATE, ops.REPLACE, ops.REPLACE, ops.DELETE]
