"""`source_delete` のテストの共通部品。

メモリ上の Repository(`sources` 用と `jobs` 用は別インスタンス)・`FakeIndexerClient`・固定時計で
組み立てる。ハートビートは本物を `ManualWaiter` で動かす(スレッドは待ちに入ったまま)。待ちは記録
だけして実際には待たない(`env.sleeps`)。

`events` は、破壊的な操作と状態の書き込みを 1 本の時系列に並べた記録(順 0〜6 の順序、後続の削除が
1 回も呼ばれないことの検証に使う)。
- `indexer:discard`・`indexer:delete_documents`・`indexer:delete_deletion_records`
- `sources:replace:{id}`(順 0)・`sources:delete:{id}`(順 5)
- `jobs:scan:{record_type}`・`jobs:delete_ids:{件数}`(順 3)
- `jobs:replace:{id}`(ジョブ記録の更新)・`jobs:delete:{id}`(ロック文書などの削除)
"""

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from typing import Any

from loreley_crawler.common.retry import Retrier, RetryPolicy
from loreley_crawler.infrastructure.indexer_client import (
    DeleteDocumentsReply,
    DeleteRecordsReply,
    DiscardReply,
    LockInfo,
)
from loreley_crawler.infrastructure.opensearch import (
    BulkDeleteResult,
    DeleteOutcome,
    RecordFilter,
    RecordPages,
    ReplaceOutcome,
    SortKey,
)
from loreley_crawler.jobs import (
    DocumentRecords,
    JobAdmission,
    JobContext,
    JobExecutor,
    JobRecord,
    JobRunner,
    JobsSettings,
    JobType,
)
from loreley_crawler.jobs.locks import Heartbeat, LeaseSet
from loreley_crawler.source_delete import SourceDeleteDependencies, SourceDeleteExecutor
from loreley_crawler.sources import SourceStatus, SourceStore
from tests.fakes.clock import FixedClock
from tests.fakes.fake_indexer_client import (
    DELETE_DELETION_RECORDS,
    DELETE_DOCUMENTS,
    DISCARD_DELETIONS,
    FakeIndexerClient,
)
from tests.fakes.in_memory_repository import InMemoryRepository
from tests.jobs.locks.support import SETTINGS as HEARTBEAT_SETTINGS
from tests.jobs.locks.support import ManualWaiter
from tests.jobs.support import (
    JOB_ID,
    NO_WAIT_RETRIER,
    OWNER,
    SOURCE_ID,
    JobsEnv,
    fixed_token,
)

OTHER_SOURCE_ID = "docs-other"
# 順 1・2・4 の Indexer の操作(順に)。
INDEXER_STEPS = [DISCARD_DELETIONS, DELETE_DOCUMENTS, DELETE_DELETION_RECORDS]
EXPECTED_LOCK = LockInfo(owner=OWNER, job_id=JOB_ID)

SKIP_ID = f"skip-{SOURCE_ID}-aaa"
OVERSIZE_ID = f"oversize-{SOURCE_ID}-aaa"
OTHER_SKIP_ID = f"skip-{OTHER_SOURCE_ID}-aaa"
OTHER_OVERSIZE_ID = f"oversize-{OTHER_SOURCE_ID}-aaa"
OTHER_JOB_ID = "job-20261113T000000Z-0000000a"


class TimelineRepository(InMemoryRepository):
    """書き込み・走査を、共有の時系列(`events`)に記録する。"""

    def __init__(self, label: str, events: list[str]) -> None:
        super().__init__()
        self._label = label
        self._events = events

    def replace_if_unchanged(
        self, record_id: str, body: Mapping[str, Any], *, seq_no: int, primary_term: int
    ) -> ReplaceOutcome:
        self._events.append(f"{self._label}:replace:{record_id}")
        return super().replace_if_unchanged(
            record_id, body, seq_no=seq_no, primary_term=primary_term
        )

    def delete_if_unchanged(
        self, record_id: str, *, seq_no: int, primary_term: int
    ) -> DeleteOutcome:
        self._events.append(f"{self._label}:delete:{record_id}")
        return super().delete_if_unchanged(record_id, seq_no=seq_no, primary_term=primary_term)

    def scan(
        self, record_filter: RecordFilter, *, sort: Sequence[SortKey]
    ) -> AbstractContextManager[RecordPages]:
        self._events.append(f"{self._label}:scan:{record_filter.equals['record_type']}")
        return super().scan(record_filter, sort=sort)

    def delete_ids(self, record_ids: Sequence[str]) -> BulkDeleteResult:
        self._events.append(f"{self._label}:delete_ids:{len(record_ids)}")
        return super().delete_ids(record_ids)


