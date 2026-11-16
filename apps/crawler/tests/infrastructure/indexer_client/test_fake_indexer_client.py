"""`FakeIndexerClient` の自己テスト(後続のフェーズが、この偽物の振る舞いを前提にするため)。"""

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from loreley_crawler.infrastructure.indexer_client import (
    BatchResults,
    Change,
    CrawlStatus,
    DeletionRecordsDeleted,
    DiscardResult,
    DocumentFailed,
    DocumentRegistered,
    DocumentsDeleted,
    FailureType,
    FinishOutcome,
    IndexerClient,
    IndexerRejected,
    IndexerUnavailable,
    LastSeenEntry,
    LastSeenResult,
    LastSeenResults,
    Succeeded,
)
from tests.fakes import fake_indexer_client as ops
from tests.fakes.fake_indexer_client import FakeIndexerClient
from tests.infrastructure.indexer_client.support import (
    CRAWL_ID,
    CRAWL_STARTED_AT,
    LOCK,
    SOURCE_ID,
    make_document,
)

NOW = datetime(2026, 11, 13, tzinfo=UTC)


def start(client: IndexerClient) -> object:
    return client.start_crawl(
        crawl_id=CRAWL_ID,
        source_id=SOURCE_ID,
        crawl_started_at=CRAWL_STARTED_AT,
        ttl=1,
        ratio_threshold=0.5,
        min_delete_count=1,
        force_delete=False,
        rewrite_mode=False,
    )


def register(client: IndexerClient, *external_ids: str) -> object:
    return client.register_documents(
        SOURCE_ID,
        crawl_id=CRAWL_ID,
        crawl_started_at=CRAWL_STARTED_AT,
        lock=LOCK,
        documents=[make_document(external_id=external_id) for external_id in external_ids],
    )


def test_calls_are_recorded_in_order_with_their_arguments() -> None:
    fake = FakeIndexerClient()

    start(fake)
    fake.report_last_seen(
        SOURCE_ID,
        crawl_id=CRAWL_ID,
        crawl_started_at=CRAWL_STARTED_AT,
        lock=LOCK,
        document_ids=["a"],
    )
    register(fake, "x")
    fake.finish_crawl(CRAWL_ID, source_id=SOURCE_ID, outcome=FinishOutcome.FAILED, finished_at=NOW)
    fake.get_crawl_status(CRAWL_ID)

    assert fake.operations() == [
        ops.START_CRAWL,
        ops.REPORT_LAST_SEEN,
        ops.REGISTER_DOCUMENTS,
        ops.FINISH_CRAWL,
        ops.GET_CRAWL_STATUS,
    ]
    [last_seen] = fake.calls_of(ops.REPORT_LAST_SEEN)
    assert last_seen.arguments["lock"] == LOCK
    assert last_seen.arguments["document_ids"] == ["a"]
    assert fake.calls_of(ops.START_CRAWL)[0].arguments["crawl_started_at"] == CRAWL_STARTED_AT


def test_the_default_responses_are_successes() -> None:
    fake = FakeIndexerClient()

    assert start(fake) == Succeeded()
    last_seen = fake.report_last_seen(
        SOURCE_ID,
        crawl_id=CRAWL_ID,
        crawl_started_at=CRAWL_STARTED_AT,
        lock=LOCK,
        document_ids=["a", "b"],
    )
    assert last_seen == LastSeenResults(
        entries=(
            LastSeenEntry("a", LastSeenResult.UPDATED),
            LastSeenEntry("b", LastSeenResult.UPDATED),
        )
    )
    finished = fake.finish_crawl(
        CRAWL_ID, source_id=SOURCE_ID, outcome=FinishOutcome.FAILED, finished_at=NOW
    )
    assert finished == Succeeded()
    assert fake.discard_deletions(SOURCE_ID, lock=LOCK) == DiscardResult(())
    assert fake.delete_documents(SOURCE_ID, lock=LOCK) == DocumentsDeleted(0)
    assert fake.delete_deletion_records(SOURCE_ID, lock=LOCK) == DeletionRecordsDeleted(True)


def test_the_default_batch_response_registers_every_document_with_its_document_id() -> None:
    fake = FakeIndexerClient()
    start(fake)

    result = register(fake, "a.md", "b.md")

    assert isinstance(result, BatchResults)
    assert [(d.external_id, d.change) for d in result.documents] == [
        ("a.md", Change.CREATED),
        ("b.md", Change.CREATED),
    ]
    # `SHA-256(source_id + "\0" + external_id)`(indexer-api 3.3)。
    expected_id = hashlib.sha256(f"{SOURCE_ID}\0a.md".encode()).hexdigest()
    assert result.documents[0].document_id == expected_id


