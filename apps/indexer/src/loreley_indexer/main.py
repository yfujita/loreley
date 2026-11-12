"""エントリポイント: 依存の組み立て、起動順、停止(module 3章、5.6。arch 12章)。

起動順(FastAPI の lifespan):
1. 設定の読み込み(`Settings`)。要約が有効なのに LLM のプロバイダが未設定なら、起動を失敗させる。
2. OpenSearch のクライアント(通常と `delete_by_query` 専用の 2 つ)とアダプタ。
3. 各機能の組み立て。`CrawlRuns` の `wake` と削除ワーカーは同じイベントでつなぐ。
4. 未完了の削除結果の整理(`fail_unfinished_crawls_after_restart`)を、HTTP の受け付けの前に 1 回。
5. 削除ワーカーの起動。整理の後に始める(先に始めると、再起動前に受理した削除を再開してしまう)。
6. 要約ワーカーの起動(起動時の再走査の要請を含む。受け付けと並行して進む)。
7. HTTP の受け付けの開始(`ready` を立てる。`/healthz` が 200 を返す)。
停止は逆順(受け付けの停止、要約ワーカー、削除ワーカー、OpenSearch の接続)。

uvicorn は単一プロセス(ワーカー数 1)で動かす。ソース単位のロック・削除ワーカー・起床通知は
プロセス内のため、複数プロセスは対象外(arch 13.2)。
起動: `python -m loreley_indexer.main`
"""

import logging
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import ExitStack, asynccontextmanager
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI
from pydantic import ValidationError

from loreley_indexer.api import ApiDependencies, create_api_app
from loreley_indexer.common.clock import Clock, SystemClock
from loreley_indexer.common.log_setup import configure_logging
from loreley_indexer.common.source_locks import SourceLocks
from loreley_indexer.config import Settings
from loreley_indexer.crawl_runs import AdmissionChecker, CrawlRuns, create_deletion_manager
from loreley_indexer.documents import DocumentRegistrar, LastSeenUpdater, create_summarization
from loreley_indexer.documents.extraction import TextExtractor
from loreley_indexer.infrastructure.llm import DisabledLlmClient, LlmClient
from loreley_indexer.infrastructure.opensearch import (
    OpenSearchSearchIndexRepository,
    OpenSearchStore,
    SearchIndexRepository,
    StoreJobsReader,
    StoreReader,
    StoreRepository,
    close_clients,
    create_delete_by_query_client,
    create_opensearch_client,
)

logger = logging.getLogger(__name__)

MAX_REPORTED_SETTING_ERRORS = 10
INVALID_CONNECTION_MESSAGE = (
    "invalid OpenSearch connection settings "
    "(the URL must be valid and must not contain credentials)"
)


class StartupError(Exception):
    """起動を続けられない設定の食い違い。メッセージは固定文と、フィールド名・検証の種別だけ(値なし)。"""


@dataclass(frozen=True)
class Backends:
    """外部システムへの窓口。テストでは、インメモリの代役に差し替える。"""

    search_index: SearchIndexRepository
    deletions_store: StoreRepository
    jobs_store: StoreReader  # `loreley-jobs` は読み取りのみ(R6)
    llm: LlmClient
    close_connections: Callable[[], None] = lambda: None  # 停止時に、OpenSearch の接続を閉じる


def create_backends(settings: Settings) -> Backends:
    """OpenSearch のクライアントを 2 つ作る。`delete_by_query` は専用(タイムアウトで再送しない)。

    LLM は、具体的なプロバイダが未実装のため、無効な既定の実装(呼ぶと例外)を使う。
    """
    # URL を解釈できないと、標準ライブラリや opensearch-py の `ValueError` は URL の一部(認証情報を
    # 含む netloc やポートの値)をメッセージに入れる。起動前の例外は標準エラー出力へそのまま出る
    # ため、固定文の `StartupError` に置き換える。`except` の外で送出し、元の例外を `__context__`
    # に残さない。
    try:
        connection = settings.opensearch_connection()
        client = create_opensearch_client(connection)
        delete_by_query_client = create_delete_by_query_client(connection)
    except ValueError:
        is_connection_valid = False
    else:
        is_connection_valid = True
    if not is_connection_valid:
        raise StartupError(INVALID_CONNECTION_MESSAGE)

    index_names = settings.index_names()
    return Backends(
        search_index=OpenSearchSearchIndexRepository(
            client,
            index_names.search_index,
            update_retry_on_conflict=settings.update_retry_on_conflict,
            delete_by_query_client=delete_by_query_client,
            delete_by_query_timeout_seconds=connection.delete_by_query_timeout_seconds,
        ),
        deletions_store=OpenSearchStore(client, index_names.deletions),
        jobs_store=OpenSearchStore(client, index_names.jobs),
        llm=DisabledLlmClient(),
        close_connections=lambda: close_clients(client, delete_by_query_client),
    )


