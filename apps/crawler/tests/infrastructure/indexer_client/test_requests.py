"""リクエストの組み立て(indexer-api 3・4章。architecture 7.2・7.4・7.10)。

実際の `HttpIndexerClient` を、ローカルの HTTP サーバにつないで、送られたリクエストそのもの
(メソッド・パス・ヘッダ・本文)を確かめる。
"""

import base64
import json
import math
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from loreley_crawler.infrastructure.indexer_client import (
    FinishOutcome,
    HttpIndexerClient,
    IndexerClientConfig,
    Succeeded,
)
from loreley_crawler.infrastructure.indexer_client.payloads import encode_json
from tests.fakes.local_http_server import LocalServer, ReceivedRequest, Reply, local_http_server
from tests.infrastructure.indexer_client.support import (
    CONTENT_HASH,
    CRAWL_ID,
    CRAWL_STARTED_AT,
    LOCK,
    SOURCE_ID,
    make_document,
)

LOCK_JSON = {"owner": LOCK.owner, "job_id": LOCK.job_id}
STARTED_AT_JSON = "2026-11-13T01:02:03.456Z"


def respond_ok(request: ReceivedRequest) -> Reply:
    """どの API にも、契約どおりの成功の応答を返す。"""
    if request.path.endswith("/documents:batch"):
        return Reply(body={"results": []})
    if request.path.endswith("/last-seen"):
        return Reply(body={"results": []})
    if request.path.endswith("/deletions:discard"):
        return Reply(body={"discarded_crawl_ids": []})
    if request.path.endswith("/deletion-records"):
        return Reply(body={"deleted": True})
    if request.method == "DELETE":
        return Reply(body={"deleted_count": 0})
    if request.path.endswith("/finish"):
        return Reply(status=202, raw=b"")
    if request.method == "GET":
        return Reply(body={"crawl_id": CRAWL_ID, "source_id": SOURCE_ID, "status": "running"})
    return Reply(body={"crawl_id": CRAWL_ID, "status": "running"})


@pytest.fixture
def server() -> Iterator[LocalServer]:
    with local_http_server(respond_ok) as started:
        yield started


@pytest.fixture
def client(server: LocalServer) -> Iterator[HttpIndexerClient]:
    http_client = HttpIndexerClient(IndexerClientConfig(server.url))
    yield http_client
    http_client.close()


def only_request(server: LocalServer) -> ReceivedRequest:
    [request] = server.requests
    return request


def start(client: HttpIndexerClient, **overrides: Any) -> object:
    arguments: dict[str, Any] = {
        "crawl_id": CRAWL_ID,
        "source_id": SOURCE_ID,
        "crawl_started_at": CRAWL_STARTED_AT,
        "ttl": 86_400,
        "ratio_threshold": 0.3,
        "min_delete_count": 10,
        "force_delete": False,
        "rewrite_mode": False,
    }
    arguments.update(overrides)
    return client.start_crawl(**arguments)


# --- 開始通知 ---


def test_start_posts_the_settings_snapshot_as_strictly_typed_json(
    client: HttpIndexerClient, server: LocalServer
) -> None:
    assert start(client) == Succeeded()

    request = only_request(server)
    assert (request.method, request.path) == ("POST", "/crawls/start")
    assert request.headers["content-type"] == "application/json"
    assert request.json() == {
        "crawl_id": CRAWL_ID,
        "source_id": SOURCE_ID,
        "crawl_started_at": STARTED_AT_JSON,
        "ttl": 86_400,
        "ratio_threshold": 0.3,
        "min_delete_count": 10,
        "force_delete": False,
        "rewrite_mode": False,  # 省略せず、常に真偽値で送る
    }
    # JSON の型そのもの(`1` や `"true"` に変換されていない)。
    body = request.json()
    assert type(body["ttl"]) is int
    assert type(body["min_delete_count"]) is int
    assert type(body["ratio_threshold"]) is float
    assert type(body["force_delete"]) is bool
    assert type(body["rewrite_mode"]) is bool