class TimelineIndexerClient(FakeIndexerClient):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self._events = events

    def discard_deletions(self, source_id: str, *, lock: LockInfo) -> DiscardReply:
        self._events.append("indexer:discard")
        return super().discard_deletions(source_id, lock=lock)

    def delete_documents(self, source_id: str, *, lock: LockInfo) -> DeleteDocumentsReply:
        self._events.append("indexer:delete_documents")
        return super().delete_documents(source_id, lock=lock)

    def delete_deletion_records(self, source_id: str, *, lock: LockInfo) -> DeleteRecordsReply:
        self._events.append("indexer:delete_deletion_records")
        return super().delete_deletion_records(source_id, lock=lock)


def make_retrier(sleeps: list[float], on_sleep: Any = None) -> Retrier:
    """待たずに待ち秒数を記録する(試行 3 回。待ちは 1 秒・2 秒。ジッタなし)。"""

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if on_sleep is not None:
            on_sleep()

    return Retrier(RetryPolicy(3, 1.0, 2.0, 30.0, 0.0), sleep=sleep, wait_slice_seconds=1_000)


@dataclass
class SourceDeleteEnv:
    jobs: JobsEnv
    indexer: TimelineIndexerClient
    store: SourceStore
    executor: SourceDeleteExecutor
    context: JobContext
    heartbeat: Heartbeat
    record: JobRecord
    sleeps: list[float]
    events: list[str] = field(default_factory=list)

    def run(self) -> dict[str, Any]:
        """`SourceDeleteExecutor.__call__`(JobExecutor)で最終状態の記録まで実行し、ジョブ記録を返す。"""
        self.executor(self.record, self.context)
        return self.jobs.job_body()

    def source_body(self, source_id: str = SOURCE_ID) -> dict[str, Any] | None:
        return self.jobs.sources_repository.body_of(source_id)

    def indexer_calls(self) -> list[str]:
        """Indexer へ送った削除の呼び出し(順に)。"""
        return [call.operation for call in self.indexer.calls_of(*INDEXER_STEPS)]

    def destructive_events(self) -> list[str]:
        """削除に当たる操作(Indexer の 3 つ・記録の削除・設定の削除)。ジョブ記録の更新は除く。"""
        return [
            event
            for event in self.events
            if event.startswith(("indexer:", "jobs:scan:", "jobs:delete_ids:", "sources:delete:"))
        ]

    def seed_document_records(self) -> set[str]:
        """このソースと他のソースの記録を置く。順 3 の後に残るべき記録の ID の集合を返す。"""
        repository = self.jobs.jobs_repository
        for record_id, record_type, source_id in (
            (SKIP_ID, "skip", SOURCE_ID),
            (OVERSIZE_ID, "oversize", SOURCE_ID),
            (OTHER_SKIP_ID, "skip", OTHER_SOURCE_ID),
            (OTHER_OVERSIZE_ID, "oversize", OTHER_SOURCE_ID),
        ):
            repository.seed(
                record_id,
                {
                    "record_type": record_type,
                    "source_id": source_id,
                    "document_id": "aaa",
                    "external_id": "a.txt",
                },
            )
        self.jobs.seed_job(OTHER_JOB_ID, source_id=OTHER_SOURCE_ID)
        self.jobs.seed_lock(OTHER_JOB_ID, source_id=OTHER_SOURCE_ID)
        self.jobs.seed_maintenance(False)
        return set(repository.record_ids()) - {SKIP_ID, OVERSIZE_ID}


def new_timeline_env(events: list[str]) -> JobsEnv:
    return JobsEnv(
        FixedClock(),
        TimelineRepository("jobs", events),
        sources_repository=TimelineRepository("sources", events),
    )