def build_application(
    settings: Settings, backends: Backends, *, clock: Clock | None = None
) -> FastAPI:
    """機能を組み立てて、FastAPI アプリケーションを作る。起動・停止は lifespan で行う。"""
    if settings.summary_enabled and isinstance(backends.llm, DisabledLlmClient):
        raise StartupError("summarization is enabled but no LLM provider is configured")
    clock = clock if clock is not None else SystemClock()

    wake_event = threading.Event()
    jobs = StoreJobsReader(backends.jobs_store)
    runs = CrawlRuns(
        config=settings.lifecycle_config(),
        deletions_store=backends.deletions_store,
        clock=clock,
        wake=wake_event.set,
    )
    deletion = create_deletion_manager(
        settings.deletion_config(),
        results=runs.results,
        search_index=backends.search_index,
        jobs=jobs,
        clock=clock,
        wake_event=wake_event,
    )
    summarization = create_summarization(
        settings.summarization_config(),
        search_index=backends.search_index,
        jobs=jobs,
        llm=backends.llm,
        clock=clock,
    )
    # 登録と `last-seen` は、同じソース単位のロックで直列化する(案19)。
    source_locks = SourceLocks()
    admission_checker = AdmissionChecker(backends.deletions_store)
    registration_config = settings.registration_config()
    registrar = DocumentRegistrar(
        config=registration_config,
        admission_checker=admission_checker,
        search_index=backends.search_index,
        jobs=jobs,
        extractor=TextExtractor(settings.extraction_config()),
        summary_requests=summarization.requests,
        source_locks=source_locks,
        clock=clock,
    )
    last_seen = LastSeenUpdater(
        config=registration_config,
        admission_checker=admission_checker,
        search_index=backends.search_index,
        jobs=jobs,
        source_locks=source_locks,
        clock=clock,
    )

    ready = threading.Event()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # 後に登録したものから順に実行される。ある停止が例外を投げても、残りは実行される
        # (要約の停止が失敗しても、削除ワーカーを止め、接続を閉じる)。
        with ExitStack() as shutdown:
            shutdown.callback(backends.close_connections)
            failed_count = runs.fail_unfinished_crawls_after_restart()
            logger.info(
                "unfinished deletion results were failed after the restart: count=%d", failed_count
            )
            deletion.start()
            shutdown.callback(deletion.stop)
            shutdown.callback(summarization.stop)  # 開始の途中で失敗しても、止める
            summarization.start()
            ready.set()
            shutdown.callback(ready.clear)
            logger.info("the indexer is ready")
            yield

    return create_api_app(
        dependencies=ApiDependencies(
            crawl_runs=runs, deletion=deletion, registrar=registrar, last_seen=last_seen
        ),
        config=settings.api_config(),
        ready=ready,
        lifespan=lifespan,
    )


def create_app(settings: Settings) -> FastAPI:
    """ログの設定、外部システムへの窓口、機能の組み立てを行う。"""
    password = settings.opensearch_password
    configure_logging(
        level=settings.log_level,
        secrets=[password.get_secret_value()] if password is not None else [],
    )
    return build_application(settings, create_backends(settings))


def describe_settings_errors(error: ValidationError) -> str:
    """設定の検証エラーを、フィールド名と検証の種別(`type`)だけで表す(R9)。

    pydantic の表示(`str(error)`)は、入力の環境変数の辞書(`OPENSEARCH_PASSWORD` を含む)や
    不正な値(`input_value`)をそのまま出す。`SecretStr` でも防げないため、`input`・`ctx`・
    本文(`msg`)は使わない。フィールドを持たない整合の検証は、`type` が検証名になる。
    """
    errors = error.errors(include_url=False, include_context=False, include_input=False)
    reported = [
        f"{'.'.join(str(part) for part in item['loc']) or 'settings'}: {item['type']}"
        for item in errors[:MAX_REPORTED_SETTING_ERRORS]
    ]
    omitted_count = len(errors) - len(reported)
    if omitted_count > 0:
        reported.append(f"... and {omitted_count} more")
    return "; ".join(reported)


def load_settings() -> Settings:
    """環境変数から設定を読む。不正なら、値を含まない `StartupError` で起動に失敗する。"""
    try:
        return Settings()  # 必須の項目は環境変数から読む(足りなければ起動に失敗する)
    except ValidationError as error:
        description = describe_settings_errors(error)
    # `except` の外で送出し、元の例外(入力値を持つ)を `__context__` に連鎖させない。
    raise StartupError(f"invalid settings: {description}")


def main() -> None:
    settings = load_settings()
    app = create_app(settings)
    # アプリケーションのオブジェクトを渡すので単一プロセス(ワーカーは増やさない)。
    # ログの設定は `configure_logging` に任せ(`log_config=None`)、uvicorn のアクセスログは
    # 本文や ID を含みうるパスを出すため無効にする(自前のアクセスログを使う)。
    uvicorn.run(
        app,
        host=settings.http_host,
        port=settings.http_port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
