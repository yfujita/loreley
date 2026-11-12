"""ログに本文・ID・秘密値を出さないこと(R9、完了条件 10)。

センチネル文字列を、リクエストの各項目(本文、`source_id`、`crawl_id`、`lock.owner`、ID の一覧、
`raw_content`)に入れて、DEBUG までのすべてのログ・応答に現れないことを確かめる。

- api 層(ドメインの代役): 正常・400(形式不正と、ドメインの `ValueError`)・409・503・500 を、
  8 つのエンドポイントすべてに通す。モードごとの期待ステータスを固定する(空振りの防止)。
- 通し(fake の OpenSearch、ワーカーの非同期のログを含む): 正常な一連の流れと、下位の失敗。

検査するのは、テストのクライアント(httpx2・httpcore2)以外のすべてのロガー(Indexer、uvicorn、
starlette、anyio、asyncio、opensearchpy など)。

例外: `crawl_id` は、`crawl_runs` が運用のために意図して出している(案 16: 未知の `crawl_id` の
終了通知、削除の完了・失敗、不正な記録の ID)。ジョブの ID で本文でも秘密でもない。
api 層(アクセスログ・エラーログ)には出さない。
"""

import ast
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from loreley_indexer.common.errors import CrawlNotFoundError, LockNotOwnedError
from loreley_indexer.crawl_runs import CrawlStatus
from loreley_indexer.crawl_runs.lifecycle import DeletionStatus, deletion_result_record_id
from loreley_indexer.documents.document_id import compute_document_id
from loreley_indexer.infrastructure.opensearch import OpenSearchUnavailableError
from loreley_indexer.main import Backends, build_application
from tests.api.factories import (
    batch_json,
    document_json,
    encode,
    finish_json,
    last_seen_json,
    lock_json,
    make_settings,
    start_json,
)
from tests.api.stubs import StubDependencies, stub_client
from tests.crawl_runs.factories import hex_id, make_result, seed_malformed_result, seed_result
from tests.documents.factories import seed_lock
from tests.fakes import in_memory_store as store_ops
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore
from tests.fakes.llm import FakeLlmClient
from tests.fakes.waiting import wait_until
from tests.log_records import record_text

SOURCE = "SENTINEL-SOURCE-ID"
CRAWL = "SENTINEL-CRAWL-ID"
OWNER = "SENTINEL-LOCK-OWNER"
BODY = "SENTINEL-BODY-TEXT"
EXTERNAL_ID = "SENTINEL-EXTERNAL-ID.txt"
TITLE = "SENTINEL-TITLE"
URL = "https://SENTINEL-URL.example/"
PATH = "SENTINEL-PATH/a.txt"
PASSWORD = "SENTINEL-PASSWORD"
EXCEPTION_MESSAGE = "SENTINEL-EXCEPTION-MESSAGE"

DOCUMENT_ID = compute_document_id(SOURCE, EXTERNAL_ID)
LISTED_IDS = [hex_id(0xABC), hex_id(0xDEF)]
RAW_CONTENT = encode(BODY.encode("utf-8"))

# どのログにも出てはならない値。
FORBIDDEN = [
    SOURCE,
    OWNER,
    BODY,
    EXTERNAL_ID,
    TITLE,
    URL,
    PATH,
    PASSWORD,
    EXCEPTION_MESSAGE,
    DOCUMENT_ID,
    *LISTED_IDS,
    RAW_CONTENT,
]


# テストのクライアントが出すログ(リクエストの URL を出す)。サーバ側の実装のログではない。
TEST_CLIENT_LOGGERS = {"httpx", "httpx2", "httpcore", "httpcore2"}


