"""エントリポイント(composition root): 組み立て・起動順・停止順(module 3章・5.7)。

起動: `python -m loreley_crawler.main`(uvicorn は単一プロセス・ワーカー数 1。ソース単位の
ロック・Job Runner・取り消し要求・起床通知はプロセス内の状態で、複数プロセスは対象外)。

起動順(architecture 10章。CA-P-40)。どこで失敗しても、HTTP の受け付けは始めずに異常終了する
(例外を捕捉しない。プロセスは非 0 で終わる)。
1. `load_config()`: 設定の読み込みと整合性検査(CA-P-55)。違反・不備は `ConfigError`(値を含まない)
2. ログの設定(秘密値のマスキングを含む)と、未設定の Indexer 上限の警告
3. OpenSearch のクライアントと Repository(`create_backends`)。Repository は**ちょうど 3 つ**:
   `loreley-sources` 用・`loreley-jobs` 用(Store 層のクライアントを共有)と、ハートビート専用の
   `loreley-jobs` 用(専用クライアント。R7。CM-P-14)。`loreley-deletions`・検索インデックスは指さない
4. 各モジュールの組み立て(`assemble`。I/O もスレッドもない)
5. 起動時の回復(`StartupRecovery.run()`)
6. Job Runner、Scheduler のスレッドの開始(この順。回復の後)
7. アプリケーションの作成(`create_app`)と uvicorn の開始。**アプリは回復の後に作る**: uvicorn は
   アプリを受け取るまで接続を受け付けないので、回復の完了前は `/healthz` を含めどの API にも
   つながらない(`api` に受付の可否の状態を持たせない。crawler-api 3.1・4.7)

停止順(起動の逆順。CM-U-4): SIGTERM・SIGINT で uvicorn が止まる(HTTP の受け付けの停止)→
`Scheduler.request_stop()` → `JobRunner.request_stop()` → それぞれに `join`(タイムアウトつき)。
**実行中のジョブの完了は待たず、最終状態の記録・ロックの解放といった終了処理もしない**: ジョブは
`running` のまま、ロック文書も残り、次回の起動時の回復が `failed`(`crawler_restart`)にする
(architecture 5.8)。Job Runner が実行中のジョブの中で止まっていれば `join` はタイムアウトで戻り、
スレッドはデーモンなのでプロセスの終了とともに消える(ハートビートもデーモンで、ロック文書は削除しない)。
OpenSearch・Indexer の接続は閉じない: 閉じると、実行中のジョブが途中で失敗の記録を試み、終了処理を
しない方針とずれる。プロセスの終了が閉じる。

シグナルは uvicorn が扱う。uvicorn は graceful shutdown の後に元のハンドラを戻してシグナルを
再送出するので、そのままでは SIGTERM で `uvicorn.run` から戻る前にプロセスが終わる。
`_return_normally_after_a_stop_signal` が、再送出を受けても戻れるようにし(PID 1 かどうかに
依らない)、`main` は戻った後(`finally`)に停止処理を行う。スレッドの開始以降の起動の失敗でも、
`start_components` が開始したスレッドを止める。
"""

import logging
import signal
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from types import FrameType
from typing import Any

import uvicorn
from fastapi import FastAPI

from loreley_crawler.api import ApiDependencies, create_app
from loreley_crawler.common.clock import Clock, SystemClock
from loreley_crawler.common.log_setup import configure_logging
from loreley_crawler.common.retry import Retrier
from loreley_crawler.config import (
    CrawlerConfig,
    load_config,
    warn_about_unchecked_indexer_limits,
)
from loreley_crawler.connectors.registry import ConnectorRegistry, create_connector_registry
from loreley_crawler.crawl import CrawlDependencies, CrawlExecutor
from loreley_crawler.infrastructure.indexer_client import HttpIndexerClient, IndexerClient
from loreley_crawler.infrastructure.opensearch import (
    OpenSearchRepository,
    Repository,
    create_heartbeat_client,
    create_store_client,
)
from loreley_crawler.jobs import (
    CancelRequestRegistry,
    DocumentRecords,
    JobAdmission,
    JobCancellation,
    JobHistory,
    JobRunner,
    JobType,
    LockRelease,
    RunnerWakeup,
    StartupRecovery,
)
from loreley_crawler.jobs.locks import Heartbeat, LockStore
from loreley_crawler.jobs.records import JobRecordStore, is_maintenance_enabled
from loreley_crawler.scheduler import Scheduler
from loreley_crawler.source_delete import SourceDeleteDependencies, SourceDeleteExecutor
from loreley_crawler.sources import SourceReader, SourceStore

logger = logging.getLogger(__name__)

# 停止時に、スレッドの終了を待つ上限(仮値。止まっているスレッドを見つけて警告するための待ち)。
STOP_JOIN_TIMEOUT_SECONDS = 5.0
# 停止時に、処理中の HTTP リクエストの完了を待つ上限(仮値。接続を持ち続けるクライアントで
# 停止が終わらないようにする)。
HTTP_GRACEFUL_SHUTDOWN_SECONDS = 10


