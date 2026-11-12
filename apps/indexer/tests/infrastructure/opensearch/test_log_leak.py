"""実際のクライアントと通信層を通しても、ログにセンチネル(ID・本文・応答の理由・秘密値)が出ない(R9)。

opensearch-py は、失敗した呼び出しごとに ID を含む URL を WARNING で出す(404 を含む)。
ローカルの HTTP スタブに実際のクライアントをつなぎ、`configure_logging(level="DEBUG")` を適用した
状態で、404・400・503・接続切断・正常の各応答を、アダプタのすべてのメソッドに返して確かめる。
"""

import io
import logging
import traceback
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from loreley_indexer.common.log_setup import configure_logging
from loreley_indexer.infrastructure.opensearch import (
    Deleted,
    DocumentFilter,
    NotFound,
    OpenSearchSearchIndexRepository,
    OpenSearchStore,
    OpenSearchUnavailableError,
    OpenSearchUnexpectedResponseError,
    RecordFilter,
    Rejected,
    SearchIndexRepository,
    StoreRepository,
    create_delete_by_query_client,
    create_opensearch_client,
)
from loreley_indexer.infrastructure.opensearch.connection import OpenSearchConnectionConfig
from tests.infrastructure.opensearch.http_stub import StubOpenSearch, StubResponse, stub_opensearch
from tests.log_records import record_text

pytestmark = pytest.mark.usefixtures("restore_logging")

ID = "SENTINEL-DOC-ID"
BODY_TEXT = "SENTINEL-BODY-TEXT"
REASON = "SENTINEL-ERROR-REASON"
PASSWORD = "SENTINEL-PASSWORD"
SENTINELS = [ID, BODY_TEXT, REASON, PASSWORD]

HTML_BODY = f"<html>{BODY_TEXT} {ID} {REASON}</html>".encode()
INSTANT = datetime(2026, 11, 9, tzinfo=UTC)
FOUND = {"found": True, "_source": {"a": BODY_TEXT}, "_seq_no": 1, "_primary_term": 1}


def error_body(error_type: str, status: int) -> dict[str, Any]:
    """本物の OpenSearch と同じ形。opensearch-py の `TransportError.__str__` は `root_cause` の
    `reason` を出す(例外が連鎖すると、traceback に載る)ので、ここにも理由を入れる。"""
    reason = f"{REASON} {ID}"
    return {
        "error": {
            "root_cause": [{"type": error_type, "reason": reason}],
            "type": error_type,
            "reason": reason,
        },
        "status": status,
    }


# 応答ごとの、アダプタの全メソッドの結果。想定外の結果は例外(`IndexerError`)で出る。
RESPONSES: dict[str, StubResponse] = {
    "document_not_found": StubResponse(404, {"_id": ID, "found": False, "result": "not_found"}),
    "document_missing": StubResponse(404, error_body("document_missing_exception", 404)),
    "index_not_found": StubResponse(404, error_body("index_not_found_exception", 404)),
    "bad_request": StubResponse(400, error_body("mapper_parsing_exception", 400)),
    "conflict": StubResponse(409, error_body("version_conflict_engine_exception", 409)),
    "unavailable": StubResponse(503, error_body("service_unavailable", 503)),
    "disconnected": StubResponse(disconnect=True),
    # 応答が遅れて、クライアントのタイムアウトになる(`TIMEOUT_SECONDS` より長く待たせる)。
    "timeout": StubResponse(200, {}, delay_seconds=0.5),
    # 認証の失敗(本文は JSON ではない)。
    "unauthorized": StubResponse(
        401, raw=f"{REASON} {ID}".encode(), content_type="text/plain; charset=UTF-8"
    ),
    # プロキシ・Ingress の 404(JSON ではない・壊れた JSON)。ID・本文・理由が混ざる想定。
    "html_404": StubResponse(404, raw=HTML_BODY, content_type="text/html"),
    "broken_json_404": StubResponse(
        404, raw=b'{"error": {"reason": "' + HTML_BODY, content_type="application/json"
    ),
    "ok_document": StubResponse(200, FOUND),
    "ok_empty": StubResponse(200, {"result": "deleted", "count": 0, "hits": {"hits": []}}),
}


@dataclass
class Adapters:
    repository: OpenSearchSearchIndexRepository
    store: OpenSearchStore


# 遅延する応答だけは短いタイムアウトにする(ほかは、負荷がかかっても失敗しない長さ)。
TIMEOUT_SECONDS = 0.1
DEFAULT_REQUEST_TIMEOUT_SECONDS = 5


