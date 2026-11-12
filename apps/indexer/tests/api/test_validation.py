"""入力の形式検証(strict)と、入力サイズの防御(api 3.4、4.1〜4.8、plan 案 7・14・22、D-94)。

ドメインの代役(呼ばれたかを記録する)に対して、不正なリクエストが
- 400 `invalid_request` の共通エラー形式になること
- どの入口(ドメイン)も呼ばないこと
- 応答に入力値(センチネル文字列)が一切出ないこと(位置と型だけ。R9)
を確かめる。
"""

import asyncio
import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from loreley_indexer.api import raw_content
from loreley_indexer.api.errors import InvalidRequestError
from loreley_indexer.api.request_body import read_limited_body
from tests.api.factories import (
    BATCH_PATH,
    DELETE_DOCUMENTS_PATH,
    DELETE_RECORDS_PATH,
    DISCARD_PATH,
    FINISH_PATH,
    LAST_SEEN_PATH,
    MAX_BATCH_DOCUMENTS,
    MAX_LAST_SEEN_IDS,
    MAX_RAW_BYTES,
    MAX_REQUEST_BODY_BYTES,
    START_PATH,
    STATUS_PATH,
    batch_json,
    document_json,
    encode,
    finish_json,
    last_seen_json,
    lock_json,
    locked_json,
    start_json,
)
from tests.api.stubs import StubDependencies, make_api_config, stub_client
from tests.crawl_runs.factories import hex_id

SENTINEL = "SENTINEL-INPUT-VALUE"
LONE_SURROGATE = "\ud800"


@pytest.fixture
def stubs() -> StubDependencies:
    return StubDependencies()


@pytest.fixture
def client(stubs: StubDependencies) -> Iterator[TestClient]:
    with stub_client(stubs) as test_client:
        yield test_client


def send_raw(client: TestClient, method: str, path: str, body: bytes) -> Any:
    """`json=` を使わずに送る(NaN やサロゲートのエスケープなど、クライアントが拒む形も送るため)。"""
    return client.request(method, path, content=body, headers={"content-type": "application/json"})


def send_json(client: TestClient, method: str, path: str, body: object) -> Any:
    # `json.dumps` は NaN・Infinity をそのまま書き、孤立サロゲートは `\ud800` と書く。
    return send_raw(client, method, path, json.dumps(body).encode("ascii"))


def assert_rejected(response: Any, stubs: StubDependencies) -> dict[str, Any]:
    assert response.status_code == 400, response.text
    body = response.json()
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    assert set(error) == {"code", "message", "retryable"}
    assert (error["code"], error["retryable"]) == ("invalid_request", False)
    assert stubs.calls() == []
    assert SENTINEL not in response.text
    return error


START = ("POST", START_PATH)
FINISH = ("POST", FINISH_PATH)
BATCH = ("POST", BATCH_PATH)
LAST_SEEN = ("POST", LAST_SEEN_PATH)
DISCARD = ("POST", DISCARD_PATH)
DELETE_DOCS = ("DELETE", DELETE_DOCUMENTS_PATH)
DELETE_RECORDS = ("DELETE", DELETE_RECORDS_PATH)


def without(body: dict[str, Any], name: str) -> dict[str, Any]:
    return {key: value for key, value in body.items() if key != name}