def test_an_integer_ratio_threshold_is_sent_as_a_json_integer(
    client: HttpIndexerClient, server: LocalServer
) -> None:
    start(client, ratio_threshold=1, force_delete=True, rewrite_mode=True)

    body = only_request(server).json()
    assert body["ratio_threshold"] == 1
    assert type(body["ratio_threshold"]) is int
    assert (body["force_delete"], body["rewrite_mode"]) == (True, True)


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"ttl": True}, TypeError),  # bool は整数として送らない
        ({"ttl": 1.5}, TypeError),
        ({"ttl": "86400"}, TypeError),
        ({"min_delete_count": 2.0}, TypeError),
        ({"ratio_threshold": "0.3"}, TypeError),
        ({"ratio_threshold": True}, TypeError),
        ({"force_delete": 1}, TypeError),
        ({"rewrite_mode": "true"}, TypeError),
        ({"ratio_threshold": math.nan}, ValueError),
        ({"ratio_threshold": math.inf}, ValueError),
        ({"ratio_threshold": -math.inf}, ValueError),
    ],
)
def test_values_of_the_wrong_type_or_not_finite_are_never_sent(
    client: HttpIndexerClient, server: LocalServer, overrides: dict[str, Any], error: type
) -> None:
    with pytest.raises(error):
        start(client, **overrides)

    assert server.requests == []


def test_the_same_start_values_are_sent_identically_on_a_resend(
    client: HttpIndexerClient, server: LocalServer
) -> None:
    start(client)
    start(client)

    first, second = server.requests
    assert first.body == second.body


def test_timestamps_are_utc_millisecond_strings_whatever_the_zone_of_the_input(
    client: HttpIndexerClient, server: LocalServer
) -> None:
    jst = timezone(timedelta(hours=9))

    start(client, crawl_started_at=datetime(2026, 11, 13, 10, 2, 3, 456999, tzinfo=jst))

    assert only_request(server).json()["crawl_started_at"] == STARTED_AT_JSON


def test_a_naive_timestamp_is_rejected_before_sending(
    client: HttpIndexerClient, server: LocalServer
) -> None:
    with pytest.raises(ValueError, match="timezone"):
        start(client, crawl_started_at=datetime(2026, 11, 13, 1, 2, 3))

    assert server.requests == []


# --- パス(source_id・crawl_id のパーセントエンコード) ---

AWKWARD_SOURCE_ID = "a b/c?d#e%f日本"
ENCODED_SOURCE_ID = "a%20b%2Fc%3Fd%23e%25f%E6%97%A5%E6%9C%AC"


def test_source_id_and_crawl_id_are_percent_encoded_in_every_path(
    client: HttpIndexerClient, server: LocalServer
) -> None:
    client.report_last_seen(
        AWKWARD_SOURCE_ID, crawl_id=CRAWL_ID, crawl_started_at=CRAWL_STARTED_AT, lock=LOCK,
        document_ids=[],
    )  # fmt: skip
    client.register_documents(
        AWKWARD_SOURCE_ID, crawl_id=CRAWL_ID, crawl_started_at=CRAWL_STARTED_AT, lock=LOCK,
        documents=[make_document()],
    )  # fmt: skip
    client.discard_deletions(AWKWARD_SOURCE_ID, lock=LOCK)
    client.delete_documents(AWKWARD_SOURCE_ID, lock=LOCK)
    client.delete_deletion_records(AWKWARD_SOURCE_ID, lock=LOCK)
    client.finish_crawl(
        "job/1 2", source_id=SOURCE_ID, outcome=FinishOutcome.FAILED, finished_at=CRAWL_STARTED_AT
    )
    client.get_crawl_status("job/1 2")

    assert [(r.method, r.path) for r in server.requests] == [
        ("POST", f"/sources/{ENCODED_SOURCE_ID}/last-seen"),
        ("POST", f"/sources/{ENCODED_SOURCE_ID}/documents:batch"),
        ("POST", f"/sources/{ENCODED_SOURCE_ID}/deletions:discard"),
        ("DELETE", f"/sources/{ENCODED_SOURCE_ID}/documents"),
        ("DELETE", f"/sources/{ENCODED_SOURCE_ID}/deletion-records"),
        ("POST", "/crawls/job%2F1%202/finish"),
        ("GET", "/crawls/job%2F1%202"),
    ]