def operations(adapters: Adapters) -> dict[str, Callable[[], object]]:
    repository, store = adapters.repository, adapters.store
    return {
        "repository.fetch": lambda: repository.fetch(ID),
        "repository.fetch_for_deletion": lambda: repository.fetch_for_deletion(ID),
        "repository.create": lambda: repository.create(ID, {"body": BODY_TEXT}),
        "repository.replace_if_unchanged": lambda: repository.replace_if_unchanged(
            ID, {"body": BODY_TEXT}, seq_no=1, primary_term=1
        ),
        "repository.raise_last_seen_at": lambda: repository.raise_last_seen_at(ID, INSTANT),
        "repository.delete_if_unchanged": lambda: repository.delete_if_unchanged(
            ID, seq_no=1, primary_term=1
        ),
        "repository.search_document_ids": lambda: repository.search_document_ids(
            DocumentFilter(source_id=ID), page_size=10, after=ID
        ),
        "repository.count": lambda: repository.count(DocumentFilter(source_id=ID)),
        "repository.count_existing_ids": lambda: repository.count_existing_ids([ID]),
        "repository.refresh": lambda: repository.refresh(),
        "repository.delete_by_query": lambda: repository.delete_by_query(
            DocumentFilter(source_id=ID)
        ),
        "store.fetch": lambda: store.fetch(f"lock-{ID}"),
        "store.list_records": lambda: store.list_records(
            RecordFilter(equals={"source_id": ID}), [], limit=1
        ),
        "store.save": lambda: store.save(ID, {"body": BODY_TEXT}),
        "store.replace_if_unchanged": lambda: store.replace_if_unchanged(
            ID, {"body": BODY_TEXT}, seq_no=1, primary_term=1
        ),
        "store.delete": lambda: store.delete(ID),
    }


@pytest.fixture
def log_output() -> io.StringIO:
    stream = io.StringIO()
    configure_logging(level="DEBUG", secrets=[PASSWORD], stream=stream)
    return stream


@pytest.fixture
def emitted_records(log_output: io.StringIO) -> list[logging.LogRecord]:
    """ハンドラに届いた記録そのもの(引数・例外・`extra` を含む)。設定の後に付ける。"""
    records: list[logging.LogRecord] = []

    class Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logging.getLogger().addHandler(Collector())
    return records


@contextmanager
def adapters_on(response: StubResponse) -> Iterator[tuple[Adapters, StubOpenSearch]]:
    """どのリクエストにも `response` を返すスタブに、実際のクライアント 2 つをつなぐ。"""
    timeout_seconds = (
        TIMEOUT_SECONDS if response.delay_seconds > 0 else DEFAULT_REQUEST_TIMEOUT_SECONDS
    )
    with stub_opensearch(lambda method, path: response) as stub:
        config = OpenSearchConnectionConfig(
            url=stub.url,
            username="admin",
            password=PASSWORD,
            request_timeout_seconds=timeout_seconds,
            transport_max_retries=1,
        )
        client = create_opensearch_client(config)
        delete_by_query_client = create_delete_by_query_client(config)
        try:
            repository = OpenSearchSearchIndexRepository(
                client,
                "docs",
                update_retry_on_conflict=3,
                delete_by_query_client=delete_by_query_client,
                delete_by_query_timeout_seconds=timeout_seconds,
            )
            yield Adapters(repository, OpenSearchStore(client, "records")), stub
        finally:
            client.close()
            delete_by_query_client.close()


def test_every_repository_method_is_exercised_by_the_log_checks() -> None:
    """アダプタにメソッドが増えたら、ログの検査にも加える(通し忘れを防ぐ)。"""
    names = set(operations(MagicMock()))

    assert names == {
        *(f"repository.{name}" for name in SearchIndexRepository.__abstractmethods__),
        *(f"store.{name}" for name in StoreRepository.__abstractmethods__),
    }


# 連鎖した例外を traceback に出すときの、標準ライブラリの区切り。
CHAIN_MARKERS = (
    "During handling of the above exception",
    "The above exception was the direct cause of the following exception",
)


def assert_no_sentinel_in(error: BaseException) -> None:
    """例外が利用者の目に触れる形(`str`・`repr`・連鎖を含む traceback)にセンチネルを出さない。

    元の例外(`TransportError` など)は、応答の理由・本文・ID を `str` に持つ。`from None` を
    付け忘れて連鎖させると、traceback に元の例外が載る。タイムアウト・接続エラーの元の例外は
    センチネルを持たないので、センチネルの有無だけでは見逃す。連鎖の区切りがないことも調べる。
    """
    chained_traceback = "".join(traceback.format_exception(error))
    shown = chained_traceback + repr(error) + str(error)
    for sentinel in SENTINELS:
        assert sentinel not in shown, f"{sentinel} in {type(error).__name__}"
    for marker in CHAIN_MARKERS:
        assert marker not in chained_traceback, f"{type(error).__name__} is chained to a cause"


def assert_nothing_logged_with_a_sentinel(
    log_output: io.StringIO, emitted_records: list[logging.LogRecord]
) -> None:
    output = log_output.getvalue()
    emitted = "\n".join(record_text(record) for record in emitted_records)
    for sentinel in SENTINELS:
        assert sentinel not in output, f"{sentinel} in the log output"
        assert sentinel not in emitted, f"{sentinel} in a log record"
    assert all(record.exc_info is None for record in emitted_records)