# (エンドポイント, 不正な本文, 応答の message に含まれるべき位置と型)。
INVALID_REQUESTS = [
    # --- 開始通知: 数値・真偽値は strict(D-94(f)、案 14) ---
    pytest.param(START, start_json(ttl=1.5), "ttl (int_type)", id="start-ttl-fraction"),
    pytest.param(START, start_json(ttl=1.0), "ttl (int_type)", id="start-ttl-integral-float"),
    pytest.param(START, start_json(ttl="86400"), "ttl (int_type)", id="start-ttl-string"),
    pytest.param(START, start_json(ttl=True), "ttl (int_type)", id="start-ttl-bool"),
    pytest.param(START, start_json(ttl=None), "ttl (int_type)", id="start-ttl-null"),
    pytest.param(START, start_json(ttl=2**63), "ttl (less_than_equal)", id="start-ttl-over-int64"),
    pytest.param(START, start_json(ratio_threshold="0.2"), "ratio_threshold", id="start-ratio-str"),
    pytest.param(START, start_json(ratio_threshold=True), "ratio_threshold", id="start-ratio-bool"),
    pytest.param(
        START, start_json(ratio_threshold=float("nan")), "not valid JSON", id="start-ratio-nan"
    ),
    pytest.param(
        START, start_json(ratio_threshold=float("inf")), "not valid JSON", id="start-ratio-inf"
    ),
    pytest.param(START, start_json(min_delete_count=1.5), "min_delete_count", id="start-min-float"),
    pytest.param(START, start_json(min_delete_count="10"), "min_delete_count", id="start-min-str"),
    pytest.param(START, start_json(force_delete="true"), "force_delete", id="start-force-str"),
    pytest.param(START, start_json(force_delete=1), "force_delete", id="start-force-int"),
    pytest.param(START, start_json(rewrite_mode="true"), "rewrite_mode", id="start-rewrite-str"),
    pytest.param(START, start_json(rewrite_mode=1), "rewrite_mode", id="start-rewrite-one"),
    pytest.param(START, start_json(rewrite_mode=0), "rewrite_mode", id="start-rewrite-zero"),
    pytest.param(START, start_json(rewrite_mode=None), "rewrite_mode", id="start-rewrite-null"),
    # --- 必須項目の欠落 ---
    *[
        pytest.param(
            START,
            without(start_json(), missing),
            f"{missing} (missing)",
            id=f"start-missing-{missing}",
        )
        for missing in (
            "crawl_id",
            "source_id",
            "crawl_started_at",
            "ttl",
            "ratio_threshold",
            "min_delete_count",
        )
    ],
    # --- 日時: ISO 8601 でタイムゾーン必須 ---
    pytest.param(
        START, start_json(crawl_started_at="2026-11-09T01:00:00"), "crawl_started_at", id="no-tz"
    ),
    pytest.param(START, start_json(crawl_started_at="2026-11-09"), "crawl_started_at", id="date"),
    pytest.param(START, start_json(crawl_started_at=1731114000), "crawl_started_at", id="epoch"),
    pytest.param(START, start_json(crawl_started_at=SENTINEL), "crawl_started_at", id="garbage"),
    pytest.param(START, start_json(crawl_started_at=None), "crawl_started_at", id="null-time"),
    pytest.param(
        START,
        start_json(crawl_started_at="9999-12-31T23:59:59-05:00"),
        "crawl_started_at (timestamp_invalid)",
        id="overflow-after-utc-conversion",
    ),
    # --- ID 類: 空文字・NUL・長さ・孤立サロゲート ---
    pytest.param(START, start_json(crawl_id=""), "crawl_id (id_empty)", id="crawl-id-empty"),
    pytest.param(
        START, start_json(source_id="a\x00b"), "source_id (id_invalid_character)", id="source-nul"
    ),
    pytest.param(
        START,
        start_json(source_id=SENTINEL + "x" * 300),
        "source_id (id_too_long)",
        id="source-long",
    ),
    pytest.param(
        START,
        start_json(crawl_id=SENTINEL + "あ" * 100),
        "crawl_id (id_too_long)",
        id="id-too-long-in-bytes",
    ),
    pytest.param(START, start_json(crawl_id=LONE_SURROGATE), "crawl_id", id="crawl-id-surrogate"),
    pytest.param(START, start_json(source_id=LONE_SURROGATE), "source_id", id="source-surrogate"),
    pytest.param(START, start_json(crawl_id=123), "crawl_id (string_type)", id="crawl-id-int"),
    # --- 終了通知 ---
    pytest.param(FINISH, finish_json(outcome="bogus"), "outcome (literal_error)", id="fin-outcome"),
    pytest.param(FINISH, finish_json(outcome=None), "outcome", id="fin-outcome-null"),
    pytest.param(FINISH, finish_json(enumerated_count=-1), "enumerated_count", id="fin-count-neg"),
    pytest.param(
        FINISH, finish_json(enumerated_count=1.5), "enumerated_count", id="fin-count-float"
    ),
    pytest.param(FINISH, finish_json(skipped_count="2"), "skipped_count", id="fin-skipped-count"),
    pytest.param(
        FINISH, finish_json(skipped_document_ids=["ABC"]), "skipped_document_ids.0", id="fin-id"
    ),
    pytest.param(FINISH, finish_json(oversize_document_ids=["A" * 64]), "oversize", id="fin-upper"),
    pytest.param(
        FINISH, finish_json(skipped_document_ids="x"), "skipped_document_ids", id="fin-str"
    ),
    pytest.param(FINISH, finish_json(finished_at=None), "finished_at", id="fin-finished-null"),
    pytest.param(
        FINISH, finish_json(finished_at="2026-11-09T01:12"), "finished_at", id="fin-no-tz"
    ),
    pytest.param(FINISH, finish_json(source_id=""), "source_id (id_empty)", id="fin-source-empty"),
    pytest.param(
        FINISH,
        without(finish_json(), "finished_at"),
        "finished_at (missing)",
        id="fin-missing-finished-at",
    ),
    pytest.param(
        FINISH,
        without(finish_json(), "enumerated_count"),
        "body (required_when_enumeration_completed)",
        id="fin-missing-enumerated-count",
    ),
    # --- バッチ登録(本文の形式) ---
    pytest.param(BATCH, batch_json([]), "documents must not be empty", id="batch-empty"),
    pytest.param(
        BATCH,
        batch_json([document_json(f"d{n}") for n in range(MAX_BATCH_DOCUMENTS + 1)]),
        "documents has too many items",
        id="batch-too-many",
    ),
    pytest.param(
        BATCH,
        without(batch_json(), "documents"),
        "documents (missing)",
        id="batch-missing-documents",
    ),
    pytest.param(BATCH, batch_json(documents=[None]), "documents.0", id="batch-doc-null"),
    pytest.param(BATCH, batch_json(documents="x"), "documents", id="batch-docs-str"),
    pytest.param(BATCH, batch_json(lock=None), "lock", id="batch-lock-null"),
    pytest.param(
        BATCH, batch_json(lock=lock_json(owner="")), "lock.owner (id_empty)", id="batch-owner-empty"
    ),
    pytest.param(
        BATCH, batch_json(lock=lock_json(owner=LONE_SURROGATE)), "lock.owner", id="batch-owner-sur"
    ),
    pytest.param(
        BATCH, batch_json(lock=lock_json(job_id=LONE_SURROGATE)), "lock.job_id", id="batch-job-sur"
    ),
    pytest.param(
        BATCH, batch_json(crawl_id=LONE_SURROGATE), "crawl_id", id="batch-crawl-id-surrogate"
    ),
    pytest.param(
        BATCH,
        without(batch_json(), "crawl_started_at"),
        "crawl_started_at (missing)",
        id="batch-missing-crawl-started-at",
    ),
    pytest.param(
        BATCH, without(batch_json(), "crawl_id"), "crawl_id (missing)", id="batch-missing-crawl-id"
    ),
    # --- バッチ登録(文書の項目) ---
    *[
        pytest.param(
            BATCH,
            batch_json([document_json(**{field: value})]),
            f"documents.0.{field}",
            id=f"doc-{field}-{label}",
        )
        for field, value, label in [
            ("external_id", "", "empty"),
            ("external_id", LONE_SURROGATE, "surrogate"),
            ("external_id", "x" * 4097, "too-long"),
            ("external_id", 5, "int"),
            ("title", 5, "int"),
            ("title", None, "null"),
            ("mime_type", None, "null"),
            ("url", 5, "int"),
            ("path", [], "list"),
            ("content_hash", "A" * 64, "upper"),
            ("content_hash", "a" * 63, "short"),
            ("content_hash", "a" * 64 + "\n", "trailing-newline"),
            ("content_hash", LONE_SURROGATE, "surrogate"),
            ("content_hash", 5, "int"),
            ("size", -1, "negative"),
            ("size", 1.5, "float"),
            ("size", "5", "str"),
            ("size", True, "bool"),
            ("source_updated_at", "2026-11-08T12:00:00", "no-tz"),
            ("source_updated_at", 0, "int"),
            ("raw_content", 5, "int"),
            ("raw_content", LONE_SURROGATE * 4, "surrogate"),
        ]
    ],
    *[
        pytest.param(
            BATCH,
            batch_json([without(document_json(), missing)]),
            f"documents.0.{missing} (missing)",
            id=f"doc-missing-{missing}",
        )
        for missing in (
            "external_id",
            "title",
            "mime_type",
            "raw_content",
            "content_hash",
            "source_updated_at",
            "size",
        )
    ],
    pytest.param(
        BATCH,
        batch_json([document_json("a\x00b")]),
        "documents.0.external_id (id_invalid_character)",
        id="doc-external_id-nul",
    ),
    pytest.param(
        BATCH,
        batch_json([document_json(raw_content="abc")]),
        "documents.0.raw_content (base64_invalid)",
        id="base64-bad-length",
    ),
    pytest.param(
        BATCH,
        batch_json([document_json(raw_content="!!!!")]),
        "documents.0.raw_content (base64_invalid)",
        id="base64-bad-alphabet",
    ),
    pytest.param(
        BATCH,
        batch_json([document_json(), document_json("b", raw_content="aGVsbG8")]),
        "documents.1.raw_content (base64_invalid)",
        id="base64-unpadded-second-document",
    ),
    *[
        pytest.param(
            BATCH,
            batch_json([document_json(raw_content=raw_content)]),
            "documents.0.raw_content (base64_invalid)",
            id=f"base64-{label}",
        )
        for label, raw_content in [
            ("newline-bad-length", "aGVs\nbG8="),  # 9 文字
            ("newline-valid-length", "aGVs\nG8="),  # 8 文字(文字種で拒否される)
            ("crlf", "aGVs\r\nbG8="),
            ("only-padding", "===="),
            ("non-ascii", "aGVsbG8é"),
            ("url-safe-alphabet", "a-_b"),
            ("data-after-padding", "YQ==YQ=="),
            ("padding-in-the-middle", "aG=sbG8="),
            ("space", "aGVs bG8="),
            ("only-three-padding", "A==="),
        ]
    ],
    # --- last-seen ---
    pytest.param(
        LAST_SEEN,
        last_seen_json(["A" * 64]),
        "document_ids.0 (string_pattern_mismatch)",
        id="ls-upper",
    ),
    pytest.param(LAST_SEEN, last_seen_json([hex_id(1)[:-1]]), "document_ids.0", id="ls-short"),
    pytest.param(LAST_SEEN, last_seen_json([hex_id(1) + "\n"]), "document_ids.0", id="ls-newline"),
    pytest.param(LAST_SEEN, last_seen_json([5]), "document_ids.0", id="ls-int"),
    pytest.param(LAST_SEEN, last_seen_json("x"), "document_ids", id="ls-str"),
    pytest.param(
        LAST_SEEN,
        last_seen_json([hex_id(n) for n in range(MAX_LAST_SEEN_IDS + 1)]),
        "document_ids has too many items",
        id="ls-too-many",
    ),
    pytest.param(
        LAST_SEEN,
        without(last_seen_json([]), "document_ids"),
        "document_ids (missing)",
        id="ls-missing-ids",
    ),
    pytest.param(LAST_SEEN, last_seen_json([], lock=None), "lock", id="ls-lock-null"),
    pytest.param(
        LAST_SEEN, last_seen_json([], crawl_started_at="x"), "crawl_started_at", id="ls-time"
    ),
    # --- ソース削除 1〜3 ---
    pytest.param(DISCARD, {}, "lock (missing)", id="discard-no-lock"),
    pytest.param(
        DISCARD, locked_json(reason="other"), "reason (literal_error)", id="discard-reason"
    ),
    pytest.param(DISCARD, locked_json(lock=lock_json(owner=5)), "lock.owner", id="discard-owner"),
    pytest.param(DELETE_DOCS, {}, "lock (missing)", id="delete-docs-no-lock"),
    pytest.param(DELETE_DOCS, locked_json(lock="x"), "lock", id="delete-docs-lock-str"),
    pytest.param(DELETE_RECORDS, {}, "lock (missing)", id="delete-records-no-lock"),
    pytest.param(
        DELETE_RECORDS, locked_json(lock=lock_json(job_id="")), "lock.job_id", id="delete-job-id"
    ),
]


