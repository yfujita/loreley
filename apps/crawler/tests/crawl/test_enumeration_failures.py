"""列挙の失敗と、確認点での中断(architecture 4.6・4.8・6.2・7.7。テスト観点 #21)。

列挙の `Failed`・`external_id` の衝突・列挙した文書数の上限超過は、以降のチャンクを処理せず
ジョブを `failed` にする。取り消し・所有権の喪失・メンテナンスは `JobInterrupted` として伝播する
(最終対応は P6b)。
"""

import pytest

from loreley_crawler.connectors.interface import (
    Completed,
    ConnectorError,
    DocumentRef,
    ErrorCategory,
    ErrorScope,
)
from loreley_crawler.crawl import CrawlSettings
from loreley_crawler.crawl.executor import FailureRecorded, ReadyToFinish
from loreley_crawler.documents import DocumentsSettings
from loreley_crawler.infrastructure.indexer_client import IndexerRejected
from loreley_crawler.jobs import CancellationRequested, MaintenanceDetected, OwnershipLost
from tests.crawl.support import CrawlEnv, crawl_env, document_id_of
from tests.fakes.fake_connector import FETCH, NEXT
from tests.fakes.fake_indexer_client import REGISTER_DOCUMENTS, REPORT_LAST_SEEN


def assert_failed(env: CrawlEnv, result: object, reason: str) -> None:
    assert isinstance(result, FailureRecorded)
    assert env.job_body()["status"] == "failed"
    assert env.job_body()["failure_reason"] == reason


@pytest.mark.parametrize(
    "category",
    [
        ErrorCategory.SOURCE_UNREACHABLE,
        ErrorCategory.SOURCE_NOT_FOUND,
        ErrorCategory.SOURCE_ACCESS_DENIED,
        ErrorCategory.ENUMERATION_INCOMPLETE,
    ],
)
def test_an_enumeration_failure_fails_the_job_with_the_category_and_message(
    category: ErrorCategory,
) -> None:
    items = [DocumentRef("a", "a"), ConnectorError.of(category, "列挙に失敗した")]
    with crawl_env(items=items) as env:
        assert_failed(env, env.run(), "enumeration_failed")

        assert env.job_body()["failure_detail"] == f"{category.value}: 列挙に失敗した"


def test_an_enumeration_connector_internal_error_fails_the_job() -> None:
    error = ConnectorError.of(
        ErrorCategory.CONNECTOR_INTERNAL_ERROR, "想定外", scope=ErrorScope.SOURCE
    )
    with crawl_env(items=[error]) as env:
        assert_failed(env, env.run(), "enumeration_failed")


def test_an_enumeration_failure_stops_before_the_chunk_in_progress_is_processed() -> None:
    items = [
        DocumentRef("a", "a"),
        DocumentRef("b", "b"),
        DocumentRef("c", "c"),
        ConnectorError.of(ErrorCategory.ENUMERATION_INCOMPLETE, "失敗"),
    ]
    with crawl_env(
        items=items,
        documents={},
        settings=CrawlSettings(chunk_size=2),
    ) as env:
        env.run()

        # 1 つ目のチャンク(a・b)は処理済み。失敗したチャンク(c)は処理しない。
        assert len(env.indexer.calls_of(REPORT_LAST_SEEN)) == 1
        assert env.job_body()["registration"]["enumerated_count"] == 3


def test_an_external_id_collision_fails_the_job_with_the_colliding_document_id() -> (
    None
):  # 観点 #21
    # NFC と NFD は同じ `document_id` になるが、元の `external_id` は別(衝突)。
    nfc = "café.txt"
    nfd = "café.txt"
    with crawl_env(items=[DocumentRef(nfc, "nfc"), DocumentRef(nfd, "nfd"), Completed()]) as env:
        assert_failed(env, env.run(), "external_id_collision")

        detail = env.job_body()["failure_detail"]
        assert document_id_of(nfc) in detail
        assert env.indexer.calls_of(REGISTER_DOCUMENTS) == []


def test_a_duplicate_with_the_same_raw_external_id_is_not_a_collision() -> None:
    with crawl_env(items=[DocumentRef("a", "a"), DocumentRef("a", "a"), Completed()]) as env:
        result = env.run()

        assert isinstance(result, ReadyToFinish)
        assert result.run.enumeration is not None
        assert result.run.enumeration.enumerated_count == 1


def test_exceeding_the_enumerated_document_limit_fails_the_job() -> None:
    refs = [DocumentRef(f"f{i}", i) for i in range(3)]
    with crawl_env(
        items=[*refs, Completed()],
        documents_settings=DocumentsSettings(max_enumerated_documents=2),
    ) as env:
        assert_failed(env, env.run(), "enumeration_too_large")

        assert env.job_body()["failure_detail"] == "列挙した文書数が上限 2 件を超えた"


