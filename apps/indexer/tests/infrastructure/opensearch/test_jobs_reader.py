import logging
from datetime import UTC, datetime

import pytest

from loreley_indexer.common.locks import LockRecord
from loreley_indexer.infrastructure.opensearch import StoreJobsReader
from tests.documents.factories import MALFORMED_MAINTENANCE_BODIES
from tests.fakes.in_memory_store import InMemoryStore


def test_fetch_lock_parses_the_provisional_lock_document(jobs_store: InMemoryStore) -> None:
    jobs_store.seed(
        "lock-s1",
        {"owner": "crawler-1", "job_id": "job-1", "lease_expires_at": "2026-11-11T09:00:00+09:00"},
    )

    lock = StoreJobsReader(jobs_store).fetch_lock("s1")

    assert lock == LockRecord(
        owner="crawler-1",
        job_id="job-1",
        lease_expires_at=datetime(2026, 11, 11, 0, 0, tzinfo=UTC),
    )


def test_fetch_lock_returns_none_without_a_lock_document(jobs_store: InMemoryStore) -> None:
    assert StoreJobsReader(jobs_store).fetch_lock("s1") is None


def test_fetch_lock_treats_a_malformed_document_as_no_lock(jobs_store: InMemoryStore) -> None:
    jobs_store.seed("lock-s1", {"owner": "crawler-1", "job_id": 7, "lease_expires_at": "x"})
    jobs_store.seed("lock-s2", {"owner": "c", "job_id": "j", "lease_expires_at": "not-a-date"})
    jobs_store.seed(
        "lock-s3", {"owner": "c", "job_id": "j", "lease_expires_at": "2026-11-11T00:00:00"}
    )
    reader = StoreJobsReader(jobs_store)

    assert reader.fetch_lock("s1") is None
    assert reader.fetch_lock("s2") is None
    assert reader.fetch_lock("s3") is None


def test_maintenance_flag_is_off_without_a_document(jobs_store: InMemoryStore) -> None:
    assert not StoreJobsReader(jobs_store).is_maintenance_enabled()


def test_maintenance_flag_follows_the_enabled_field(jobs_store: InMemoryStore) -> None:
    reader = StoreJobsReader(jobs_store)

    jobs_store.seed("maintenance", {"enabled": True})
    assert reader.is_maintenance_enabled()

    jobs_store.seed("maintenance", {"enabled": False})
    assert not reader.is_maintenance_enabled()


@pytest.mark.parametrize("body", MALFORMED_MAINTENANCE_BODIES)
def test_a_malformed_maintenance_flag_counts_as_enabled(  # fail-closed(0014)
    jobs_store: InMemoryStore, body: dict[str, object], caplog: pytest.LogCaptureFixture
) -> None:
    jobs_store.seed("maintenance", body)

    with caplog.at_level(logging.DEBUG):
        assert StoreJobsReader(jobs_store).is_maintenance_enabled()

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].getMessage() == (
        "the maintenance flag is malformed, treated as enabled: record_id=maintenance field=enabled"
    )


def test_a_malformed_maintenance_flag_is_warned_once_per_process_then_logged_at_debug(
    jobs_store: InMemoryStore, caplog: pytest.LogCaptureFixture
) -> None:
    """判定・バッチ・要約のたびに読まれる。WARNING が毎回出ると洪水になる。"""
    jobs_store.seed("maintenance", {"enabled": "yes"})
    reader = StoreJobsReader(jobs_store)

    with caplog.at_level(logging.DEBUG):
        results = [reader.is_maintenance_enabled() for _ in range(5)]

    assert results == [True] * 5  # fail-closed は、警告の抑制と無関係に毎回効く
    levels = [record.levelno for record in caplog.records]
    assert levels == [logging.WARNING] + [logging.DEBUG] * 4


def test_the_malformed_flag_warning_is_per_reader_not_global(
    jobs_store: InMemoryStore, caplog: pytest.LogCaptureFixture
) -> None:
    """抑制はリーダー(プロセスで 1 つ)ごと。別のリーダーは、あらためて警告する。"""
    jobs_store.seed("maintenance", {"enabled": 1})

    with caplog.at_level(logging.WARNING):
        StoreJobsReader(jobs_store).is_maintenance_enabled()
        StoreJobsReader(jobs_store).is_maintenance_enabled()

    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2


def test_a_malformed_maintenance_flag_never_logs_its_value(
    jobs_store: InMemoryStore, caplog: pytest.LogCaptureFixture
) -> None:
    jobs_store.seed("maintenance", {"enabled": "SENTINEL-VALUE"})

    with caplog.at_level(logging.DEBUG):
        StoreJobsReader(jobs_store).is_maintenance_enabled()

    assert "SENTINEL-VALUE" not in caplog.text


def test_a_well_formed_maintenance_flag_does_not_log(
    jobs_store: InMemoryStore, caplog: pytest.LogCaptureFixture
) -> None:
    reader = StoreJobsReader(jobs_store)
    with caplog.at_level(logging.DEBUG):
        reader.is_maintenance_enabled()  # 文書なし
        jobs_store.seed("maintenance", {"enabled": True})
        reader.is_maintenance_enabled()
        jobs_store.seed("maintenance", {"enabled": False})
        reader.is_maintenance_enabled()

    assert caplog.records == []


def test_jobs_reader_never_writes_to_the_jobs_index(jobs_store: InMemoryStore) -> None:
    reader = StoreJobsReader(jobs_store)
    reader.fetch_lock("s1")
    reader.is_maintenance_enabled()
    assert jobs_store.write_calls() == []
    assert not hasattr(reader, "save")
    assert not hasattr(reader, "delete")