def test_registration_failures_fail_only_the_listed_documents() -> None:
    fake = FakeIndexerClient()
    fake.registration_failures["bad.md"] = FailureType.DOCUMENT_REJECTED
    start(fake)

    result = register(fake, "ok.md", "bad.md")

    assert isinstance(result, BatchResults)
    ok, bad = result.documents
    assert isinstance(ok, DocumentRegistered)
    assert isinstance(bad, DocumentFailed)
    assert bad.failure_type == FailureType.DOCUMENT_REJECTED


@pytest.mark.parametrize(
    "outcome", [IndexerUnavailable("http_503"), IndexerRejected(409, "lock_not_owned")]
)
def test_a_response_can_be_replaced_for_the_next_calls_only(
    outcome: IndexerUnavailable | IndexerRejected,
) -> None:
    fake = FakeIndexerClient()
    start(fake)
    fake.behavior.inject(ops.REGISTER_DOCUMENTS, outcome, times=2)

    results = [register(fake, "a.md") for _ in range(3)]

    assert results[:2] == [outcome, outcome]
    assert isinstance(results[2], BatchResults)
    assert fake.operations() == [ops.START_CRAWL, *[ops.REGISTER_DOCUMENTS] * 3]  # 差し替えも記録


def test_a_hook_runs_before_the_call_to_interleave_other_events() -> None:
    fake = FakeIndexerClient()
    events: list[str] = []
    fake.behavior.before(ops.FINISH_CRAWL, lambda: events.append("cancelled-just-before"))

    fake.finish_crawl(CRAWL_ID, source_id=SOURCE_ID, outcome=FinishOutcome.FAILED, finished_at=NOW)

    assert events == ["cancelled-just-before"]


def test_the_fake_implements_every_operation_of_the_interface() -> None:
    abstract_methods = IndexerClient.__abstractmethods__

    assert abstract_methods == {
        ops.START_CRAWL,
        ops.REPORT_LAST_SEEN,
        ops.REGISTER_DOCUMENTS,
        ops.FINISH_CRAWL,
        ops.GET_CRAWL_STATUS,
        ops.DISCARD_DELETIONS,
        ops.DELETE_DOCUMENTS,
        ops.DELETE_DELETION_RECORDS,
    }
    assert not FakeIndexerClient.__abstractmethods__


# --- 入力の検証(実クライアントと同じ) ---


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"ttl": True}, TypeError),
        ({"ttl": 1.5}, TypeError),
        ({"min_delete_count": "1"}, TypeError),
        ({"ratio_threshold": float("nan")}, ValueError),
        ({"force_delete": 1}, TypeError),
        ({"rewrite_mode": "true"}, TypeError),
    ],
)
def test_start_validates_its_input_like_the_real_client_and_records_nothing(
    overrides: dict[str, object], error: type[Exception]
) -> None:
    fake = FakeIndexerClient()
    arguments: dict[str, object] = {
        "crawl_id": CRAWL_ID,
        "source_id": SOURCE_ID,
        "crawl_started_at": CRAWL_STARTED_AT,
        "ttl": 1,
        "ratio_threshold": 0.5,
        "min_delete_count": 1,
        "force_delete": False,
        "rewrite_mode": False,
        **overrides,
    }

    with pytest.raises(error):
        fake.start_crawl(**arguments)

    assert fake.calls == []


def test_an_empty_batch_and_an_incomplete_finish_are_rejected_before_they_are_recorded() -> None:
    fake = FakeIndexerClient()

    with pytest.raises(ValueError, match="documents"):
        register(fake)
    with pytest.raises(ValueError, match="requires"):
        fake.finish_crawl(
            CRAWL_ID,
            source_id=SOURCE_ID,
            outcome=FinishOutcome.ENUMERATION_COMPLETED,
            finished_at=NOW,
        )
    with pytest.raises(TypeError, match="enumerated_count"):
        fake.finish_crawl(
            CRAWL_ID,
            source_id=SOURCE_ID,
            outcome=FinishOutcome.ENUMERATION_COMPLETED,
            finished_at=NOW,
            enumerated_count=True,
            skipped_document_ids=[],
            oversize_document_ids=[],
        )

    assert fake.calls == []


def test_a_naive_timestamp_is_rejected_like_the_real_client() -> None:
    fake = FakeIndexerClient()

    with pytest.raises(ValueError, match="timezone"):
        fake.report_last_seen(
            SOURCE_ID,
            crawl_id=CRAWL_ID,
            crawl_started_at=datetime(2026, 11, 13),
            lock=LOCK,
            document_ids=[],
        )