@dataclass(frozen=True)
class Backends:
    """外部システムへの窓口。テストでは、メモリ上の代役に差し替える。"""

    sources_repository: Repository
    jobs_repository: Repository
    heartbeat_jobs_repository: Repository
    indexer_client: IndexerClient


@dataclass(frozen=True)
class Components:
    """組み立てた部品。`start_components`・`stop_components` が、起動順・停止順で使う。"""

    recovery: StartupRecovery
    runner: JobRunner
    scheduler: Scheduler
    api_dependencies: ApiDependencies
    # `JobRunner` に渡したものと同じ。本体では使わず、専用 Repository への配線をテストが確かめる。
    heartbeat_factory: Callable[[], Heartbeat]


def create_backends(config: CrawlerConfig) -> Backends:
    """OpenSearch のクライアント 2 つ(Store 層・ハートビート専用)と、Repository 3 つを作る。

    クライアントを作るだけで、接続はしない(最初の読み書きが接続する)。Repository の数と索引は
    R7 の機械検査(`tests/architecture/test_write_rules.py`)が見る。ここ以外では作らない。
    """
    store_client = create_store_client(config.opensearch)
    heartbeat_client = create_heartbeat_client(config.opensearch)
    return Backends(
        sources_repository=OpenSearchRepository(
            store_client, config.sources_index_name, config.repository
        ),
        jobs_repository=OpenSearchRepository(
            store_client, config.jobs_index_name, config.repository
        ),
        heartbeat_jobs_repository=OpenSearchRepository(
            heartbeat_client, config.jobs_index_name, config.repository
        ),
        indexer_client=HttpIndexerClient(config.indexer),
    )


def assemble(
    config: CrawlerConfig,
    backends: Backends,
    *,
    clock: Clock,
    connector_registry: ConnectorRegistry | None = None,
) -> Components:
    """各モジュールを組み立てる。I/O もスレッドの開始もしない(順序の制約は `start_components`)。

    共有する物は 1 つずつ作る: 取り消し要求(`CancelRequestRegistry`)、起床通知(`RunnerWakeup`)、
    `JobAdmission`(API と Scheduler が同じもの)、`SourceStore`(`api` と `source_delete`)。
    リトライは、確認点なしの `Retrier`(HTTP ハンドラ・Scheduler・回復・Job Runner)。実行対象は、
    `JobContext` から確認点つきのものを受ける。
    """
    retrier = Retrier(config.retry_policy)
    registry = connector_registry or create_connector_registry(fs_settings=config.file_system)
    jobs_repository = backends.jobs_repository

    source_reader = SourceReader(backends.sources_repository)
    source_store = SourceStore(backends.sources_repository, clock, retrier)
    job_store = JobRecordStore(jobs_repository)
    lock_store = LockStore(jobs_repository, clock)
    heartbeat_lock_store = LockStore(backends.heartbeat_jobs_repository, clock)
    document_records = DocumentRecords(jobs_repository, clock)
    job_history = JobHistory(jobs_repository)
    read_maintenance_flag = partial(is_maintenance_enabled, jobs_repository)
    cancel_requests = CancelRequestRegistry()
    wakeup = RunnerWakeup()

    admission = JobAdmission(
        settings=config.jobs,
        source_reader=source_reader,
        job_store=job_store,
        lock_store=lock_store,
        read_maintenance_flag=read_maintenance_flag,
        clock=clock,
        retrier=retrier,
        wakeup=wakeup,
    )
    cancellation = JobCancellation(
        job_store=job_store,
        lock_store=lock_store,
        cancel_requests=cancel_requests,
        clock=clock,
        retrier=retrier,
    )
    lock_release = LockRelease(
        settings=config.jobs,
        job_store=job_store,
        lock_store=lock_store,
        clock=clock,
        retrier=retrier,
    )
    executors = {
        JobType.CRAWL: CrawlExecutor(
            CrawlDependencies(
                source_reader=source_reader,
                connector_registry=registry,
                indexer_client=backends.indexer_client,
                document_records=document_records,
                job_history=job_history,
                clock=clock,
                settings=config.crawl,
                documents_settings=config.documents,
            )
        ),
        JobType.SOURCE_DELETE: SourceDeleteExecutor(
            SourceDeleteDependencies(
                source_store=source_store,
                indexer_client=backends.indexer_client,
                document_records=document_records,
            )
        ),
    }

    def heartbeat_factory() -> Heartbeat:
        return Heartbeat(heartbeat_lock_store, clock, config.jobs.heartbeat)

    return Components(
        recovery=StartupRecovery(
            settings=config.jobs,
            job_store=job_store,
            lock_store=lock_store,
            clock=clock,
            retrier=retrier,
        ),
        runner=JobRunner(
            settings=config.jobs,
            job_store=job_store,
            lock_store=lock_store,
            heartbeat_factory=heartbeat_factory,
            executors=executors,
            cancel_requests=cancel_requests,
            wakeup=wakeup,
            read_maintenance_flag=read_maintenance_flag,
            clock=clock,
            retrier=retrier,
        ),
        scheduler=Scheduler(
            settings=config.scheduler,
            source_reader=source_reader,
            admission=admission,
            clock=clock,
            retrier=retrier,
        ),
        api_dependencies=ApiDependencies(
            job_admission=admission,
            job_cancellation=cancellation,
            lock_release=lock_release,
            source_store=source_store,
            connector_registry=registry,
            retrier=retrier,
        ),
        heartbeat_factory=heartbeat_factory,
    )