@pytest.mark.parametrize("response_name", RESPONSES)
def test_no_sentinel_reaches_the_log_through_the_real_client(
    response_name: str, log_output: io.StringIO, emitted_records: list[logging.LogRecord]
) -> None:
    with adapters_on(RESPONSES[response_name]) as (adapters, stub):
        for operation_name, operation in operations(adapters).items():
            requests_before = len(stub.requests)
            try:
                operation()
            except Exception as error:  # 結果は問わない(漏れだけを見る)。想定外の例外も含める
                assert_no_sentinel_in(error)
            # ライブラリを通っていなければ、何も確かめていない。
            assert len(stub.requests) > requests_before, operation_name

    assert_nothing_logged_with_a_sentinel(log_output, emitted_records)


def test_the_normal_not_found_path_logs_nothing(
    log_output: io.StringIO, emitted_records: list[logging.LogRecord]
) -> None:
    """文書がないのは正常な結果(メンテナンスフラグなし・初回の登録など)。ログを出さない。"""
    with adapters_on(RESPONSES["document_not_found"]) as (adapters, stub):
        assert adapters.store.fetch("maintenance") is None
        assert adapters.repository.fetch(ID) is None
        assert adapters.repository.fetch_for_deletion(ID) is None
        assert adapters.store.delete(ID) == NotFound()
        assert adapters.repository.delete_if_unchanged(ID, seq_no=1, primary_term=1) == NotFound()
        assert adapters.repository.raise_last_seen_at(ID, INSTANT) == NotFound()

    assert len(stub.requests) == 6
    assert log_output.getvalue() == ""
    assert emitted_records == []


def test_a_failure_is_still_reported_by_the_application_not_the_library(
    log_output: io.StringIO,
) -> None:
    """ライブラリの WARNING を止めても、失敗は例外(種別名つき)で呼び出し側に伝わる。"""
    with (
        adapters_on(RESPONSES["unavailable"]) as (adapters, _stub),
        pytest.raises(OpenSearchUnavailableError) as excinfo,
    ):
        adapters.repository.fetch(ID)

    assert excinfo.value.reason == "http_503"
    assert log_output.getvalue() == ""


# --- 404 の本文が JSON でない・壊れている場合(プロキシ・Ingress) ---
# 例外経路(`ignore` を使わない)なので、ライブラリは本文のデコードに失敗しても `TransportError`
# にする。削除の executor は `Rejected` を有限回で諦めるため、`SerializationError` のような
# 想定外の例外が素通りして無限に再試行することがあってはならない。


@pytest.mark.parametrize("response_name", ["html_404", "broken_json_404"])
def test_a_404_with_an_unreadable_body_is_a_rejection_for_the_writes(
    response_name: str, log_output: io.StringIO, emitted_records: list[logging.LogRecord]
) -> None:
    with adapters_on(RESPONSES[response_name]) as (adapters, _stub):
        outcomes = [
            adapters.repository.delete_if_unchanged(ID, seq_no=1, primary_term=1),
            adapters.store.delete(ID),
            adapters.repository.raise_last_seen_at(ID, INSTANT),
        ]

    assert outcomes == [Rejected("http_404")] * 3
    assert_nothing_logged_with_a_sentinel(log_output, emitted_records)


@pytest.mark.parametrize("response_name", ["html_404", "broken_json_404"])
@pytest.mark.parametrize(
    "fetch",
    [
        pytest.param(lambda adapters: adapters.repository.fetch(ID), id="repository.fetch"),
        pytest.param(
            lambda adapters: adapters.repository.fetch_for_deletion(ID),
            id="repository.fetch_for_deletion",
        ),
        pytest.param(lambda adapters: adapters.store.fetch("maintenance"), id="store.fetch"),
    ],
)
def test_a_404_with_an_unreadable_body_is_an_unexpected_response_for_the_fetches(
    response_name: str,
    fetch: Callable[[Adapters], object],
    log_output: io.StringIO,
    emitted_records: list[logging.LogRecord],
) -> None:
    with (
        adapters_on(RESPONSES[response_name]) as (adapters, _stub),
        pytest.raises(OpenSearchUnexpectedResponseError) as excinfo,
    ):
        fetch(adapters)

    assert excinfo.value.error_type == "http_404"
    assert_no_sentinel_in(excinfo.value)
    assert_nothing_logged_with_a_sentinel(log_output, emitted_records)


def test_a_401_is_unavailable_whatever_its_body(
    log_output: io.StringIO, emitted_records: list[logging.LogRecord]
) -> None:
    with (
        adapters_on(RESPONSES["unauthorized"]) as (adapters, _stub),
        pytest.raises(OpenSearchUnavailableError) as excinfo,
    ):
        adapters.repository.delete_if_unchanged(ID, seq_no=1, primary_term=1)

    assert excinfo.value.reason == "http_401"
    assert_no_sentinel_in(excinfo.value)
    assert_nothing_logged_with_a_sentinel(log_output, emitted_records)


def test_a_successful_delete_is_deleted_through_the_real_client() -> None:
    """404 の扱いを変えても、200 の削除は `Deleted` のまま(末尾が `NotFound` に固定されない)。"""
    with adapters_on(RESPONSES["ok_empty"]) as (adapters, _stub):
        assert adapters.repository.delete_if_unchanged(ID, seq_no=1, primary_term=1) == Deleted()
        assert adapters.store.delete(ID) == Deleted()