# --- 開始通知・終了通知・Status の状態 ---


def finish(
    fake: FakeIndexerClient,
    outcome: FinishOutcome = FinishOutcome.ENUMERATION_COMPLETED,
    *,
    skipped: tuple[str, ...] = (),
    source_id: str = SOURCE_ID,
    finished_at: datetime = NOW,
) -> object:
    counts = outcome == FinishOutcome.ENUMERATION_COMPLETED
    return fake.finish_crawl(
        CRAWL_ID,
        source_id=source_id,
        outcome=outcome,
        finished_at=finished_at,
        enumerated_count=len(skipped) if counts else None,
        skipped_document_ids=list(skipped) if counts else None,
        oversize_document_ids=[] if counts else None,
    )


def test_status_of_an_unknown_crawl_is_a_404_crawl_not_found() -> None:
    assert FakeIndexerClient().get_crawl_status("job-unknown") == IndexerRejected(
        404, "crawl_not_found"
    )


def test_status_is_running_after_start_and_deleted_after_an_enumeration_completed_finish() -> None:
    fake = FakeIndexerClient()
    start(fake)
    assert fake.get_crawl_status(CRAWL_ID) == CrawlStatus(CRAWL_ID, SOURCE_ID, "running")

    assert finish(fake) == Succeeded()

    assert fake.get_crawl_status(CRAWL_ID) == CrawlStatus(CRAWL_ID, SOURCE_ID, "deleted")


@pytest.mark.parametrize("outcome", [FinishOutcome.FAILED, FinishOutcome.CANCELLED])
def test_status_is_failed_with_an_outcome_reason_after_a_failed_or_cancelled_finish(
    outcome: FinishOutcome,
) -> None:
    fake = FakeIndexerClient()
    start(fake)

    finish(fake, outcome)

    assert fake.get_crawl_status(CRAWL_ID) == CrawlStatus(
        CRAWL_ID, SOURCE_ID, "failed", reason=f"outcome_{outcome.value}"
    )


def test_a_resent_start_succeeds_and_one_with_different_values_is_a_409() -> None:
    fake = FakeIndexerClient()
    start(fake)

    assert start(fake) == Succeeded()
    changed = fake.start_crawl(
        crawl_id=CRAWL_ID,
        source_id=SOURCE_ID,
        crawl_started_at=CRAWL_STARTED_AT,
        ttl=2,
        ratio_threshold=0.5,
        min_delete_count=1,
        force_delete=False,
        rewrite_mode=False,
    )
    assert changed == IndexerRejected(409, "crawl_start_conflict")


def test_a_start_after_the_crawl_finished_is_a_409_crawl_already_finished() -> None:
    fake = FakeIndexerClient()
    start(fake)
    finish(fake)

    assert start(fake) == IndexerRejected(409, "crawl_already_finished")


def test_a_resent_finish_with_the_same_content_succeeds_whatever_finished_at_is() -> None:
    fake = FakeIndexerClient()
    start(fake)
    finish(fake, skipped=("a" * 64,))

    resent = finish(fake, skipped=("a" * 64,), finished_at=NOW.replace(year=2027))

    assert resent == Succeeded()


def test_a_resent_finish_with_different_content_is_a_409_finish_content_mismatch() -> None:
    fake = FakeIndexerClient()
    start(fake)
    finish(fake, skipped=("a" * 64,))

    assert finish(fake, skipped=("b" * 64,)) == IndexerRejected(409, "finish_content_mismatch")
    assert finish(fake, FinishOutcome.FAILED) == IndexerRejected(409, "finish_content_mismatch")
    # 最初の内容が保たれる。
    assert fake.get_crawl_status(CRAWL_ID) == CrawlStatus(CRAWL_ID, SOURCE_ID, "deleted")


def test_a_finish_for_another_source_is_a_409_finish_source_mismatch() -> None:
    fake = FakeIndexerClient()
    start(fake)

    assert finish(fake, source_id="other-source") == IndexerRejected(409, "finish_source_mismatch")
    assert fake.get_crawl_status(CRAWL_ID) == CrawlStatus(CRAWL_ID, SOURCE_ID, "running")


def test_a_finish_for_an_unknown_crawl_is_accepted_and_changes_nothing() -> None:
    fake = FakeIndexerClient()

    assert finish(fake) == Succeeded()  # 実 Indexer は 202 で破棄する

    assert fake.get_crawl_status(CRAWL_ID) == IndexerRejected(404, "crawl_not_found")


