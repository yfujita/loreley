"""`crawl` のテストの共通部品。

メモリ上の Repository(`sources` 用と `jobs` 用は別インスタンス)・`FakeIndexerClient`・
`FakeConnector`・固定時計で組み立てる。ハートビートは本物を `ManualWaiter` で動かす(スレッドは
待ちに入ったまま)。待ちは記録だけして実際には待たない(`env.sleeps`)。

`events` は、Connector・Indexer の呼び出しを 1 本の時系列に並べた記録(取得と登録の交互の進行を
確かめる)。
"""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Any

from loreley_crawler.common.retry import Retrier, RetryPolicy
from loreley_crawler.connectors.interface import DocumentRef, FetchedDocument
from loreley_crawler.connectors.registry import FILE_SYSTEM, ConnectorRegistry
from loreley_crawler.crawl import (
    CrawlDependencies,
    CrawlExecutor,
    CrawlSettings,
)
from loreley_crawler.crawl.executor import StageResult
from loreley_crawler.documents import DocumentsSettings, compute_document_id
from loreley_crawler.infrastructure.indexer_client import (
    BatchReply,
    CrawlStatus,
    DocumentFailed,
    DocumentRegistered,
    DocumentToRegister,
    FailureType,
    FinishReply,
    LastSeenReply,
    LockInfo,
    StartReply,
    StatusReply,
)
from loreley_crawler.jobs import (
    DocumentRecords,
    JobContext,
    JobHistory,
    JobRecord,
    JobRunner,
    JobsSettings,
    JobType,
)
from loreley_crawler.jobs.locks import Heartbeat, LeaseSet
from tests.fakes.clock import FixedClock
from tests.fakes.fake_connector import FakeConnector, FakeConnectorType, StreamItem
from tests.fakes.fake_indexer_client import FINISH_CRAWL, FakeIndexerClient
from tests.jobs.locks.support import SETTINGS as HEARTBEAT_SETTINGS
from tests.jobs.locks.support import ManualWaiter
from tests.jobs.support import JOB_ID, NO_WAIT_RETRIER, OWNER, SOURCE_ID, JobsEnv, make_env

SKIP_RECORD_PREFIX = f"skip-{SOURCE_ID}-"
OVERSIZE_RECORD_PREFIX = f"oversize-{SOURCE_ID}-"


class RecordingConnector(FakeConnector):
    """取得を `events` に記録する(`fetch:{名前}`)。"""

    events: list[str] | None = None

    def fetch(self, ref: DocumentRef, max_bytes: int) -> FetchedDocument:
        if self.events is not None:
            self.events.append(f"fetch:{ref.locator}")
        return super().fetch(ref, max_bytes)


class RecordingIndexerClient(FakeIndexerClient):
    """呼び出しを `events` に記録する。

    `start`・`last_seen:{件数}`・`register:{名前の列}`・`finish:{outcome}`・`status`。
    実 Indexer と同じく、終了通知を受けた crawl の Status には `finish_received_at` が付く。
    """

    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []
        # 最初の 1 回だけ `document_rejected` にする文書(再送で登録される)。
        self.rejected_once: set[str] = set()
        # `extract_failed: true` で登録される文書。
        self.extract_failed: set[str] = set()

    def start_crawl(self, **arguments: Any) -> StartReply:
        self.events.append("start")
        return super().start_crawl(**arguments)

    def report_last_seen(self, source_id: str, **arguments: Any) -> LastSeenReply:
        self.events.append(f"last_seen:{len(arguments['document_ids'])}")
        return super().report_last_seen(source_id, **arguments)

    def register_documents(
        self, source_id: str, *, documents: Sequence[DocumentToRegister], **arguments: Any
    ) -> BatchReply:
        self.events.append("register:" + ",".join(document.external_id for document in documents))
        return super().register_documents(source_id, documents=documents, **arguments)

    def finish_crawl(self, crawl_id: str, **arguments: Any) -> FinishReply:
        self.events.append(f"finish:{arguments['outcome'].value}")
        return super().finish_crawl(crawl_id, **arguments)

    def get_crawl_status(self, crawl_id: str) -> StatusReply:
        self.events.append("status")
        return super().get_crawl_status(crawl_id)

    def _document_result(
        self, source_id: str, document: DocumentToRegister
    ) -> DocumentRegistered | DocumentFailed:
        external_id = document.external_id
        if external_id in self.rejected_once:
            self.rejected_once.discard(external_id)
            document_id = document_id_of(external_id)
            return DocumentFailed(external_id, document_id, FailureType.DOCUMENT_REJECTED)
        result = super()._document_result(source_id, document)
        if external_id in self.extract_failed and isinstance(result, DocumentRegistered):
            return replace(result, extract_failed=True)
        return result

    def _status_of(self, crawl_id: str) -> StatusReply:
        # 差し替えていない既定の応答だけに付ける(差し替えた応答は、そのまま返す)。
        reply = super()._status_of(crawl_id)
        # 実 Indexer は、`failed`・`cancelled` の終了通知では `finish_received_at` を記録しない。
        if isinstance(reply, CrawlStatus) and reply.status == "deleted":
            return replace(reply, finish_received_at="2026-11-13T00:00:00.000Z")
        return reply


