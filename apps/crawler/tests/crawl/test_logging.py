"""ログ・ジョブ記録に、本文・`connector_config`・秘密が出ないこと(R11。完了条件 8)。

センチネル文字列を、文書の本文・`connector_config`(認証情報の参照名)・想定外の例外のメッセージに
置き、成功・失敗のさまざまな経路を実行して、全ログとジョブ記録(`loreley-jobs` の全記録)を検査する。
"""

import json
import logging
from collections.abc import Callable

import pytest

from loreley_crawler.common.errors import StoreUnexpectedResponseError
from loreley_crawler.connectors.interface import Completed, DocumentRef
from loreley_crawler.documents import DocumentsSettings
from loreley_crawler.infrastructure.indexer_client import (
    FailureType,
    IndexerRejected,
    IndexerUnavailable,
)
from loreley_crawler.sources import SourceSettingsInput, SourceStatus
from loreley_crawler.sources.records import build_body
from tests.crawl.support import CrawlEnv, crawl_env
from tests.fakes import in_memory_repository as ops
from tests.fakes.clock import DEFAULT_NOW
from tests.fakes.fake_connector import CREATE, NEXT, fetched_document
from tests.fakes.fake_indexer_client import (
    FINISH_CRAWL,
    GET_CRAWL_STATUS,
    REGISTER_DOCUMENTS,
    START_CRAWL,
)
from tests.jobs.support import JOB_ID, SOURCE_ID

BODY = "SENTINEL_BODY_c1d2e3"
CONFIG = "SENTINEL_CONFIG_REF_9f8e"
SECRET = "SENTINEL_SECRET_77aa"
SENTINELS = (BODY, CONFIG, SECRET)


def use_sentinel_config(env: CrawlEnv) -> None:
    env.jobs.sources_repository.seed(
        SOURCE_ID,
        build_body(
            SOURCE_ID,
            "file_system",
            SourceSettingsInput(
                {"root": "/data", "credentials_ref": CONFIG, "password": SECRET}, 100, 0.5, 3, None
            ),
            status=SourceStatus.ACTIVE,
            updated_at=DEFAULT_NOW,
        ),
    )


def dump_job_store(env: CrawlEnv) -> str:
    repository = env.jobs.jobs_repository
    return json.dumps({i: repository.body_of(i) for i in repository.record_ids()})


def run_scenario(env: CrawlEnv) -> None:
    try:
        env.executor(env.record, env.context)
    except Exception as error:
        # 伝播する例外(最終状態を記録できなかった場合など)も、メッセージ・repr に出さない。
        assert not any(s in f"{error!s}{error!r}" for s in SENTINELS)


def scenario_success(env: CrawlEnv) -> None:
    pass


def scenario_rejected_document(env: CrawlEnv) -> None:
    env.indexer.registration_failures["a"] = FailureType.DOCUMENT_REJECTED


def scenario_unavailable_indexer(env: CrawlEnv) -> None:
    env.indexer.behavior.inject(REGISTER_DOCUMENTS, IndexerUnavailable("timeout"), times=None)


def scenario_rejected_request(env: CrawlEnv) -> None:
    env.indexer.behavior.inject(START_CRAWL, IndexerRejected(400, "invalid_request"))


def scenario_unexpected_connector_create_error(env: CrawlEnv) -> None:
    env.connector_type.behavior.inject(CREATE, RuntimeError(f"cannot open {CONFIG} {SECRET}"))


def scenario_unexpected_enumeration_error(env: CrawlEnv) -> None:
    env.connector.behavior.inject(NEXT, RuntimeError(f"cannot read {BODY}"))


def scenario_unexpected_store_response(env: CrawlEnv) -> None:
    env.jobs.jobs_repository.behavior.inject(
        ops.SCAN, StoreUnexpectedResponseError("http_400"), times=None
    )


def scenario_finish_notice_rejected(env: CrawlEnv) -> None:
    env.indexer.behavior.inject(FINISH_CRAWL, IndexerRejected(409, "finish_content_mismatch"))


def scenario_polling_never_finds_the_crawl(env: CrawlEnv) -> None:
    env.indexer.behavior.inject(
        GET_CRAWL_STATUS, IndexerRejected(404, "crawl_not_found"), times=None
    )


def scenario_unexpected_error_while_polling(env: CrawlEnv) -> None:
    env.indexer.behavior.inject(GET_CRAWL_STATUS, RuntimeError(f"cannot read {BODY} {SECRET}"))


def scenario_lock_lost(env: CrawlEnv) -> None:
    env.indexer.behavior.before(
        REGISTER_DOCUMENTS, lambda: env.heartbeat.record_loss("lock_missing")
    )


def scenario_cancelled(env: CrawlEnv) -> None:
    env.indexer.behavior.before(
        REGISTER_DOCUMENTS, lambda: env.jobs.cancel_requests.request(JOB_ID)
    )


def scenario_maintenance(env: CrawlEnv) -> None:
    env.indexer.behavior.before(REGISTER_DOCUMENTS, lambda: env.jobs.seed_maintenance(True))


def scenario_oversize(env: CrawlEnv) -> None:
    env.connector.documents["a"] = fetched_document(BODY.encode() * 10)


@pytest.mark.parametrize(
    "scenario",
    [
        scenario_success,
        scenario_rejected_document,
        scenario_unavailable_indexer,
        scenario_rejected_request,
        scenario_unexpected_connector_create_error,
        scenario_unexpected_enumeration_error,
        scenario_unexpected_store_response,
        scenario_oversize,
        scenario_finish_notice_rejected,
        scenario_polling_never_finds_the_crawl,
        scenario_unexpected_error_while_polling,
        scenario_lock_lost,
        scenario_cancelled,
        scenario_maintenance,
    ],
    ids=lambda scenario: scenario.__name__.removeprefix("scenario_"),
)
def test_no_log_or_record_contains_a_body_a_connector_config_or_a_secret(
    scenario: Callable[[CrawlEnv], None], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    with crawl_env(
        items=[DocumentRef("a", "a"), DocumentRef("b", "b"), Completed()],
        documents={"a": fetched_document(BODY.encode()), "b": fetched_document(BODY.encode())},
        documents_settings=DocumentsSettings(max_raw_bytes=len(BODY) * 2),
    ) as env:
        use_sentinel_config(env)
        scenario(env)

        run_scenario(env)

        logged = "\n".join(
            f"{record.getMessage()}\n{record.exc_text or ''}\n{record.__dict__.get('stack_info')}"
            for record in caplog.records
        )
        assert logged  # ログが出ていること(検査が空振りしない)
        for sentinel in SENTINELS:
            assert sentinel not in logged
            assert sentinel not in dump_job_store(env)