@contextmanager
def source_delete_env(
    *,
    seed_source: bool = True,
    source_status: SourceStatus = SourceStatus.ACTIVE,
    job_fields: Mapping[str, Any] | None = None,
    on_sleep: Any = None,
) -> Iterator[SourceDeleteEnv]:
    """`queued` の `source_delete` ジョブ・ロック・設定を置き、リース設定とハートビートまで進める。

    ブロックを抜けるときにハートビートを止める。
    """
    events: list[str] = []
    jobs = new_timeline_env(events)
    indexer = TimelineIndexerClient(events)
    if seed_source:
        jobs.seed_source(status=source_status)
    sleeps: list[float] = []
    retrier = make_retrier(sleeps, on_sleep)
    store = SourceStore(jobs.sources_repository, jobs.clock, NO_WAIT_RETRIER)
    record = jobs.seed_job(JOB_ID, job_type=JobType.SOURCE_DELETE, **(job_fields or {}))
    jobs.seed_lock(JOB_ID)
    lock = jobs.lock_store.read(SOURCE_ID)
    assert lock is not None
    leased = jobs.lock_store.set_lease(
        lock, lease_seconds=HEARTBEAT_SETTINGS.lease_seconds, require_active_lease=False
    )
    assert isinstance(leased, LeaseSet)
    heartbeat = Heartbeat(jobs.lock_store, jobs.clock, HEARTBEAT_SETTINGS, waiter=ManualWaiter())
    heartbeat.start(leased.lock, leased.lease_expires_at)
    context = JobContext(
        record=record,
        job_store=jobs.job_store,
        heartbeat=heartbeat,
        cancel_requests=jobs.cancel_requests,
        read_maintenance_flag=jobs.read_maintenance_flag,
        clock=jobs.clock,
        retrier=retrier,
    )
    env = SourceDeleteEnv(
        jobs=jobs,
        indexer=indexer,
        store=store,
        executor=make_executor(jobs, indexer, store),
        context=context,
        heartbeat=heartbeat,
        record=record,
        sleeps=sleeps,
        events=events,
    )
    # 実行開始までは、イベントに残さない(置いた記録の準備の書き込み)。
    events.clear()
    try:
        yield env
    finally:
        heartbeat.stop()


def make_executor(
    jobs: JobsEnv, indexer: FakeIndexerClient, store: SourceStore
) -> SourceDeleteExecutor:
    return SourceDeleteExecutor(
        SourceDeleteDependencies(
            source_store=store,
            indexer_client=indexer,
            document_records=DocumentRecords(jobs.jobs_repository, jobs.clock),
        )
    )


def make_admission(jobs: JobsEnv, random_token: Callable[[], str] = fixed_token) -> JobAdmission:
    return JobAdmission(
        settings=jobs.settings,
        source_reader=jobs.source_reader,
        job_store=jobs.job_store,
        lock_store=jobs.lock_store,
        read_maintenance_flag=jobs.read_maintenance_flag,
        clock=jobs.clock,
        retrier=NO_WAIT_RETRIER,
        wakeup=jobs.wakeup,
        random_token=random_token,
    )


def make_runner(
    jobs: JobsEnv, indexer: FakeIndexerClient, heartbeats: list[Heartbeat] | None = None
) -> JobRunner:
    """`SourceDeleteExecutor` を実行対象にした Job Runner(本物のハートビート)。"""
    store = SourceStore(jobs.sources_repository, jobs.clock, NO_WAIT_RETRIER)

    def unused(record: JobRecord, context: JobContext) -> None:
        raise AssertionError("crawl is not used")

    def new_heartbeat() -> Heartbeat:
        heartbeat = Heartbeat(
            jobs.lock_store, jobs.clock, HEARTBEAT_SETTINGS, waiter=ManualWaiter()
        )
        if heartbeats is not None:
            heartbeats.append(heartbeat)
        return heartbeat

    executors: dict[JobType, JobExecutor] = {
        JobType.CRAWL: unused,
        JobType.SOURCE_DELETE: make_executor(jobs, indexer, store),
    }
    return JobRunner(
        settings=JobsSettings(owner=OWNER, heartbeat=HEARTBEAT_SETTINGS),
        job_store=jobs.job_store,
        lock_store=jobs.lock_store,
        heartbeat_factory=new_heartbeat,
        executors=executors,
        cancel_requests=jobs.cancel_requests,
        wakeup=jobs.wakeup,
        read_maintenance_flag=jobs.read_maintenance_flag,
        clock=jobs.clock,
        retrier=NO_WAIT_RETRIER,
    )