@pytest.mark.parametrize(("endpoint", "body", "expected"), INVALID_REQUESTS)
def test_an_invalid_request_is_a_400_that_reports_only_the_location_and_type(
    client: TestClient,
    stubs: StubDependencies,
    endpoint: tuple[str, str],
    body: dict[str, Any],
    expected: str,
) -> None:
    method, path = endpoint

    response = send_json(client, method, path, body)

    error = assert_rejected(response, stubs)
    assert expected in error["message"]


# --- 本文そのものの不正 ---


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"not json", id="text"),
        pytest.param(b'{"a": ', id="truncated"),
        pytest.param(b"[]", id="array"),
        pytest.param(b'"string"', id="string"),
        pytest.param(b"123", id="number"),
        pytest.param(b"null", id="null"),
        pytest.param(b"\xff\xfe\x00", id="invalid-utf8"),
        pytest.param(b'{"ttl": NaN}', id="nan"),  # JSON の定数ではない
        pytest.param(b'{"ttl": Infinity}', id="infinity"),
        pytest.param(b'{"ttl": -Infinity}', id="negative-infinity"),
        pytest.param(b"[" * 200_000, id="deeply-nested"),
    ],
)
@pytest.mark.parametrize("endpoint", [START, FINISH, BATCH, LAST_SEEN, DISCARD, DELETE_DOCS])
def test_a_body_that_is_not_a_json_object_is_a_400(
    client: TestClient, stubs: StubDependencies, endpoint: tuple[str, str], body: bytes
) -> None:
    method, path = endpoint

    response = send_raw(client, method, path, body)

    assert_rejected(response, stubs)


@pytest.mark.parametrize(
    ("literal", "expected"),
    [
        (b"NaN", "not valid JSON"),  # JSON の定数ではない
        (b"Infinity", "not valid JSON"),
        (b"-Infinity", "not valid JSON"),
        (b"1e999", "ratio_threshold (finite_number)"),  # 数値の書式だが、Python で無限大になる
        (b"-1e999", "ratio_threshold (finite_number)"),
    ],
)
def test_non_finite_numbers_in_the_json_text_are_rejected_in_every_form(
    client: TestClient, stubs: StubDependencies, literal: bytes, expected: str
) -> None:
    template = b'{"crawl_id":"c","source_id":"s","crawl_started_at":"2026-11-09T01:00:00Z",'
    body = template + b'"ttl":1,"ratio_threshold":' + literal + b',"min_delete_count":1}'

    response = send_raw(client, "POST", START_PATH, body)

    assert expected in assert_rejected(response, stubs)["message"]