def document_id_of(name: str) -> str:
    return compute_document_id(SOURCE_ID, name)


@dataclass
class CrawlEnv:
    jobs: JobsEnv
    indexer: RecordingIndexerClient
    connector: RecordingConnector
    connector_type: FakeConnectorType
    executor: CrawlExecutor
    context: JobContext
    heartbeat: Heartbeat
    record: JobRecord
    sleeps: list[float]
    events: list[str] = field(default_factory=list)

    def run(self) -> StageResult:
        return self.executor.run_until_finish_notice(self.record, self.context)

    def job_body(self) -> dict[str, Any]:
        return self.jobs.job_body(JOB_ID)

    def skip_record_ids(self) -> list[str]:
        return [i for i in self.jobs.jobs_repository.record_ids() if i.startswith("skip-")]

    def oversize_record_ids(self) -> list[str]:
        return [i for i in self.jobs.jobs_repository.record_ids() if i.startswith("oversize-")]

    def seed_document_record(self, record_type: str, name: str, **fields: Any) -> str:
        """前回までのスキップ記録・原本サイズ超過記録を置く(整理のテスト用)。"""
        record_id = f"{record_type}-{SOURCE_ID}-{document_id_of(name)}"
        body = {
            "record_type": record_type,
            "source_id": SOURCE_ID,
            "document_id": document_id_of(name),
            "external_id": name,
            "last_job_id": "job-previous",
            **fields,
        }
        self.jobs.jobs_repository.seed(record_id, body)
        return record_id


def make_retrier(sleeps: list[float], clock: FixedClock | None = None) -> Retrier:
    """待たずに待ち秒数を記録する(試行 3 回。待ちは 1 秒・2 秒。ジッタなし)。

    `clock` を渡すと、待った秒数だけ固定時計を進める(ポーリングの上限時間のテスト用)。
    """

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if clock is not None:
            clock.advance(seconds=seconds)

    return Retrier(RetryPolicy(3, 1.0, 2.0, 30.0, 0.0), sleep=sleep, wait_slice_seconds=1_000)