def test_an_injected_response_does_not_change_the_state() -> None:
    fake = FakeIndexerClient()
    fake.behavior.inject(ops.START_CRAWL, IndexerUnavailable("http_503"))

    assert start(fake) == IndexerUnavailable("http_503")
    assert fake.get_crawl_status(CRAWL_ID) == IndexerRejected(404, "crawl_not_found")


# --- last-seen・バッチ登録の受理条件(実 Indexer の `AdmissionChecker`。arch 9.5) ---


def last_seen(
    client: IndexerClient,
    *,
    source_id: str = SOURCE_ID,
    crawl_started_at: datetime = CRAWL_STARTED_AT,
) -> object:
    return client.report_last_seen(
        source_id,
        crawl_id=CRAWL_ID,
        crawl_started_at=crawl_started_at,
        lock=LOCK,
        document_ids=["a" * 64],
    )


@pytest.mark.parametrize("operation", ["last_seen", "register"])
def test_a_crawl_that_was_not_started_is_a_409_crawl_not_started(operation: str) -> None:
    fake = FakeIndexerClient()

    reply = last_seen(fake) if operation == "last_seen" else register(fake, "a.md")

    assert reply == IndexerRejected(409, "crawl_not_started")


def test_another_source_is_a_409_crawl_source_mismatch() -> None:
    fake = FakeIndexerClient()
    start(fake)

    assert last_seen(fake, source_id="other") == IndexerRejected(409, "crawl_source_mismatch")


@pytest.mark.parametrize("operation", ["last_seen", "register"])
def test_a_different_crawl_started_at_is_a_409_crawl_started_at_mismatch(operation: str) -> None:
    fake = FakeIndexerClient()
    start(fake)
    other = CRAWL_STARTED_AT.replace(year=2030)

    if operation == "last_seen":
        reply = last_seen(fake, crawl_started_at=other)
    else:
        reply = fake.register_documents(
            SOURCE_ID,
            crawl_id=CRAWL_ID,
            crawl_started_at=other,
            lock=LOCK,
            documents=[make_document(external_id="a.md")],
        )

    assert reply == IndexerRejected(409, "crawl_started_at_mismatch")


@pytest.mark.parametrize("operation", ["last_seen", "register"])
def test_writes_after_an_enumeration_completed_finish_are_a_409_crawl_finished(
    operation: str,
) -> None:
    fake = FakeIndexerClient()
    start(fake)
    fake.finish_crawl(
        CRAWL_ID,
        source_id=SOURCE_ID,
        outcome=FinishOutcome.ENUMERATION_COMPLETED,
        finished_at=NOW,
        enumerated_count=0,
        skipped_document_ids=[],
        oversize_document_ids=[],
    )

    reply = last_seen(fake) if operation == "last_seen" else register(fake, "a.md")

    assert reply == IndexerRejected(409, "crawl_finished")


@pytest.mark.parametrize("outcome", [FinishOutcome.FAILED, FinishOutcome.CANCELLED])
def test_writes_after_a_failed_or_cancelled_finish_are_a_409_crawl_already_closed(
    outcome: FinishOutcome,
) -> None:
    fake = FakeIndexerClient()
    start(fake)
    fake.finish_crawl(CRAWL_ID, source_id=SOURCE_ID, outcome=outcome, finished_at=NOW)

    assert last_seen(fake) == IndexerRejected(409, "crawl_already_closed")


def test_the_admission_checks_run_in_the_order_of_the_real_indexer() -> None:
    fake = FakeIndexerClient()
    start(fake)
    finish(fake, outcome=FinishOutcome.FAILED)  # 終了済み
    other = CRAWL_STARTED_AT.replace(year=2030)

    # ソースの不一致が先、次に `crawl_started_at`、最後に終了済み。
    assert last_seen(fake, source_id="other", crawl_started_at=other) == IndexerRejected(
        409, "crawl_source_mismatch"
    )
    assert last_seen(fake, crawl_started_at=other) == IndexerRejected(
        409, "crawl_started_at_mismatch"
    )
    assert last_seen(fake) == IndexerRejected(409, "crawl_already_closed")


def test_a_crawl_started_at_that_differs_below_a_millisecond_is_not_rejected() -> None:
    # 実 Indexer は、ミリ秒精度の UTC に正規化して比べる(表記の違いでは拒否しない)。
    fake = FakeIndexerClient()
    start(fake)

    reply = last_seen(fake, crawl_started_at=CRAWL_STARTED_AT + timedelta(microseconds=300))

    assert isinstance(reply, LastSeenResults)