def test_a_cesu8_encoded_lone_surrogate_in_the_raw_body_is_a_400(
    client: TestClient, stubs: StubDependencies
) -> None:
    """UTF-8 では孤立サロゲートを表せない(CESU-8 の `ED A0 80` は不正な UTF-8)。"""
    body = b'{"crawl_id":"\xed\xa0\x80"}'

    assert_rejected(send_raw(client, "POST", START_PATH, body), stubs)


# --- パスの ID ---


PATH_CASES = [
    pytest.param("POST", "/crawls/{}/finish", finish_json(), id="finish"),
    pytest.param("GET", "/crawls/{}", None, id="status"),
    pytest.param("POST", "/sources/{}/documents:batch", batch_json(), id="batch"),
    pytest.param("POST", "/sources/{}/last-seen", last_seen_json([]), id="last-seen"),
    pytest.param("POST", "/sources/{}/deletions:discard", locked_json(), id="discard"),
    pytest.param("DELETE", "/sources/{}/documents", locked_json(), id="delete-documents"),
    pytest.param("DELETE", "/sources/{}/deletion-records", locked_json(), id="delete-records"),
]


@pytest.mark.parametrize(("method", "template", "body"), PATH_CASES)
@pytest.mark.parametrize(
    ("segment", "expected"),
    [
        pytest.param("a" * 300, "id_too_long", id="too-long"),
        pytest.param("a%00b", "id_invalid_character", id="nul"),
        pytest.param("%E3%81%82" * 100, "id_too_long", id="too-long-in-bytes"),  # 300 バイト
    ],
)
def test_a_path_id_that_is_too_long_or_has_nul_is_a_400(
    client: TestClient,
    stubs: StubDependencies,
    method: str,
    template: str,
    body: dict[str, Any] | None,
    segment: str,
    expected: str,
) -> None:
    response = client.request(method, template.format(segment), json=body)

    error = assert_rejected(response, stubs)
    assert expected in error["message"]


# --- サイズの防御(plan 案 22、U-3、API-U-17) ---


def test_a_declared_content_length_over_the_limit_is_rejected_before_reading_the_body(
    client: TestClient, stubs: StubDependencies
) -> None:
    response = client.post(
        START_PATH, content=b"{}", headers={"content-length": str(MAX_REQUEST_BODY_BYTES + 1)}
    )

    error = assert_rejected(response, stubs)
    assert error["message"] == "the request body is too large"


@pytest.mark.parametrize(
    "content_length",
    [
        pytest.param(b"-5", id="negative"),
        pytest.param(b"+5", id="plus-sign"),
        pytest.param(b"", id="empty"),
        pytest.param(b" 5", id="leading-space"),
        pytest.param(b"5 ", id="trailing-space"),
        pytest.param(b"1e3", id="exponent"),
        pytest.param(b"0x10", id="hex"),
        pytest.param(b"1_0", id="underscore"),
        pytest.param(b"5.0", id="fraction"),
        # ASCII 以外の数字(UTF-8 で送られ、サーバは latin-1 で読むので別の文字になる)。
        # `isdigit()` が真になる上付き文字は、テストのクライアントが UTF-8 に変えてしまうので、
        # 下の `read_limited_body` の直接のテストで確かめる。
        pytest.param("١٢".encode(), id="arabic-indic-digits"),
        pytest.param("\uff11\uff12".encode(), id="fullwidth-digits"),
    ],
)
def test_a_content_length_that_is_not_a_plain_number_is_a_400_with_its_own_message(
    client: TestClient, stubs: StubDependencies, content_length: bytes
) -> None:
    response = client.post(START_PATH, content=b"{}", headers={"content-length": content_length})

    error = assert_rejected(response, stubs)
    assert error["message"] == "the Content-Length header is invalid"


@pytest.mark.parametrize("digits", [21, 100, 5000])
def test_a_content_length_with_too_many_digits_is_a_too_large_400_not_a_conversion_failure(
    client: TestClient, stubs: StubDependencies, digits: int
) -> None:
    """4300 桁を超える数は `int()` が ValueError になる(Python の桁数制限)。変換の前に弾く。"""
    response = client.post(START_PATH, content=b"{}", headers={"content-length": b"9" * digits})

    error = assert_rejected(response, stubs)
    assert error["message"] == "the request body is too large"


def test_a_content_length_padded_with_zeros_is_too_large_even_if_its_value_is_small(
    client: TestClient, stubs: StubDependencies
) -> None:
    """「20 桁を超えれば過大」は桁数だけで判定する仕様。先頭のゼロ埋めは数値としては 2 だが、
    過大の 400 になる(実際のクライアントは先頭にゼロを付けないので、実害はない)。
    """
    response = client.post(START_PATH, content=b"{}", headers={"content-length": b"0" * 24 + b"2"})

    error = assert_rejected(response, stubs)
    assert error["message"] == "the request body is too large"


@pytest.mark.parametrize("content_length", [b"\xb2", b"\xb3", b"\xb9", b"1\xb2"])
def test_a_content_length_of_latin1_digits_is_rejected_without_converting_it_to_an_integer(
    content_length: bytes,
) -> None:
    """`isdigit()` は上付き文字(`²` など)で真になるが `int()` は失敗する(500 になる)。

    `isascii()` の検査で防ぐ。サーバは `Content-Length` を latin-1 で読むので、1 バイトの
    `0xb2` がこの文字になる(テストのクライアントは UTF-8 に変えるので、リーダーを直接呼ぶ)。
    """

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"{}", "more_body": False}

    request = Request(
        {"type": "http", "method": "POST", "headers": [(b"content-length", content_length)]},
        receive,
    )

    with pytest.raises(InvalidRequestError, match="the Content-Length header is invalid"):
        asyncio.run(read_limited_body(request, max_bytes=100))