def server_side_records(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    """テストのクライアント以外のすべてのロガー(Indexer・uvicorn・asyncio など)の記録。"""
    return [record for record in records if record.name.split(".")[0] not in TEST_CLIENT_LOGGERS]


def assert_no_forbidden_value(
    records: list[logging.LogRecord], responses: list[Any], *, allow_crawl_id_in: str | None = None
) -> None:
    """`records` のサーバ側のログと、`responses` のうちエラー応答に、禁止された値が現れない。

    成功の応答は、契約で ID・`external_id` を返すので対象にしない。
    """
    for record in server_side_records(records):
        text = record_text(record)
        for value in FORBIDDEN:
            assert value not in text, f"{value!r} appeared in a log record of {record.name}"
        if CRAWL in text:
            assert allow_crawl_id_in is not None and record.name.startswith(allow_crawl_id_in), (
                f"the crawl_id appeared in a log record of {record.name}"
            )
        assert record.exc_info is None
        assert record.stack_info is None
        assert not record.exc_text
    for response in responses:
        if response.status_code < 400:
            continue
        for value in [*FORBIDDEN, CRAWL]:
            assert value not in response.text


@pytest.fixture
def debug_logs(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG)
    return caplog


# --- api 層のログ(アクセスログ・エラーログ) ---


def sentinel_requests() -> list[tuple[str, str, Any]]:
    """センチネルをあらゆる項目に入れたリクエスト(パスのテンプレートごとに)。"""
    document = document_json(EXTERNAL_ID, text=BODY, title=TITLE, url=URL, path=PATH)
    batch = batch_json([document], crawl_id=CRAWL, lock=lock_json(owner=OWNER, job_id=CRAWL))
    return [
        ("POST", "/crawls/start", start_json(crawl_id=CRAWL, source_id=SOURCE)),
        (
            "POST",
            f"/crawls/{CRAWL}/finish",
            finish_json(
                source_id=SOURCE, skipped_document_ids=LISTED_IDS, oversize_document_ids=LISTED_IDS
            ),
        ),
        ("GET", f"/crawls/{CRAWL}", None),
        ("POST", f"/sources/{SOURCE}/documents:batch", batch),
        (
            "POST",
            f"/sources/{SOURCE}/last-seen",
            last_seen_json(LISTED_IDS, crawl_id=CRAWL, lock=lock_json(owner=OWNER, job_id=CRAWL)),
        ),
        ("POST", f"/sources/{SOURCE}/deletions:discard", {"lock": lock_json(owner=OWNER)}),
        ("DELETE", f"/sources/{SOURCE}/documents", {"lock": lock_json(owner=OWNER)}),
        ("DELETE", f"/sources/{SOURCE}/deletion-records", {"lock": lock_json(owner=OWNER)}),
    ]


# モードごとの、`sentinel_requests()` の 8 つの応答の期待ステータス。
# 順序: start, finish, status(GET。本文がないので形式不正にならない), batch, last-seen,
# discard, DELETE documents, DELETE deletion-records
EXPECTED_STATUSES = {
    "ok": [200, 202, 200, 200, 200, 200, 200, 200],
    "invalid": [400, 400, 200, 400, 400, 400, 400, 400],
    "domain-value-error": [400] * 8,
    "conflict": [409] * 8,
    "unavailable": [503] * 8,
    "unexpected": [500] * 8,
}
_DOMAIN_ERRORS = {
    "domain-value-error": ValueError(EXCEPTION_MESSAGE),
    "conflict": LockNotOwnedError(),
    "unavailable": OpenSearchUnavailableError("http_503"),
    "unexpected": RuntimeError(EXCEPTION_MESSAGE),
}


def make_status() -> CrawlStatus:
    """`ok` のモードの Status の応答(`MagicMock` を返すと、写像に失敗して 500 になる)。"""
    return CrawlStatus(
        crawl_id=CRAWL,
        source_id=SOURCE,
        status=DeletionStatus.RUNNING,
        reason=None,
        forced=False,
        target_count=None,
        denominator=None,
        ttl=86_400,
        ratio_threshold=0.2,
        min_delete_count=10,
        deleted_count=None,
        enumerated_count=None,
        n_seen=None,
        e_missing=None,
        finish_received_at=None,
        deletion_started_at=None,
        finished_at=None,
        waiting_for=None,
    )


@pytest.mark.parametrize("mode", EXPECTED_STATUSES)
def test_the_api_layer_logs_no_value_of_any_request_on_any_outcome(
    mode: str, debug_logs: pytest.LogCaptureFixture
) -> None:
    """8 つのエンドポイントすべてに、モード(正常・形式不正・各エラー)ごとの応答を返させる。"""
    stubs = StubDependencies()
    stubs.crawl_runs.crawl_status.return_value = make_status()
    if mode in _DOMAIN_ERRORS:
        for entry in (stubs.crawl_runs, stubs.deletion, stubs.registrar, stubs.last_seen):
            entry.configure_mock(**{name: _raising(_DOMAIN_ERRORS[mode]) for name in _METHODS})

    responses = []
    with stub_client(stubs) as client:
        for method, path, body in sentinel_requests():
            if mode == "invalid":
                body = _corrupt(body)
            responses.append(client.request(method, path, json=body))

    assert [response.status_code for response in responses] == EXPECTED_STATUSES[mode]
    assert any(record.name == "loreley_indexer.api.access" for record in debug_logs.records)
    # `crawl_id` を含めてセンチネルが出ない(代役のドメインは何も出さない)。
    assert_no_forbidden_value(debug_logs.records, responses)


_METHODS = [
    "start_crawl",
    "finish_crawl",
    "crawl_status",
    "register",
    "update",
    "discard_source_crawls",
    "delete_source_documents",
    "delete_source_records",
]


def _raising(error: Exception) -> MagicMock:
    return MagicMock(side_effect=error)


def _corrupt(body: Any) -> Any:
    """形式を壊す(センチネルは入力に残ったまま、型だけが不正。終了通知は `outcome` を壊す)。"""
    if not isinstance(body, dict):
        return body
    return {
        **body,
        "ttl": 1.5,
        "outcome": SOURCE,
        "lock": SOURCE,
        "documents": SOURCE,
        "document_ids": SOURCE,
    }


def test_the_access_log_has_only_the_method_the_route_template_the_status_and_the_time(
    debug_logs: pytest.LogCaptureFixture,
) -> None:
    stubs = StubDependencies()
    stubs.crawl_runs.crawl_status.side_effect = CrawlNotFoundError()
    with stub_client(stubs) as client:
        client.post(f"/sources/{SOURCE}/last-seen", json=last_seen_json([]))
        client.get(f"/crawls/{CRAWL}")
        client.get(f"/unknown/{SOURCE}")

    lines = [r.getMessage() for r in debug_logs.records if r.name == "loreley_indexer.api.access"]
    assert [line.rsplit(" ", 1)[0] for line in lines] == [
        "POST /sources/{source_id}/last-seen 200",
        "GET /crawls/{crawl_id} 404",
        "GET - 404",
    ]
    assert all(line.endswith("ms") for line in lines)


def test_an_unexpected_exception_is_logged_by_class_name_only(
    debug_logs: pytest.LogCaptureFixture,
) -> None:
    stubs = StubDependencies()
    stubs.crawl_runs.crawl_status.side_effect = RuntimeError(EXCEPTION_MESSAGE)

    with stub_client(stubs) as client:
        client.get(f"/crawls/{CRAWL}")

    errors = [r for r in debug_logs.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert (
        errors[0].getMessage().startswith("request failed unexpectedly: error=RuntimeError origin=")
    )
    assert errors[0].exc_info is None
    assert EXCEPTION_MESSAGE not in debug_logs.text


def test_an_unavailable_error_is_logged_by_its_reason_only(
    debug_logs: pytest.LogCaptureFixture,
) -> None:
    stubs = StubDependencies()
    stubs.crawl_runs.crawl_status.side_effect = OpenSearchUnavailableError("http_503")

    with stub_client(stubs) as client:
        client.get(f"/crawls/{CRAWL}")

    warnings = [r.getMessage() for r in debug_logs.records if r.levelno == logging.WARNING]
    assert warnings == ["the indexer is unavailable: reason=http_503"]


# --- 通しの経路(fake の OpenSearch。ドメイン・ワーカーのログも含む) ---


@pytest.fixture
def app_with_backends(
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    llm: FakeLlmClient,
    clock: FixedClock,
) -> FastAPI:
    backends = Backends(
        search_index=search_index, deletions_store=deletions_store, jobs_store=jobs_store, llm=llm
    )
    settings = make_settings(opensearch_password=PASSWORD)
    return build_application(settings, backends, clock=clock)


@pytest.fixture
def full_stack_client(app_with_backends: FastAPI) -> Iterator[TestClient]:
    with TestClient(app_with_backends, raise_server_exceptions=False) as client:
        yield client


TERMINAL_STATUSES = {status.value for status in DeletionStatus if status.is_terminal}


def _status_of(client: TestClient) -> str:
    return client.get(f"/crawls/{CRAWL}").json()["status"]


def test_a_full_crawl_never_logs_a_value_except_the_crawl_id_from_crawl_runs(
    full_stack_client: TestClient,
    jobs_store: InMemoryStore,
    deletions_store: InMemoryStore,
    debug_logs: pytest.LogCaptureFixture,
) -> None:
    seed_lock(jobs_store, source_id=SOURCE, owner=OWNER, job_id=CRAWL)
    lock = lock_json(owner=OWNER, job_id=CRAWL)
    document = document_json(EXTERNAL_ID, text=BODY, title=TITLE, url=URL, path=PATH)
    responses = [
        full_stack_client.post("/crawls/start", json=start_json(crawl_id=CRAWL, source_id=SOURCE)),
        full_stack_client.post(
            f"/sources/{SOURCE}/last-seen",
            json=last_seen_json([DOCUMENT_ID], crawl_id=CRAWL, lock=lock),
        ),
        full_stack_client.post(
            f"/sources/{SOURCE}/documents:batch",
            json=batch_json([document], crawl_id=CRAWL, lock=lock),
        ),
        full_stack_client.post(
            f"/crawls/{CRAWL}/finish",
            json=finish_json(
                source_id=SOURCE,
                enumerated_count=1,
                skipped_document_ids=LISTED_IDS,
                oversize_document_ids=[],
            ),
        ),
        full_stack_client.post("/crawls/finish-unknown/finish", json=finish_json(source_id=SOURCE)),
        full_stack_client.get(f"/crawls/{CRAWL}"),
        full_stack_client.post(
            f"/sources/{SOURCE}/documents:batch",
            json=batch_json([document], crawl_id="no-such-crawl", lock=lock),
        ),
    ]

    # 削除ワーカーは、終了通知の後に非同期でログを出す。結果が終端になる(処理が終わる)まで待つ。
    assert wait_until(lambda: _status_of(full_stack_client) in TERMINAL_STATUSES)

    assert_no_forbidden_value(
        debug_logs.records,
        responses[:5] + responses[6:],
        allow_crawl_id_in="loreley_indexer.crawl_runs",
    )
    assert responses[2].status_code == 200  # バッチは登録できた(ログの確認が空振りでない)
    # 許容した `crawl_id` が実際に出ている(許容の範囲を検証できている)。出る先は `crawl_runs` だけ。
    crawl_id_loggers = {
        record.name
        for record in server_side_records(debug_logs.records)
        if CRAWL in record_text(record)
    }
    assert crawl_id_loggers
    assert all(name.startswith("loreley_indexer.crawl_runs") for name in crawl_id_loggers)


def test_failures_of_the_backends_never_log_a_value(
    full_stack_client: TestClient,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    debug_logs: pytest.LogCaptureFixture,
) -> None:
    seed_lock(jobs_store, source_id=SOURCE, owner=OWNER, job_id=CRAWL)
    seed_result(deletions_store, make_result(crawl_id=CRAWL, source_id=SOURCE))
    seed_malformed_result(deletions_store, crawl_id="bad-record", source_id=SOURCE)
    lock = lock_json(owner=OWNER, job_id=CRAWL)
    deletions_store.behavior.inject(
        store_ops.FETCH,
        OpenSearchUnavailableError("http_503"),
        key=deletion_result_record_id(CRAWL),
    )
    document = document_json(EXTERNAL_ID, text=BODY, title=TITLE, url=URL, path=PATH)

    responses = [
        full_stack_client.post(
            f"/sources/{SOURCE}/documents:batch",
            json=batch_json([document], crawl_id=CRAWL, lock=lock),
        ),
        full_stack_client.get("/crawls/bad-record"),
        full_stack_client.post(f"/sources/{SOURCE}/last-seen", json=last_seen_json(LISTED_IDS)),
    ]

    assert [r.status_code for r in responses] == [503, 500, 409]
    assert_no_forbidden_value(
        debug_logs.records, responses, allow_crawl_id_in="loreley_indexer.crawl_runs"
    )


# --- ソースコードの検査: `extra`・`stack_info`・`exc_info` を渡さない ---

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "loreley_indexer"
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "critical", "exception", "log", "fatal"}
# ログに値(本文・ID)を持ち込みうる、`SecretRedactionFilter` が伏せない引数。
FORBIDDEN_KEYWORDS = {"extra", "stack_info", "exc_info"}


def _is_get_logger_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    function = node.func
    return (isinstance(function, ast.Attribute) and function.attr == "getLogger") or (
        isinstance(function, ast.Name) and function.id == "getLogger"
    )


def logging_calls_in(tree: ast.AST) -> Iterator[ast.Call]:
    """ロガーのメソッド呼び出し。ロガーは、`logging.getLogger(...)` の代入先の名前で見つける。

    名前は決め打ちにしない(`_log = logging.getLogger(...)` のような別名の追加で、検査から外れない)。
    `logging.warning(...)` のようなモジュール直の呼び出しも含める。
    """
    logger_names = {"logging"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign | ast.AnnAssign) and _is_get_logger_call(node.value):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            logger_names |= {target.id for target in targets if isinstance(target, ast.Name)}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in LOG_METHODS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in logger_names
        ):
            yield node