# --- last-seen ---


def test_last_seen_posts_the_ids_with_the_same_started_at_string_and_the_lock(
    client: HttpIndexerClient, server: LocalServer
) -> None:
    ids = [CONTENT_HASH, "7f2216b2a91e74fe53ce071ed0bd8dcebccaa904f9a8d8004f592b0a4210a9c5"]

    client.report_last_seen(
        SOURCE_ID, crawl_id=CRAWL_ID, crawl_started_at=CRAWL_STARTED_AT, lock=LOCK, document_ids=ids
    )

    request = only_request(server)
    assert (request.method, request.path) == ("POST", f"/sources/{SOURCE_ID}/last-seen")
    assert request.json() == {
        "crawl_id": CRAWL_ID,
        "lock": LOCK_JSON,
        "crawl_started_at": STARTED_AT_JSON,
        "document_ids": ids,
    }


# --- バッチ登録 ---


def register(client: HttpIndexerClient, *documents: Any) -> object:
    return client.register_documents(
        SOURCE_ID,
        crawl_id=CRAWL_ID,
        crawl_started_at=CRAWL_STARTED_AT,
        lock=LOCK,
        documents=documents,
    )


def test_a_batch_carries_the_documents_in_the_contract_shape(
    client: HttpIndexerClient, server: LocalServer
) -> None:
    register(client, make_document(url="https://wiki.example.com/p/1", path="guide/setup.md"))

    request = only_request(server)
    assert (request.method, request.path) == ("POST", f"/sources/{SOURCE_ID}/documents:batch")
    assert request.json() == {
        "crawl_id": CRAWL_ID,
        "crawl_started_at": STARTED_AT_JSON,
        "lock": LOCK_JSON,
        "documents": [
            {
                "external_id": "docs/setup.md",
                "title": "setup.md",
                "mime_type": "text/markdown",
                "raw_content": "aGVsbG8=",
                "content_hash": CONTENT_HASH,
                "source_updated_at": "2026-11-08T12:00:00.000Z",
                "size": 5,
                "url": "https://wiki.example.com/p/1",
                "path": "guide/setup.md",
            }
        ],
    }
    assert type(request.json()["documents"][0]["size"]) is int


def test_url_and_path_are_omitted_when_they_are_none(
    client: HttpIndexerClient, server: LocalServer
) -> None:
    register(client, make_document())

    document = only_request(server).json()["documents"][0]
    assert "url" not in document
    assert "path" not in document


@pytest.mark.parametrize(
    "raw_content",
    [
        b"",
        b"a",
        b"ab",
        b"abc",
        b"\xfb\xff\xbf" * 10,  # 標準の base64 は `+` と `/` を使う(URL セーフの `-`・`_` ではない)
        bytes(range(256)) * 4,  # 76 文字を超える長さ(MIME 形式なら改行が入る)
    ],
)
def test_raw_content_is_standard_base64_with_padding_and_without_newlines(
    client: HttpIndexerClient, server: LocalServer, raw_content: bytes
) -> None:
    register(client, make_document(raw_content=raw_content, size=len(raw_content)))

    encoded = only_request(server).json()["documents"][0]["raw_content"]
    assert encoded == base64.b64encode(raw_content).decode("ascii")
    assert "\n" not in encoded
    assert len(encoded) % 4 == 0
    assert base64.b64decode(encoded, validate=True) == raw_content


def test_the_url_safe_characters_never_appear_in_raw_content(
    client: HttpIndexerClient, server: LocalServer
) -> None:
    register(client, make_document(raw_content=b"\xfb\xff\xbf"))

    assert only_request(server).json()["documents"][0]["raw_content"] == "+/+/"


