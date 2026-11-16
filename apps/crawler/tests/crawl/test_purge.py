"""スキップ記録・原本サイズ超過記録の整理(architecture 6.4。テスト観点 #24)。

整理は、列挙が `Completed` で、すべての応答を確認し終えた後にだけ行う。失敗したクロールでは
整理しない(残すべき記録を失わないため)。
"""

from contextlib import AbstractContextManager

import pytest

from loreley_crawler.common.errors import StoreUnexpectedResponseError
from loreley_crawler.connectors.interface import (
    Completed,
    ConnectorError,
    DocumentRef,
    ErrorCategory,
)
from loreley_crawler.crawl.executor import ReadyToFinish
from loreley_crawler.documents import DocumentsSettings
from loreley_crawler.infrastructure.indexer_client import FailureType, IndexerRejected
from loreley_crawler.jobs import StoreWriteFailedError
from tests.crawl.support import CrawlEnv, crawl_env, document_id_of
from tests.fakes import in_memory_repository as ops
from tests.fakes.fake_connector import FETCH, fetched_document
from tests.fakes.fake_indexer_client import REGISTER_DOCUMENTS
from tests.jobs.support import SOURCE_ID


def seed_previous_records(env: CrawlEnv) -> dict[str, str]:
    """前回までの記録を置く。今回のクロールとの関係は、名前に書いた。"""
    ids = {
        "skip_now_registered": env.seed_document_record("skip", "now-registered"),
        "skip_still_failing": env.seed_document_record(
            "skip", "still-failing", consecutive_skips=2, attempts=1, stage="fetch"
        ),
        "skip_vanished": env.seed_document_record("skip", "vanished"),
        "oversize_now_fits": env.seed_document_record("oversize", "now-fits"),
        "oversize_still_big": env.seed_document_record("oversize", "still-big"),
        "oversize_vanished": env.seed_document_record("oversize", "vanished-big"),
    }
    # 他のソースの記録・ロック文書・ジョブ記録は消さない。
    other_id = f"skip-other-{document_id_of('now-registered')}"
    env.jobs.jobs_repository.seed(
        other_id,
        {
            "record_type": "skip",
            "source_id": "other",
            "document_id": document_id_of("now-registered"),
        },
    )
    ids["other_source"] = other_id
    return ids


def crawl_environment() -> AbstractContextManager[CrawlEnv]:
    """前回のスキップ記録・原本サイズ超過記録が残る状態で、今回のクロールを始める環境。"""
    refs = [
        DocumentRef(name, name)
        for name in ["now-registered", "still-failing", "now-fits", "still-big", "fresh"]
    ]
    documents = {
        "now-registered": fetched_document(b"ok"),
        "now-fits": fetched_document(b"ok"),
        "still-big": fetched_document(b"x" * 100),
        "fresh": fetched_document(b"ok"),
    }
    return crawl_env(
        items=[*refs, Completed()],
        documents=documents,
        documents_settings=DocumentsSettings(max_raw_bytes=10),
    )


def existing(env: CrawlEnv, ids: dict[str, str]) -> set[str]:
    present = set(env.jobs.jobs_repository.record_ids())
    return {name for name, record_id in ids.items() if record_id in present}


def test_a_completed_crawl_purges_records_of_registered_and_vanished_documents() -> None:
    with crawl_environment() as env:
        ids = seed_previous_records(env)
        env.connector.behavior.inject(
            FETCH,
            ConnectorError.of(ErrorCategory.FETCH_NOT_FOUND, "gone"),
            key="still-failing",
            times=None,
        )

        result = env.run()

        assert isinstance(result, ReadyToFinish)
        # (a) 今回登録された文書の記録と、(b) 今回列挙されなかった文書の記録が消える。
        # スキップした文書・原本サイズ超過の文書の記録は残る。
        assert existing(env, ids) == {"skip_still_failing", "oversize_still_big", "other_source"}


def test_the_record_of_a_document_skipped_again_is_updated_not_recreated() -> None:
    with crawl_environment() as env:
        ids = seed_previous_records(env)
        env.connector.behavior.inject(
            FETCH,
            ConnectorError.of(ErrorCategory.FETCH_NOT_FOUND, "gone"),
            key="still-failing",
            times=None,
        )

        env.run()

        record = env.jobs.jobs_repository.body_of(ids["skip_still_failing"])
        assert record is not None
        assert record["consecutive_skips"] == 3
        assert record["last_job_id"] == env.context.job_id