def forbidden_logging_calls_in(tree: ast.AST) -> list[int]:
    """禁止された呼び出しの行番号。ロガーの名前によらず、属性名とキーワード名だけで見つける。

    `.exception(...)`(スタックトレースを出す)と、ログのメソッド(`.info(...)` など。受け手は
    問わない)への `extra`・`stack_info`・`exc_info` の指定。pydantic の `extra="ignore"` など、
    ログと無関係の `extra` は対象にしない。
    """
    lines = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        keywords = {keyword.arg for keyword in node.keywords}
        is_exception_call = node.func.attr == "exception"
        passes_forbidden_keyword = node.func.attr in LOG_METHODS and FORBIDDEN_KEYWORDS & keywords
        if is_exception_call or passes_forbidden_keyword:
            lines.append(node.lineno)
    return lines


def source_trees() -> Iterator[tuple[str, ast.AST]]:
    for path in SOURCE_ROOT.rglob("*.py"):
        yield str(path.relative_to(SOURCE_ROOT)), ast.parse(path.read_text(encoding="utf-8"))


def test_the_logging_calls_are_found() -> None:
    assert sum(len(list(logging_calls_in(tree))) for _, tree in source_trees()) >= 15


def test_the_detector_finds_loggers_by_the_name_they_are_assigned_to() -> None:
    tree = ast.parse(
        "import logging\n"
        "_log = logging.getLogger('x')\n"
        "other: logging.Logger = logging.getLogger('y')\n"
        "_log.info('a')\n"
        "other.warning('b')\n"
        "logging.error('c')\n"
        "unrelated.info('d')\n"
    )

    assert [call.lineno for call in logging_calls_in(tree)] == [4, 5, 6]


@pytest.mark.parametrize(
    "statement",
    [
        "_log.info('a', extra={'v': 1})",
        "_log.warning('a', exc_info=True)",
        "_log.error('a', stack_info=True)",
        "_log.exception('a')",
        "anything.exception('a')",
        "logging.getLogger('x').error('a', exc_info=error)",
        "self._logger.log(20, 'a', extra={'v': 1})",
    ],
)
def test_the_detector_finds_a_forbidden_call_whatever_the_logger_is_called(statement: str) -> None:
    assert forbidden_logging_calls_in(ast.parse(statement)) == [1]


def test_the_detector_ignores_an_extra_keyword_that_has_nothing_to_do_with_logging() -> None:
    tree = ast.parse("ConfigDict(extra='ignore')\nsettings.build(extra='x')\n")

    assert forbidden_logging_calls_in(tree) == []


def test_no_logging_call_passes_extra_stack_info_or_exc_info() -> None:
    """`SecretRedactionFilter` は `extra`・`stack_info` を伏せない。そもそも渡さない。"""
    offenders = [
        f"{location}:{line}"
        for location, tree in source_trees()
        for line in forbidden_logging_calls_in(tree)
    ]

    assert offenders == []