def test_a_title_with_a_lone_surrogate_is_sent_as_an_escape_not_a_crash(
    client: HttpIndexerClient, server: LocalServer
) -> None:
    # Indexer が文書単位で拒否する(`document_rejected`)。送る側が UTF-8 にできずに落ちない。
    register(client, make_document(title="bad\udc80name"))

    request = only_request(server)
    assert b"\\udc80" in request.body
    assert request.body.isascii()


@pytest.mark.parametrize("size", [True, 5.0, "5"])
def test_a_document_size_that_is_not_an_integer_is_never_sent(
    client: HttpIndexerClient, server: LocalServer, size: Any
) -> None:
    with pytest.raises(TypeError, match="size"):
        register(client, make_document(size=size))

    assert server.requests == []


def test_an_empty_batch_is_not_sent(client: HttpIndexerClient, server: LocalServer) -> None:
    with pytest.raises(ValueError, match="documents"):
        register(client)

    assert server.requests == []


# --- 終了通知 ---


def test_an_enumeration_completed_finish_carries_the_count_and_both_id_lists(
    client: HttpIndexerClient, server: LocalServer
) -> None:
    finished_at = datetime(2026, 11, 13, 1, 12, 30, tzinfo=UTC)

    reply = client.finish_crawl(
        CRAWL_ID,
        source_id=SOURCE_ID,
        outcome=FinishOutcome.ENUMERATION_COMPLETED,
        finished_at=finished_at,
        enumerated_count=1203,
        skipped_document_ids=[CONTENT_HASH],
        oversize_document_ids=[],
    )

    assert reply == Succeeded()  # 202(ボディなし)
    request = only_request(server)
    assert (request.method, request.path) == ("POST", f"/crawls/{CRAWL_ID}/finish")
    assert request.json() == {
        "source_id": SOURCE_ID,
        "outcome": "enumeration_completed",
        "finished_at": "2026-11-13T01:12:30.000Z",
        "enumerated_count": 1203,
        "skipped_document_ids": [CONTENT_HASH],
        "oversize_document_ids": [],
    }


@pytest.mark.parametrize("outcome", [FinishOutcome.FAILED, FinishOutcome.CANCELLED])
def test_a_failed_or_cancelled_finish_sends_only_the_outcome_source_and_time(
    client: HttpIndexerClient, server: LocalServer, outcome: FinishOutcome
) -> None:
    client.finish_crawl(
        CRAWL_ID, source_id=SOURCE_ID, outcome=outcome, finished_at=CRAWL_STARTED_AT
    )

    assert only_request(server).json() == {
        "source_id": SOURCE_ID,
        "outcome": outcome.value,
        "finished_at": STARTED_AT_JSON,
    }


@pytest.mark.parametrize(
    "missing",
    [
        {"enumerated_count": None},
        {"skipped_document_ids": None},
        {"oversize_document_ids": None},
    ],
)
def test_an_enumeration_completed_finish_without_the_counts_is_not_sent(
    client: HttpIndexerClient, server: LocalServer, missing: dict[str, None]
) -> None:
    arguments: dict[str, Any] = {
        "enumerated_count": 1,
        "skipped_document_ids": [],
        "oversize_document_ids": [],
        **missing,
    }

    with pytest.raises(ValueError, match="requires"):
        client.finish_crawl(
            CRAWL_ID,
            source_id=SOURCE_ID,
            outcome=FinishOutcome.ENUMERATION_COMPLETED,
            finished_at=CRAWL_STARTED_AT,
            **arguments,
        )

    assert server.requests == []


@pytest.mark.parametrize("enumerated_count", [True, 1.5, "2", 2.0])
def test_an_enumerated_count_that_is_not_an_integer_is_never_sent(
    client: HttpIndexerClient, server: LocalServer, enumerated_count: Any
) -> None:
    with pytest.raises(TypeError, match="enumerated_count"):
        client.finish_crawl(
            CRAWL_ID,
            source_id=SOURCE_ID,
            outcome=FinishOutcome.ENUMERATION_COMPLETED,
            finished_at=CRAWL_STARTED_AT,
            enumerated_count=enumerated_count,
            skipped_document_ids=[],
            oversize_document_ids=[],
        )

    assert server.requests == []