def test_the_purge_scans_once_per_record_type_and_leaves_no_scan_open() -> None:
    with crawl_environment() as env:
        seed_previous_records(env)

        env.run()

        repository = env.jobs.jobs_repository
        assert len(repository.behavior.calls_of(ops.SCAN)) == 2  # skip と oversize を別々に
        assert repository.open_scan_count == 0


def test_the_purge_leaves_other_sources_locks_and_jobs_alone() -> None:
    with crawl_environment() as env:
        seed_previous_records(env)

        env.run()

        assert env.jobs.lock_body(SOURCE_ID) is not None
        assert env.jobs.job_body(env.context.job_id)["status"] == "running"


def test_a_failed_crawl_does_not_purge() -> None:  # 観点 #24
    with crawl_environment() as env:
        ids = seed_previous_records(env)
        env.indexer.behavior.inject(REGISTER_DOCUMENTS, IndexerRejected(400, "invalid_request"))

        env.run()

        assert env.job_body()["status"] == "failed"
        assert existing(env, ids) == set(ids)
        repository = env.jobs.jobs_repository
        assert repository.behavior.calls_of(ops.SCAN, ops.DELETE_IDS) == []


def test_an_enumeration_failure_does_not_purge() -> None:
    items = [
        DocumentRef("now-registered", "now-registered"),
        ConnectorError.of(ErrorCategory.ENUMERATION_INCOMPLETE, "失敗"),
    ]
    with crawl_env(items=items, documents={"now-registered": fetched_document(b"ok")}) as env:
        ids = {"skip": env.seed_document_record("skip", "now-registered")}

        env.run()

        assert existing(env, ids) == {"skip"}


def test_the_skip_record_of_a_document_that_is_now_oversize_is_purged() -> None:
    # 記録は種類ごとに判定する: `skip` 記録は、今回スキップした文書のものだけ残す。
    with crawl_env(
        files={"big": b"x" * 100}, documents_settings=DocumentsSettings(max_raw_bytes=10)
    ) as env:
        stale_skip = env.seed_document_record("skip", "big")

        env.run()

        assert stale_skip not in env.jobs.jobs_repository.record_ids()
        assert len(env.oversize_record_ids()) == 1  # 今回の原本サイズ超過の記録は残る


def test_the_oversize_record_of_a_document_that_is_now_skipped_is_purged() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        stale_oversize = env.seed_document_record("oversize", "a")
        env.connector.behavior.inject(
            FETCH, ConnectorError.of(ErrorCategory.FETCH_NOT_FOUND, "gone"), key="a", times=None
        )

        env.run()

        assert stale_oversize not in env.jobs.jobs_repository.record_ids()
        assert len(env.skip_record_ids()) == 1  # 今回のスキップの記録は残る


def test_a_record_stays_while_the_document_keeps_the_same_kind_of_result() -> None:
    with crawl_env(
        files={"big": b"x" * 100}, documents_settings=DocumentsSettings(max_raw_bytes=10)
    ) as env:
        kept = env.seed_document_record("oversize", "big")

        env.run()

        assert kept in env.jobs.jobs_repository.record_ids()


def test_a_partial_bulk_delete_that_never_succeeds_raises_a_store_write_failure() -> None:
    with crawl_env(files={"a": b"ok"}) as env:
        record_id = env.seed_document_record("skip", "a")
        env.jobs.jobs_repository.fail_bulk_delete_of([record_id], times=None)

        with pytest.raises(StoreWriteFailedError):
            env.run()

        assert env.job_body()["status"] == "running"  # 最終対応は P6b
        assert env.connector.close_count == 1
        # 登録結果の確定は、整理の前(手順 11)。整理に失敗しても、確定した値は戻らない。
        assert env.job_body()["registration"]["partial"] is False


def test_an_unexpected_store_response_during_the_purge_propagates() -> None:
    with crawl_env(files={"a": b"ok"}) as env:
        env.jobs.jobs_repository.behavior.inject(
            ops.SCAN, StoreUnexpectedResponseError("http_400"), times=None
        )

        with pytest.raises(StoreUnexpectedResponseError):
            env.run()


def test_rejected_documents_are_kept_in_the_skip_records_after_the_purge() -> None:
    with crawl_env(files={"a": b"1", "b": b"2"}) as env:
        env.indexer.registration_failures["b"] = FailureType.DOCUMENT_REJECTED
        stale = env.seed_document_record("skip", "a")

        env.run()

        records = set(env.skip_record_ids())
        assert records == {f"skip-{SOURCE_ID}-{document_id_of('b')}"}
        assert stale not in records