def test_a_streamed_body_over_the_limit_without_content_length_is_a_400(
    client: TestClient, stubs: StubDependencies
) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(MAX_REQUEST_BODY_BYTES // 1024 + 2):
            yield b" " * 1024

    response = client.post(START_PATH, content=chunks())

    error = assert_rejected(response, stubs)
    assert error["message"] == "the request body is too large"


def test_a_body_at_the_limit_is_read_and_judged_by_its_content(
    client: TestClient, stubs: StubDependencies
) -> None:
    padding = b" " * (MAX_REQUEST_BODY_BYTES - 2)

    response = send_raw(client, "POST", START_PATH, b"{" + padding + b"}")

    error = assert_rejected(response, stubs)
    assert "missing" in error["message"]  # サイズでは拒否されず、必須項目の欠落で 400


def test_the_total_decoded_size_over_the_limit_is_a_400_before_any_document_is_decoded(
    client: TestClient, stubs: StubDependencies, monkeypatch: pytest.MonkeyPatch
) -> None:
    decode = MagicMock(wraps=raw_content.decode_base64)
    monkeypatch.setattr(raw_content, "decode_base64", decode)
    # 1 件ごとは上限(1,024 バイト)以内だが、3 件の合計(3,000 バイト)が合計の上限(2,048)を超える。
    documents = [document_json(f"d{n}", text="x" * 1000) for n in range(3)]

    response = send_json(client, "POST", BATCH_PATH, batch_json(documents))

    error = assert_rejected(response, stubs)
    assert error["message"] == "the documents are too large in total"
    decode.assert_not_called()


def test_a_huge_base64_is_never_decoded_and_reaches_the_domain_as_an_oversize_marker(
    stubs: StubDependencies, monkeypatch: pytest.MonkeyPatch
) -> None:
    decode = MagicMock(wraps=raw_content.decode_base64)
    monkeypatch.setattr(raw_content, "decode_base64", decode)
    # 10 MiB 相当の base64。原本の上限(1,024 バイト)を大きく超える。デコードしないので、
    # バッチ合計の上限(2,048 バイト)には数えず、リクエストボディの上限だけを大きくする。
    huge = "A" * (10 * 1024 * 1024 // 3 * 4)
    config = make_api_config(max_request_body_bytes=20 * 2**20)
    small = document_json("small")

    with stub_client(stubs, config) as client:
        response = send_json(
            client, "POST", BATCH_PATH, batch_json([document_json("big", raw_content=huge), small])
        )

    assert response.status_code == 200
    [call] = stubs.registrar.register.call_args_list
    big_input, small_input = call.args[1]
    assert big_input.raw_content == b""
    assert big_input.size == len(huge) // 4 * 3  # 申告の `size`(小さい)ではなく、推定したサイズ
    assert big_input.size > MAX_RAW_BYTES
    assert small_input.raw_content == b"hello\nworld\n"  # 上限以内の文書はデコードされる
    assert [c.args[0] for c in decode.call_args_list] == [small["raw_content"]]


def test_an_oversize_document_keeps_a_larger_declared_size(stubs: StubDependencies) -> None:
    big = document_json("big", text="x" * 2000, size=5_000_000)

    with stub_client(stubs, make_api_config(max_batch_bytes=10_000)) as client:
        send_json(client, "POST", BATCH_PATH, batch_json([big]))

    [call] = stubs.registrar.register.call_args_list
    [big_input] = call.args[1]
    assert (big_input.raw_content, big_input.size) == (b"", 5_000_000)


def test_a_document_exactly_at_the_raw_limit_is_decoded_and_keeps_its_declared_size(
    stubs: StubDependencies,
) -> None:
    exactly = document_json("exact", text="x" * MAX_RAW_BYTES)

    with stub_client(stubs) as client:
        send_json(client, "POST", BATCH_PATH, batch_json([exactly]))

    [call] = stubs.registrar.register.call_args_list
    [exact_input] = call.args[1]
    assert exact_input.raw_content == b"x" * MAX_RAW_BYTES
    assert exact_input.size == MAX_RAW_BYTES


def test_the_total_size_limit_accepts_the_boundary_value(stubs: StubDependencies) -> None:
    documents = [document_json(f"d{n}", text="x" * 500) for n in range(MAX_BATCH_DOCUMENTS)]

    with stub_client(stubs, make_api_config(max_batch_bytes=1500)) as client:  # 500 x 3
        assert send_json(client, "POST", BATCH_PATH, batch_json(documents)).status_code == 200
    with stub_client(StubDependencies(), make_api_config(max_batch_bytes=1499)) as client:
        assert send_json(client, "POST", BATCH_PATH, batch_json(documents)).status_code == 400


def test_documents_exactly_at_the_raw_limit_count_toward_the_batch_total(
    stubs: StubDependencies,
) -> None:
    """原本の上限ちょうどの文書はデコードされる(合計に数える)。上限超過の文書だけが数えない対象。"""
    documents = [document_json(f"d{n}", text="x" * MAX_RAW_BYTES) for n in range(2)]

    with stub_client(stubs, make_api_config(max_batch_bytes=2 * MAX_RAW_BYTES)) as client:
        assert send_json(client, "POST", BATCH_PATH, batch_json(documents)).status_code == 200
    with stub_client(
        StubDependencies(), make_api_config(max_batch_bytes=2 * MAX_RAW_BYTES - 1)
    ) as client:
        response = send_json(client, "POST", BATCH_PATH, batch_json(documents))
        assert response.status_code == 400
        assert response.json()["error"]["message"] == "the documents are too large in total"


def test_last_seen_accepts_the_maximum_number_of_ids(stubs: StubDependencies) -> None:
    ids = [hex_id(n) for n in range(MAX_LAST_SEEN_IDS)]

    with stub_client(stubs) as client:
        response = send_json(client, "POST", LAST_SEEN_PATH, last_seen_json(ids))

    assert response.status_code == 200
    assert stubs.last_seen.update.call_args.args[1] == ids


# --- 正例(寛容に受け入れる値。strict が行き過ぎていないこと) ---


@pytest.mark.parametrize(
    "overrides",
    [
        {"crawl_started_at": "2026-11-09T01:00:00Z"},
        {"crawl_started_at": "2026-11-09T01:00:00.123456Z"},
        {"crawl_started_at": "2026-11-09T10:00:00+09:00"},
        {"ratio_threshold": 1},
        {"ratio_threshold": -0.5},  # 範囲は検証しない(確定事項。arch 9.13(9))
        {"ttl": 0},
        {"ttl": -1},
        {"min_delete_count": -1},
        {"ttl": 2**63 - 1},
        {"rewrite_mode": True, "force_delete": True},
        {"extra_unknown_field": {"anything": [1, 2]}},
    ],
)
def test_a_valid_start_is_passed_to_the_domain(
    client: TestClient, stubs: StubDependencies, overrides: dict[str, Any]
) -> None:
    response = send_json(client, "POST", START_PATH, start_json(**overrides))

    assert response.status_code == 200
    assert stubs.calls() == ["crawl_runs.start_crawl"]


def test_the_start_notification_passed_to_the_domain_has_aware_utc_datetimes(
    client: TestClient, stubs: StubDependencies
) -> None:
    send_json(client, "POST", START_PATH, start_json(crawl_started_at="2026-11-09T10:00:00+09:00"))

    [notification] = [call.args[0] for call in stubs.crawl_runs.start_crawl.call_args_list]
    assert notification.crawl_started_at.isoformat() == "2026-11-09T01:00:00+00:00"
    assert (notification.ttl, notification.ratio_threshold) == (86_400, 0.2)
    assert (notification.force_delete, notification.rewrite_mode) == (False, False)


def test_the_batch_context_and_documents_are_passed_to_the_domain(
    client: TestClient, stubs: StubDependencies
) -> None:
    document = document_json(url="https://example.com/a", path="a/b.txt", title="タイトル")
    body = batch_json([document], lock=lock_json(owner="crawler-1"))

    send_json(client, "POST", BATCH_PATH, body)

    [call] = stubs.registrar.register.call_args_list
    context, [passed] = call.args
    assert (context.source_id, context.crawl_id) == ("src-docs", "job-20261109-0001")
    assert (context.lock.owner, context.lock.job_id) == ("crawler-1", "job-20261109-0001")
    assert context.crawl_started_at.isoformat() == "2026-11-09T01:00:00+00:00"
    assert (passed.title, passed.url, passed.path) == (
        "タイトル",
        "https://example.com/a",
        "a/b.txt",
    )
    assert passed.source_updated_at.isoformat() == "2026-11-08T12:00:00+00:00"
    assert passed.raw_content == b"hello\nworld\n"


def test_a_null_url_and_path_and_omitted_ones_are_accepted(
    client: TestClient, stubs: StubDependencies
) -> None:
    omitted = document_json()
    explicit = document_json("b", url=None, path=None)

    send_json(client, "POST", BATCH_PATH, batch_json([omitted, explicit]))

    [call] = stubs.registrar.register.call_args_list
    assert [(d.url, d.path) for d in call.args[1]] == [(None, None), (None, None)]


def test_the_raw_content_is_decoded_to_the_original_bytes(
    client: TestClient, stubs: StubDependencies
) -> None:
    original = bytes(range(256)) + b"\x00" * 3
    document = document_json(raw_content=encode(original), size=len(original))

    send_json(client, "POST", BATCH_PATH, batch_json([document]))

    [call] = stubs.registrar.register.call_args_list
    assert call.args[1][0].raw_content == original


def test_the_status_path_id_is_passed_as_is(client: TestClient, stubs: StubDependencies) -> None:
    stubs.crawl_runs.crawl_status.side_effect = RuntimeError("not reached in this test")

    client.get(STATUS_PATH)

    stubs.crawl_runs.crawl_status.assert_called_once_with("job-20261109-0001")


# --- 長さの境界(`_id` は 512 バイトまで。`deletion_result-` の接頭辞を足しても収まる) ---


@pytest.mark.parametrize(
    ("field", "limit"), [("crawl_id", 256), ("source_id", 256)], ids=["crawl_id", "source_id"]
)
def test_an_id_is_accepted_up_to_256_bytes_and_rejected_beyond(
    client: TestClient, stubs: StubDependencies, field: str, limit: int
) -> None:
    accepted = send_json(client, "POST", START_PATH, start_json(**{field: "a" * limit}))
    rejected = send_json(client, "POST", START_PATH, start_json(**{field: "a" * (limit + 1)}))

    assert accepted.status_code == 200
    assert rejected.status_code == 400
    assert len(stubs.calls()) == 1


def test_an_id_is_measured_in_utf8_bytes_not_characters(
    client: TestClient, stubs: StubDependencies
) -> None:
    within = send_json(client, "POST", START_PATH, start_json(crawl_id="あ" * 85))  # 255 バイト
    beyond = send_json(client, "POST", START_PATH, start_json(crawl_id="あ" * 86))  # 258 バイト

    assert (within.status_code, beyond.status_code) == (200, 400)


def test_an_external_id_is_accepted_up_to_4096_bytes_and_rejected_beyond(
    client: TestClient, stubs: StubDependencies
) -> None:
    accepted = send_json(client, "POST", BATCH_PATH, batch_json([document_json("x" * 4096)]))
    assert accepted.status_code == 200
    stubs.registrar.reset_mock()

    rejected = send_json(client, "POST", BATCH_PATH, batch_json([document_json("x" * 4097)]))

    error = assert_rejected(rejected, stubs)  # 書き込み(登録の呼び出し)がゼロ
    assert error["message"] == "invalid request: documents.0.external_id (id_too_long)"


def test_a_long_title_path_and_url_are_left_to_the_domain(
    client: TestClient, stubs: StubDependencies
) -> None:
    """title・mime_type・path・url は、API 層では長さを制限しない(文書単位の判断はドメイン)。"""
    long_title = document_json(title="t" * 100_000, path="p" * 10_000, url="u" * 10_000)
    config_big = make_api_config(max_request_body_bytes=1024 * 1024)

    with stub_client(stubs, config_big) as big_client:
        response = send_json(big_client, "POST", BATCH_PATH, batch_json([long_title]))

    assert response.status_code == 200


# --- 原本の上限(+1 の境界。base64 のパディングの有無が変わる) ---


@pytest.mark.parametrize("size", [1022, 1023, 1024])
def test_a_document_up_to_the_raw_limit_is_decoded(stubs: StubDependencies, size: int) -> None:
    """1022(パディング 1)・1023(なし)・1024(2)のどれでも、デコードして渡す。"""
    document = document_json("d", text="x" * size)

    with stub_client(stubs) as client:
        response = send_json(client, "POST", BATCH_PATH, batch_json([document]))

    assert response.status_code == 200
    [call] = stubs.registrar.register.call_args_list
    [passed] = call.args[1]
    assert (passed.raw_content, passed.size) == (b"x" * size, size)


@pytest.mark.parametrize("size", [1025, 1026, 1027])
def test_a_document_over_the_raw_limit_is_not_decoded_and_keeps_the_estimated_size(
    stubs: StubDependencies, size: int
) -> None:
    """+1 でも、パディングの有無(1025 は 1 個、1026 はなし、1027 は 2 個)によらずデコードしない。"""
    document = document_json("d", text="x" * size)

    with stub_client(stubs) as client:
        response = send_json(client, "POST", BATCH_PATH, batch_json([document]))

    assert response.status_code == 200
    [call] = stubs.registrar.register.call_args_list
    [passed] = call.args[1]
    assert (passed.raw_content, passed.size) == (b"", size)


def test_an_empty_raw_content_is_accepted_as_empty_bytes(stubs: StubDependencies) -> None:
    document = document_json("d", raw_content="", size=0)

    with stub_client(stubs) as client:
        response = send_json(client, "POST", BATCH_PATH, batch_json([document]))

    assert response.status_code == 200
    [call] = stubs.registrar.register.call_args_list
    [passed] = call.args[1]
    assert (passed.raw_content, passed.size) == (b"", 0)


# --- 原本 1 件の上限を超える文書は、バッチ合計に数えない(文書単位の `oversize`。案 1) ---


def test_an_oversize_document_does_not_make_the_whole_batch_a_400(stubs: StubDependencies) -> None:
    """合計の上限(2,048)より大きい原本(5,000)も、デコードされないので合計に入らない。

    実運用の大きさでは、上限 20 MiB・合計 64 MiB に対して 70 MiB の原本が当たる。
    """
    oversize = document_json("big", text="x" * 5000)
    small = document_json("small", text="y" * 1000)

    with stub_client(stubs) as client:
        response = send_json(client, "POST", BATCH_PATH, batch_json([oversize, small, small]))

    assert response.status_code == 200
    [call] = stubs.registrar.register.call_args_list
    big_input, *small_inputs = call.args[1]
    assert (big_input.raw_content, big_input.size) == (b"", 5000)
    assert [passed.raw_content for passed in small_inputs] == [b"y" * 1000] * 2


def test_the_documents_that_are_decoded_still_count_toward_the_batch_total(
    stubs: StubDependencies,
) -> None:
    oversize = document_json("big", text="x" * 5000)
    small = document_json("small", text="y" * 1000)  # 3 件で 3,000 > 2,048

    with stub_client(stubs) as client:
        response = send_json(client, "POST", BATCH_PATH, batch_json([oversize, small, small]))
        too_many = send_json(
            client, "POST", BATCH_PATH, batch_json([small, small, small])
        )  # 合計 3,000

    assert response.status_code == 200
    assert too_many.status_code == 400


def test_an_oversize_base64_beyond_the_request_body_limit_is_still_a_400(
    client: TestClient, stubs: StubDependencies
) -> None:
    """文書単位の `oversize` にならないのは、リクエストボディの上限までの原本。"""
    huge = document_json("big", text="x" * MAX_REQUEST_BODY_BYTES)

    response = send_json(client, "POST", BATCH_PATH, batch_json([huge]))

    error = assert_rejected(response, stubs)
    assert error["message"] == "the request body is too large"


# --- ID の制御文字(ログへの偽の行の注入を防ぐ) ---

CONTROL_CHARACTERS = ["\n", "\r", "\t", "\x01", "\x1b", "\x1f", "\x7f", "\x00"]


@pytest.mark.parametrize("character", CONTROL_CHARACTERS, ids=repr)
@pytest.mark.parametrize(
    ("endpoint", "build"),
    [
        pytest.param(START, lambda v: start_json(crawl_id=f"a{v}b"), id="start-crawl_id"),
        pytest.param(START, lambda v: start_json(source_id=f"a{v}b"), id="start-source_id"),
        pytest.param(FINISH, lambda v: finish_json(source_id=f"a{v}b"), id="finish-source_id"),
        pytest.param(BATCH, lambda v: batch_json(crawl_id=f"a{v}b"), id="batch-crawl_id"),
        pytest.param(
            BATCH, lambda v: batch_json(lock=lock_json(owner=f"a{v}b")), id="batch-lock-owner"
        ),
        pytest.param(
            BATCH, lambda v: batch_json(lock=lock_json(job_id=f"a{v}b")), id="batch-lock-job_id"
        ),
        pytest.param(LAST_SEEN, lambda v: last_seen_json([], crawl_id=f"a{v}b"), id="ls-crawl_id"),
        pytest.param(
            DISCARD, lambda v: locked_json(lock=lock_json(owner=f"a{v}b")), id="discard-owner"
        ),
        pytest.param(
            DELETE_DOCS, lambda v: locked_json(lock=lock_json(job_id=f"a{v}b")), id="delete-job_id"
        ),
        pytest.param(
            DELETE_RECORDS,
            lambda v: locked_json(lock=lock_json(owner=f"a{v}b")),
            id="records-owner",
        ),
    ],
)
def test_an_id_with_a_control_character_is_a_400(
    client: TestClient,
    stubs: StubDependencies,
    endpoint: tuple[str, str],
    build: Any,
    character: str,
) -> None:
    method, path = endpoint

    response = send_json(client, method, path, build(character))

    error = assert_rejected(response, stubs)
    assert "id_invalid_character" in error["message"]


@pytest.mark.parametrize(
    "segment", ["a%0Ab", "a%0Db", "a%09b", "a%1Bb", "a%7Fb"], ids=["lf", "cr", "tab", "esc", "del"]
)
@pytest.mark.parametrize(("method", "template", "body"), PATH_CASES)
def test_a_path_id_with_a_control_character_is_a_400(
    client: TestClient,
    stubs: StubDependencies,
    method: str,
    template: str,
    body: dict[str, Any] | None,
    segment: str,
) -> None:
    response = client.request(method, template.format(segment), json=body)

    error = assert_rejected(response, stubs)
    assert "id_invalid_character" in error["message"]


@pytest.mark.parametrize("character", ["\n", "\r\n", "\t", "\x1b", "\x7f"], ids=repr)
def test_an_external_id_may_contain_control_characters(
    client: TestClient, stubs: StubDependencies, character: str
) -> None:
    """Linux のファイル名として正当で、拒否すると 1 件でバッチ全体が恒久的に 400 になる。

    `external_id` はログに出ない(ハッシュの素材と、応答の JSON だけ)。NUL は別(上の検証が拒否)。
    """
    external_id = f"docs/a{character}b.txt"

    response = send_json(client, "POST", BATCH_PATH, batch_json([document_json(external_id)]))

    assert response.status_code == 200
    [call] = stubs.registrar.register.call_args_list
    assert [document.external_id for document in call.args[1]] == [external_id]


def test_an_id_may_contain_spaces_and_non_ascii_characters(
    client: TestClient, stubs: StubDependencies
) -> None:
    """制御文字だけを拒否する(空白・日本語・記号・`U+0080` 以上は、ID として使える)。"""
    odd_but_valid = "社内 wiki/space (A)#1\u00a0\u2028\u0085"

    response = send_json(client, "POST", START_PATH, start_json(source_id=odd_but_valid))

    assert response.status_code == 200


# --- 報告するエラーの数の上限 ---


def test_more_than_ten_errors_are_cut_to_ten_with_the_number_of_the_rest(
    client: TestClient, stubs: StubDependencies
) -> None:
    body = last_seen_json(["not-hex"] * 13)

    response = send_json(client, "POST", LAST_SEEN_PATH, body)

    message = assert_rejected(response, stubs)["message"]
    assert message.count("string_pattern_mismatch") == 10
    assert message.endswith("; and 3 more")
    assert "document_ids.9 (" in message
    assert "document_ids.10 (" not in message


def test_exactly_ten_errors_have_no_remainder(client: TestClient, stubs: StubDependencies) -> None:
    response = send_json(client, "POST", LAST_SEEN_PATH, last_seen_json(["not-hex"] * 10))

    message = assert_rejected(response, stubs)["message"]
    assert message.count("string_pattern_mismatch") == 10
    assert "more" not in message


# --- 日時・整数・本文の極端な値 ---


def test_the_earliest_instant_in_utc_is_accepted_but_not_when_the_offset_underflows(
    client: TestClient, stubs: StubDependencies
) -> None:
    accepted = send_json(
        client, "POST", START_PATH, start_json(crawl_started_at="0001-01-01T00:00:00Z")
    )
    rejected = send_json(
        client, "POST", START_PATH, start_json(crawl_started_at="0001-01-01T00:00:00+05:00")
    )

    assert accepted.status_code == 200
    assert rejected.status_code == 400
    assert "crawl_started_at (timestamp_invalid)" in rejected.json()["error"]["message"]
    assert len(stubs.calls()) == 1


@pytest.mark.parametrize(
    "source_updated_at", ["9999-12-31T23:59:59-05:00", "0001-01-01T00:00:00+14:00"]
)
def test_a_source_updated_at_that_overflows_after_the_utc_conversion_is_a_400(
    client: TestClient, stubs: StubDependencies, source_updated_at: str
) -> None:
    document = document_json(source_updated_at=source_updated_at)

    response = send_json(client, "POST", BATCH_PATH, batch_json([document]))

    error = assert_rejected(response, stubs)
    assert "documents.0.source_updated_at (timestamp_invalid)" in error["message"]


def test_an_integer_with_thousands_of_digits_is_a_400(
    client: TestClient, stubs: StubDependencies
) -> None:
    """Python の整数の文字列変換の上限(4,300 桁)を超える。500 や遅延にならない。"""
    body = b'{"ttl":' + b"9" * 5000 + b"}"

    response = send_raw(client, "POST", START_PATH, body)

    assert_rejected(response, stubs)


@pytest.mark.parametrize(
    ("endpoint", "build", "field"),
    [
        pytest.param(
            BATCH,
            lambda value: batch_json([document_json(size=value)]),
            "documents.0.size",
            id="size",
        ),
        pytest.param(
            FINISH,
            lambda value: finish_json(enumerated_count=value),
            "enumerated_count",
            id="count",
        ),
        pytest.param(
            FINISH, lambda value: finish_json(skipped_count=value), "skipped_count", id="skipped"
        ),
        pytest.param(
            START, lambda value: start_json(min_delete_count=value), "min_delete_count", id="min"
        ),
    ],
)
def test_integers_are_limited_to_the_int64_range(
    client: TestClient,
    stubs: StubDependencies,
    endpoint: tuple[str, str],
    build: Any,
    field: str,
) -> None:
    method, path = endpoint

    over = send_json(client, method, path, build(2**63))
    assert field in assert_rejected(over, stubs)["message"]

    at_the_limit = send_json(client, method, path, build(2**63 - 1))
    assert at_the_limit.status_code in (200, 202)


def test_a_body_with_a_utf8_bom_is_a_400(client: TestClient, stubs: StubDependencies) -> None:
    body = b"\xef\xbb\xbf" + json.dumps(start_json()).encode("ascii")

    response = send_raw(client, "POST", START_PATH, body)

    assert assert_rejected(response, stubs)["message"] == "the request body is not valid JSON"


def test_a_delete_with_a_chunked_body_and_no_content_length_is_accepted(
    client: TestClient, stubs: StubDependencies
) -> None:
    payload = json.dumps(locked_json()).encode("ascii")

    def chunks() -> Iterator[bytes]:
        yield payload[:10]
        yield payload[10:]

    response = client.request(
        "DELETE",
        DELETE_DOCUMENTS_PATH,
        content=chunks(),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 200
    assert "content-length" not in response.request.headers
    assert stubs.calls() == ["deletion.delete_source_documents"]


def test_a_delete_without_a_body_is_a_400(client: TestClient, stubs: StubDependencies) -> None:
    """`lock` はボディで運ぶ。ボディなしの DELETE は、本文が JSON でないとして拒否される。"""
    response = client.delete(DELETE_DOCUMENTS_PATH)

    assert_rejected(response, stubs)