@contextmanager
def crawl_env(
    *,
    files: Mapping[str, bytes] | None = None,
    items: Sequence[StreamItem] | None = None,
    documents: Mapping[object, FetchedDocument] | None = None,
    settings: CrawlSettings | None = None,
    documents_settings: DocumentsSettings | None = None,
    seed_source: bool = True,
    job_fields: Mapping[str, Any] | None = None,
    advance_clock_on_sleep: bool = False,
) -> Iterator[CrawlEnv]:
    """`queued` のジョブ・ロック・設定を置き、リース設定とハートビートまで済ませる。

    ブロックを抜けるときにハートビートを止める。
    """
    jobs = make_env()
    events: list[str] = []
    if items is not None:
        connector = RecordingConnector(items, documents)
    else:
        connector = RecordingConnector.of(files or {})
    connector.events = events
    indexer = RecordingIndexerClient()
    indexer.events = events
    connector_type = FakeConnectorType(connector)
    if seed_source:
        jobs.seed_source()
    record = jobs.seed_job(JOB_ID, **(job_fields or {}))
    jobs.seed_lock(JOB_ID)
    lock = jobs.lock_store.read(SOURCE_ID)
    assert lock is not None
    leased = jobs.lock_store.set_lease(
        lock, lease_seconds=HEARTBEAT_SETTINGS.lease_seconds, require_active_lease=False
    )
    assert isinstance(leased, LeaseSet)
    heartbeat = Heartbeat(jobs.lock_store, jobs.clock, HEARTBEAT_SETTINGS, waiter=ManualWaiter())
    heartbeat.start(leased.lock, leased.lease_expires_at)
    sleeps: list[float] = []
    context = JobContext(
        record=record,
        job_store=jobs.job_store,
        heartbeat=heartbeat,
        cancel_requests=jobs.cancel_requests,
        read_maintenance_flag=jobs.read_maintenance_flag,
        clock=jobs.clock,
        retrier=make_retrier(sleeps, jobs.clock if advance_clock_on_sleep else None),
    )
    dependencies = CrawlDependencies(
        source_reader=jobs.source_reader,
        connector_registry=ConnectorRegistry({FILE_SYSTEM: connector_type}),
        indexer_client=indexer,
        document_records=DocumentRecords(jobs.jobs_repository, jobs.clock),
        job_history=JobHistory(jobs.jobs_repository),
        clock=jobs.clock,
        settings=settings or CrawlSettings(),
        documents_settings=documents_settings or DocumentsSettings(),
    )
    env = CrawlEnv(
        jobs=jobs,
        indexer=indexer,
        connector=connector,
        connector_type=connector_type,
        executor=CrawlExecutor(dependencies),
        context=context,
        heartbeat=heartbeat,
        record=record,
        sleeps=sleeps,
        events=events,
    )
    try:
        yield env
    finally:
        heartbeat.stop()


EXPECTED_LOCK = LockInfo(owner=OWNER, job_id=JOB_ID)


def run_full(env: CrawlEnv) -> dict[str, Any]:
    """`CrawlExecutor.__call__`(JobExecutor)で、最終状態の記録まで実行し、ジョブ記録を返す。"""
    env.executor(env.record, env.context)
    return env.job_body()


def finish_calls(env: CrawlEnv) -> list[dict[str, Any]]:
    """終了通知の呼び出しの引数(送った順)。"""
    return [call.arguments for call in env.indexer.calls_of(FINISH_CRAWL)]


def outcomes(env: CrawlEnv) -> list[str]:
    """送った終了通知の `outcome`(送った順)。"""
    return [arguments["outcome"].value for arguments in finish_calls(env)]


def make_runner(
    jobs: JobsEnv, indexer: RecordingIndexerClient, files: dict[str, bytes]
) -> JobRunner:
    """`CrawlExecutor` を `crawl` の実行対象にした Job Runner(本物のハートビート・ロック)。"""
    executor = CrawlExecutor(
        CrawlDependencies(
            source_reader=jobs.source_reader,
            connector_registry=ConnectorRegistry(
                {FILE_SYSTEM: FakeConnectorType(RecordingConnector.of(files))}
            ),
            indexer_client=indexer,
            document_records=DocumentRecords(jobs.jobs_repository, jobs.clock),
            job_history=JobHistory(jobs.jobs_repository),
            clock=jobs.clock,
            settings=CrawlSettings(),
            documents_settings=DocumentsSettings(),
        )
    )

    def unused(record: JobRecord, context: JobContext) -> None:
        raise AssertionError("source_delete is not used")

    return JobRunner(
        settings=JobsSettings(owner=OWNER, heartbeat=HEARTBEAT_SETTINGS),
        job_store=jobs.job_store,
        lock_store=jobs.lock_store,
        heartbeat_factory=lambda: Heartbeat(
            jobs.lock_store, jobs.clock, HEARTBEAT_SETTINGS, waiter=ManualWaiter()
        ),
        executors={JobType.CRAWL: executor, JobType.SOURCE_DELETE: unused},
        cancel_requests=jobs.cancel_requests,
        wakeup=jobs.wakeup,
        read_maintenance_flag=jobs.read_maintenance_flag,
        clock=jobs.clock,
        retrier=NO_WAIT_RETRIER,
    )