def test_an_unexpected_exception_from_the_enumeration_becomes_a_connector_internal_error() -> None:
    with crawl_env(items=[Completed()]) as env:
        env.connector.behavior.inject(NEXT, RuntimeError("boom with /secret/path"))

        assert_failed(env, env.run(), "enumeration_failed")

        detail = env.job_body()["failure_detail"]
        assert detail.startswith("connector_internal_error")
        assert "/secret/path" not in detail


def test_a_cancel_request_during_enumeration_propagates_and_closes_the_resources() -> None:
    with crawl_env(items=[DocumentRef("a", "a"), Completed()]) as env:
        # 開始通知の後、列挙の途中で取り消し要求が届く。
        env.connector.behavior.before(
            NEXT, lambda: env.jobs.cancel_requests.request(env.context.job_id)
        )

        with pytest.raises(CancellationRequested):
            env.run()

        assert env.indexer.operations() == ["start_crawl"]
        assert env.connector.close_count == 1
        assert [stream.closed for stream in env.connector.streams] == [True]
        assert env.job_body()["status"] == "running"  # 最終対応は P6b


def test_a_cancel_request_stops_an_enumeration_that_sends_no_request() -> None:
    # 識別子エラーの文書だけが続く列挙は、Indexer を呼ばない。列挙の途中でも確認点を通す。
    refs = [DocumentRef(f"/bad{i}", i) for i in range(3)]
    with crawl_env(items=[*refs, Completed()]) as env:
        env.connector.behavior.before(
            NEXT, lambda: env.jobs.cancel_requests.request(env.context.job_id)
        )

        with pytest.raises(CancellationRequested):
            env.run()

        assert len(env.connector.behavior.calls_of(NEXT)) == 1  # 列挙を読み進めない


def test_a_cancel_request_between_two_fetches_stops_before_the_next_document() -> None:
    with crawl_env(files={"a": b"1", "b": b"2"}) as env:
        env.connector.behavior.before(
            FETCH, lambda: env.jobs.cancel_requests.request(env.context.job_id)
        )

        with pytest.raises(CancellationRequested):
            env.run()

        assert [ref.locator for ref, _max_bytes in env.connector.fetch_calls] == ["a"]
        assert env.indexer.calls_of(REGISTER_DOCUMENTS) == []  # 取得済みの 1 件も登録しない
        assert env.connector.close_count == 1


def test_a_cancel_request_before_a_last_seen_request_stops_it() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.before(
            "start_crawl", lambda: env.jobs.cancel_requests.request(env.context.job_id)
        )

        with pytest.raises(CancellationRequested):
            env.run()

        assert env.indexer.operations() == ["start_crawl"]


def test_a_lost_lease_stops_further_requests() -> None:
    with crawl_env(files={"a": b"1", "b": b"2"}) as env:
        env.indexer.behavior.before(
            REPORT_LAST_SEEN, lambda: env.heartbeat.record_loss("lock_missing")
        )

        with pytest.raises(OwnershipLost) as raised:
            env.run()

        assert raised.value.reason == "lock_missing"
        assert env.connector.fetch_calls == []
        assert env.indexer.calls_of(REGISTER_DOCUMENTS) == []


def test_the_maintenance_flag_stops_the_batch_registration_that_follows_last_seen() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        env.indexer.behavior.before(REPORT_LAST_SEEN, lambda: env.jobs.seed_maintenance(True))

        with pytest.raises(MaintenanceDetected):
            env.run()

        # last-seen は送った(フラグは、その後の取得・バッチ登録の前に確認される)。
        assert env.indexer.operations() == ["start_crawl", REPORT_LAST_SEEN]


def test_rejected_registration_after_the_first_batch_keeps_the_registered_counts() -> None:
    with crawl_env(
        files={"a": b"1", "b": b"2"}, settings=CrawlSettings(batch_max_documents=1)
    ) as env:
        # 1 つ目のバッチの後、2 つ目のバッチの要請が拒否される。
        env.indexer.behavior.before(REGISTER_DOCUMENTS, lambda: None)
        env.indexer.behavior.before(
            REGISTER_DOCUMENTS,
            lambda: env.indexer.behavior.inject(REGISTER_DOCUMENTS, IndexerRejected(400, "x")),
        )

        env.run()

        assert env.job_body()["registration"]["created_count"] == 1
        assert env.job_body()["registration"]["partial"] is True