def start_components(components: Components) -> FastAPI:
    """起動時の回復 → Job Runner → Scheduler → アプリケーションの作成(この順。5.7)。

    回復が失敗すれば、例外が伝わり、スレッドもアプリケーションも作られない。スレッドの開始以降で
    失敗したときは、開始したスレッドを止めて(`stop_components`)から例外を伝える。
    """
    report = components.recovery.run()
    logger.info(
        "startup recovery finished: failed_jobs=%d deleted_locks=%d kept_locks=%d",
        len(report.failed_job_ids),
        len(report.deleted_lock_source_ids),
        len(report.kept_lock_source_ids),
    )
    try:
        components.runner.start()
        components.scheduler.start()
        return create_app(components.api_dependencies)
    except BaseException:
        stop_components(components)
        raise


def stop_components(
    components: Components, *, join_timeout_seconds: float = STOP_JOIN_TIMEOUT_SECONDS
) -> tuple[str, ...]:
    """Scheduler → Job Runner の順に停止を要求し、終了を待つ。上限までに終わらなかった名前を返す。

    実行中のジョブの完了は待たず、最終状態の記録・ロックの解放もしない(CM-U-4)。
    """
    components.scheduler.request_stop()
    components.runner.request_stop()
    not_stopped = tuple(
        name
        for name, is_stopped in (
            ("scheduler", components.scheduler.join(join_timeout_seconds)),
            ("job-runner", components.runner.join(join_timeout_seconds)),
        )
        if not is_stopped
    )
    for name in not_stopped:
        # 実行中のジョブの中などで止まっている。放置して終了する(次回の回復が `failed` にする)。
        logger.warning(
            "a thread did not stop in time and is left to the process exit: name=%s", name
        )
    return not_stopped


def http_server_options(config: CrawlerConfig) -> dict[str, Any]:
    """`uvicorn.run(app, **options)` の引数。

    アプリケーションのオブジェクトを渡し、ワーカー数は指定しない(単一プロセス)。ログの設定は
    `configure_logging` に任せ(`log_config=None`)、uvicorn のアクセスログは無効にする
    (`api/middleware.py` がルートのテンプレートだけを出す)。
    """
    return {
        "host": config.http_host,
        "port": config.http_port,
        "log_config": None,
        "access_log": False,
        "lifespan": "off",
        "timeout_graceful_shutdown": HTTP_GRACEFUL_SHUTDOWN_SECONDS,
    }


def _ignore_signal(signal_number: int, frame: FrameType | None) -> None:
    """何もしない。止めるのは uvicorn のハンドラで、これは「再送出された後」の受け皿。"""


@contextmanager
def _return_normally_after_a_stop_signal() -> Iterator[None]:
    """SIGTERM・SIGINT で `uvicorn.run` が戻った後も、`main` の停止処理が走るようにする。

    uvicorn は、シグナルで graceful shutdown した後、元のシグナルハンドラを戻して同じシグナルを
    再送出する。元のハンドラが SIGTERM の既定(終了)だと、`uvicorn.run` から戻る前にプロセスが
    終わり、停止処理(`stop_components`)が走らない(SIGINT は `KeyboardInterrupt` で戻る)。
    そこで、uvicorn が「元のハンドラ」として戻すものを、何もしない関数にする。コンテナ(PID 1)でも
    そうでなくても同じ挙動になる。`uvicorn.run` の前後だけで入れ替え、起動中(回復など)のシグナルは
    既定のまま(プロセスが終わる)。
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    stop_signals = (signal.SIGTERM, signal.SIGINT)
    original_handlers = {number: signal.signal(number, _ignore_signal) for number in stop_signals}
    try:
        yield
    finally:
        for number, handler in original_handlers.items():
            signal.signal(number, handler)


def main() -> None:
    config = load_config()
    configure_logging(level=config.log_level, secrets=config.log_secrets)
    warn_about_unchecked_indexer_limits(config)
    components = assemble(config, create_backends(config), clock=SystemClock())
    app = start_components(components)
    try:
        # bind の成否は uvicorn が知る(失敗すれば例外・終了で戻る)。ここは開始の合図だけ。
        logger.info("starting the HTTP server: owner=%s", config.jobs.owner)
        with _return_normally_after_a_stop_signal():
            uvicorn.run(app, **http_server_options(config))
    finally:
        stop_components(components)
        logger.info("the crawler stopped")


if __name__ == "__main__":
    main()