@pytest.mark.parametrize("outcome", [FinishOutcome.FAILED, FinishOutcome.CANCELLED])
def test_a_failed_or_cancelled_finish_sends_the_counts_and_lists_when_they_are_given(
    client: HttpIndexerClient, server: LocalServer, outcome: FinishOutcome
) -> None:
    client.finish_crawl(
        CRAWL_ID,
        source_id=SOURCE_ID,
        outcome=outcome,
        finished_at=CRAWL_STARTED_AT,
        enumerated_count=7,
        skipped_document_ids=[CONTENT_HASH],
        oversize_document_ids=[],
    )

    assert only_request(server).json() == {
        "source_id": SOURCE_ID,
        "outcome": outcome.value,
        "finished_at": STARTED_AT_JSON,
        "enumerated_count": 7,
        "skipped_document_ids": [CONTENT_HASH],
        "oversize_document_ids": [],
    }


def test_the_finish_content_is_the_same_on_every_send(
    client: HttpIndexerClient, server: LocalServer
) -> None:
    for _ in range(2):
        client.finish_crawl(
            CRAWL_ID,
            source_id=SOURCE_ID,
            outcome=FinishOutcome.ENUMERATION_COMPLETED,
            finished_at=CRAWL_STARTED_AT,
            enumerated_count=2,
            skipped_document_ids=[CONTENT_HASH],
            oversize_document_ids=[],
        )

    first, second = server.requests
    assert first.body == second.body


# --- Status ---


def test_status_is_a_get_without_a_body(client: HttpIndexerClient, server: LocalServer) -> None:
    client.get_crawl_status(CRAWL_ID)

    request = only_request(server)
    assert (request.method, request.path, request.body) == ("GET", f"/crawls/{CRAWL_ID}", b"")


# --- ソース削除 1〜3(DELETE のボディ。architecture 12章 #17) ---


@pytest.mark.parametrize(
    ("call", "path"),
    [
        (lambda c: c.delete_documents(SOURCE_ID, lock=LOCK), f"/sources/{SOURCE_ID}/documents"),
        (
            lambda c: c.delete_deletion_records(SOURCE_ID, lock=LOCK),
            f"/sources/{SOURCE_ID}/deletion-records",
        ),
    ],
    ids=["documents", "deletion-records"],
)
def test_delete_requests_carry_the_lock_as_a_json_body(
    client: HttpIndexerClient, server: LocalServer, call: Any, path: str
) -> None:
    call(client)

    request = only_request(server)
    assert (request.method, request.path) == ("DELETE", path)
    assert request.headers["content-type"] == "application/json"
    assert int(request.headers["content-length"]) == len(request.body)
    assert json.loads(request.body) == {"lock": LOCK_JSON}


def test_discard_posts_the_lock_and_the_reason(
    client: HttpIndexerClient, server: LocalServer
) -> None:
    client.discard_deletions(SOURCE_ID, lock=LOCK)

    request = only_request(server)
    assert (request.method, request.path) == ("POST", f"/sources/{SOURCE_ID}/deletions:discard")
    assert request.json() == {"lock": LOCK_JSON, "reason": "source_deleted"}


# --- JSON の符号化(`NaN`・`Infinity` を送らない) ---


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_json_encoding_refuses_values_that_are_not_json(value: float) -> None:
    with pytest.raises(ValueError, match="JSON"):
        encode_json({"ratio_threshold": value})


def test_json_encoding_is_compact_ascii_with_true_booleans_and_integers() -> None:
    assert encode_json({"a": 1, "b": True, "c": 0.5, "d": "日本"}) == (
        b'{"a":1,"b":true,"c":0.5,"d":"\\u65e5\\u672c"}'
    )
