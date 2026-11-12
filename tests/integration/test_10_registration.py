"""IT-10〜IT-15: バッチ登録(`POST /sources/{source_id}/documents:batch`)。

目的:
    Crawler 役として文書を登録し、Indexer が実 OpenSearch に書いた内容を直接読んで確かめる。
    形式別の抽出(txt・Markdown・HTML・PDF)、抽出失敗、再登録(`unchanged`・`updated`)、原本サイズ
    超過、ロック不所有を扱う。fake の単体テストでは確認できない、実マッピング(`dynamic: strict`、
    date 型)・実際の `_seq_no`・実際の検索(`_search`)との組み合わせを実機で確認する。

参照する設計書の章:
    - indexer-api-v0.10.md 3.2(受理条件・ロック所有確認・部分結果)、3.6(日時の正規化)、
      4.2(`last-seen`)、4.3(バッチ登録の手順 (a)(b)(c)・応答)、4.9(原本サイズ超過)
    - indexer-architecture-v0.10.md 4.2(抽出・正規化)、4.3(全件処理の手順)、5 章(書き込み種別)、
      K27(変更なしは PUT しない・`last_seen_at` を補う Update)、K30(抽出失敗)、K65(サイズ超過)
    - search-index-v0.10.md 4.1(マッピング)
    - apps/indexer/README.md 6 章(仮定義: ロック文書、サイズ)

扱うシナリオ: IT-10(形式別登録)、IT-11(抽出失敗)、IT-12(再登録 unchanged)、
    IT-13(再登録 updated)、IT-14(サイズ超過)、IT-15(ロック不所有)

共通の前提:
    各テストは専用の `source_id` と `crawl_id` を使い(他のテストと干渉しない)、`crawler.begin()` で
    ロック文書の書き込みと開始通知を済ませてから登録する(登録の受理条件。api 3.2)。
"""

import hashlib
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Any

import pytest

from support import (
    EXPIRED_LEASE_AGE,
    MILLIS_INSTANT_PATTERN,
    OVERSIZE_RAW_BYTES,
    SEARCH_INDEX,
    CrawlerClient,
    Lock,
    OpenSearchProbe,
    SourceDocument,
    ago,
    expect_json,
    iso,
    oversize_document,
    sample_document,
    text_document,
    utc_now,
)


def _fetch_record(
    opensearch: OpenSearchProbe, source_id: str, document: SourceDocument
) -> dict[str, Any]:
    """登録した文書を OpenSearch から直接読む(`_source`・`_seq_no` を含む応答本文)。"""
    record = opensearch.fetch_document(source_id, document.external_id)
    assert record is not None, f"{document.external_id} must exist in the search index"
    return record


# --- IT-10: 形式別の登録 ---


@dataclass(frozen=True)
class FormatCase:
    file_name: str
    marker: str  # 本文に含まれる固有の語(検索で 1 件に当たる)
    phrase: str  # 本文に含まれる語順どおりの連なり
    source_updated_at: str  # リクエストで送る表記(秒精度・オフセット・小数桁数を散らす)
    expected_source_updated_at: str  # 保存されるべき正規形(UTC・ミリ秒。api 3.6)


# 日時の表記を形式ごとに変えるのは、正規化(UTC・ミリ秒)が date 型のマッピングに通ることを、
# 複数の入力形で確かめるため。小数は、切り捨てでも四捨五入でも同じになる値にしている
# (api 3.6 は「ミリ秒精度」とだけ定めている)。
FORMAT_CASES = [
    FormatCase(
        "sample.txt",
        "txtmarkeralpha",
        "結合テスト用サンプル",
        "2026-11-08T12:00:00Z",
        "2026-11-08T12:00:00.000Z",
    ),
    FormatCase(
        "sample.md",
        "mdmarkerbeta",
        "原文のまま",
        "2026-11-08T21:00:00.123456+09:00",
        "2026-11-08T12:00:00.123Z",
    ),
    FormatCase(
        "sample.html",
        "htmlmarkergamma",
        "段落その一",
        "2026-11-08T12:00:00.5Z",
        "2026-11-08T12:00:00.500Z",
    ),
    FormatCase(
        "sample.pdf",
        "pdfmarkerdelta",
        "Hello Loreley PDF",
        "2026-11-08T12:00:00.000Z",
        "2026-11-08T12:00:00.000Z",
    ),
]


def _assert_extracted_content(file_name: str, raw: bytes, content: str) -> None:
    """形式ごとの、抽出後の本文の期待(arch 4.2)。"""
    if file_name in ("sample.txt", "sample.md"):
        # txt と Markdown は原文のまま(Markdown の記法も解釈しない)。サンプルは正規化で変わらない
        # 形(LF・行末空白なし・NFC)にしてあるので、原文と完全に一致する。
        assert content == raw.decode("utf-8"), f"{file_name} must be stored as-is: {content!r}"
    elif file_name == "sample.html":
        # タグ・script・style は本文に残らない(arch 4.2)。
        assert "<" not in content and ">" not in content, f"tags must be removed: {content!r}"
        for leaked in ("scriptleakmarker", "cssleakmarker", "color: red"):
            assert leaked not in content, f"{leaked} (script/style) must not remain: {content!r}"
        # 段落の境界は改行になり、語が連結しない(連結すると語が混ざって検索できなくなる)。
        assert "段落その一。" in content and "段落その二。" in content, (
            f"the body text must remain: {content!r}"
        )
        assert "段落その一。段落その二。" not in content, (
            f"paragraphs must not be glued together: {content!r}"
        )
    elif file_name == "sample.pdf":
        assert "Hello Loreley PDF" in content, f"the PDF text must be extracted: {content!r}"


@pytest.mark.parametrize("case", FORMAT_CASES, ids=lambda case: case.file_name)
def test_registers_each_supported_format_and_stores_the_extracted_text(
    case: FormatCase, crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    txt・Markdown・HTML・PDF の各形式を登録すると、抽出した本文・ハッシュ・メタデータ・日時が実
    OpenSearch に正しく保存され、本文の語句で検索に当たること。

    【前提と手順】
    前提: 専用の `source_id`。`crawl_started_at` は 1 分前(`last_seen_at` の期待値になる)。
    手順: サンプルを 1 件登録 → 応答を確認 → OpenSearch の文書を直接読む → `_search` と range
    クエリで検索・date 型の動作を確認する。

    【期待する結果とその根拠】
    - 応答は `status: ok`・`change: created`・`extract_failed: false`。`document_id` はテスト側の独立実装と
      一致(api 4.3、IT-02)。
    - `index_status=indexed`、`summary_status=disabled`(要約は無効。README 7 章)、`summary` なし。
    - `content_hash` はリクエストの値そのまま(Indexer は再計算も照合もしない。api 4.3 / K66)。
    - `text_hash` は保存された `content` の SHA-256(arch K22。変更の有無の判定に使う)。
    - `last_seen_at` は `crawl_started_at`(api 4.3: Indexer が書く)。
    - `source_updated_at` は UTC・ミリ秒に正規化された値(api 3.6)。date 型に受け入れられるので、
      range クエリで検索できる。
    - 抽出後の本文: txt・Markdown は原文のまま、HTML はタグ・script・style なし、PDF は ASCII テキスト
      (arch 4.2)。

    【fake では確認できず実機で確認する点】
    実際のマッピング(`dynamic: strict`、date 型、text 型)が Indexer の書き込み項目を受理すること、
    pypdf・lxml による実際の抽出、日時の正規化が date 型に通ること、`_search` に実際に当たること。
    """
    document = replace(sample_document(case.file_name), source_updated_at=case.source_updated_at)
    crawl_started_at = ago(minutes=1)

    # クロールを開始して、サンプルを 1 件登録する
    crawl = crawler.begin(source_id, started_at=crawl_started_at)
    results = crawl.register_ok([document])

    # 応答: 新規登録で、抽出に成功している
    result = results[0]
    assert result["status"] == "ok", f"the registration must succeed: {result}"
    assert result["change"] == "created", f"a new document must be 'created': {result}"
    assert result["extract_failed"] is False, f"extraction must succeed: {result}"
    assert result["document_id"] == document.document_id(source_id), (
        f"document_id must match the independent implementation: {result}"
    )

    # OpenSearch の実データを直接読んで確認する
    record = _fetch_record(opensearch, source_id, document)
    source = record["_source"]
    assert source["index_status"] == "indexed", f"index_status must be indexed: {source}"
    assert source["summary_status"] == "disabled", f"summaries are disabled: {source}"
    assert "summary" not in source, f"no summary must be written while disabled: {source}"
    assert source["content_hash"] == document.content_hash, "content_hash must be stored as sent"
    assert source["text_hash"] == hashlib.sha256(source["content"].encode("utf-8")).hexdigest(), (
        "text_hash must be the SHA-256 of the stored content"
    )
    assert source["truncated"] is False, f"a small document must not be truncated: {source}"
    assert source["last_seen_at"] == iso(crawl_started_at), (
        f"last_seen_at must be crawl_started_at: {source['last_seen_at']}"
    )
    assert source["source_updated_at"] == case.expected_source_updated_at, (
        f"source_updated_at must be normalized to UTC milliseconds: {source['source_updated_at']}"
    )
    assert MILLIS_INSTANT_PATTERN.match(source["indexed_at"]), (
        f"indexed_at must be UTC milliseconds: {source['indexed_at']}"
    )
    assert (source["mime_type"], source["size"], source["title"]) == (
        document.mime_type,
        len(document.raw),
        document.title,
    ), f"metadata must be stored as sent: {source}"
    assert (source["url"], source["path"]) == (document.url, document.path), (
        f"url and path must be stored as separate fields: {source}"
    )
    _assert_extracted_content(case.file_name, document.raw, source["content"])

    # 検索: 本文の語と語順どおりの連なりで、この文書だけに当たる
    term_hits = opensearch.search_content(source_id, case.marker)
    assert [hit["_id"] for hit in term_hits] == [record["_id"]], (
        f"searching '{case.marker}' must hit exactly this document: {term_hits}"
    )
    phrase_hits = opensearch.search_content(source_id, case.phrase, phrase=True)
    assert [hit["_id"] for hit in phrase_hits] == [record["_id"]], (
        f"searching the phrase '{case.phrase}' must hit exactly this document: {phrase_hits}"
    )

    # date 型: 正規化した日時が range クエリで検索できる(date として索引されている)
    in_range = opensearch.count(
        SEARCH_INDEX,
        {
            "bool": {
                "filter": [
                    {"term": {"source_id": source_id}},
                    {"range": {"last_seen_at": {"gte": iso(crawl_started_at)}}},
                    {"range": {"source_updated_at": {"gte": case.expected_source_updated_at}}},
                ]
            }
        },
    )
    assert in_range == 1, (
        f"last_seen_at and source_updated_at must be searchable as dates: {in_range}"
    )


# --- IT-11: 抽出失敗 ---


def test_corrupt_pdf_is_registered_as_extract_failed_without_content(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    壊れた PDF が、登録の失敗ではなく `extract_failed` として登録されること。本文・`text_hash`・要約を
    持たず、メタデータだけが残ること。

    【前提と手順】
    前提: 専用の `source_id`。`corrupt.pdf` は MIME タイプが PDF だが PDF ではないバイト列。
    手順: 1 件登録 → 応答と OpenSearch の文書を確認する。

    【期待する結果とその根拠】
    - 応答は `status: ok`・`change: created`・`extract_failed: true`。抽出の失敗は文書単位の失敗ではなく、
      タイトルとメタデータの登録として扱う(api 4.3。リトライしない)。
    - `index_status=extract_failed`。`content`・`text_hash`・`summary` を書かず、`summary_status=disabled`
      (arch K30)。
    - `content_hash` はリクエストの値、`last_seen_at` は `crawl_started_at`。つまりこの文書は、後の件数
      照合で `N_seen` に数えられる(api 4.4「抽出に失敗した文書は検索インデックスにあるので N_seen に数えられる」。
      IT-30 で件数として確認する)。

    【fake では確認できず実機で確認する点】
    実際の pypdf が壊れた入力で投げる例外を Indexer が「抽出失敗」に分類できること(fake は抽出を通さない)。
    抽出失敗の文書が `dynamic: strict` のマッピングに通ること(`content` なしの形)。
    """
    document = sample_document("corrupt.pdf")
    crawl_started_at = ago(minutes=1)

    # クロールを開始して、壊れた PDF を登録する
    crawl = crawler.begin(source_id, started_at=crawl_started_at)
    result = crawl.register_ok([document])[0]

    # 応答: 登録は成功で、抽出だけが失敗している
    assert result["status"] == "ok", f"extract failure is not a registration failure: {result}"
    assert result["extract_failed"] is True, f"extract_failed must be true: {result}"
    assert result["change"] == "created", f"the document must still be registered: {result}"

    # OpenSearch の文書: 本文なし、メタデータあり
    source = _fetch_record(opensearch, source_id, document)["_source"]
    assert source["index_status"] == "extract_failed", f"index_status must say so: {source}"
    for absent in ("content", "text_hash", "summary", "summary_model"):
        assert absent not in source, f"{absent} must not be written for extract_failed: {source}"
    assert source["summary_status"] == "disabled", f"summary_status must be disabled: {source}"
    assert source["content_hash"] == document.content_hash, "content_hash must still be stored"
    assert source["title"] == document.title, f"the title must still be registered: {source}"
    assert source["last_seen_at"] == iso(crawl_started_at), (
        f"last_seen_at must be set so that the document counts as seen: {source}"
    )


# --- IT-12: 再登録 unchanged ---


def test_registering_the_same_content_again_is_unchanged_and_writes_nothing(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    同じ内容の再登録が `unchanged` になり、全文書き込みをしないこと(`_seq_no`・`indexed_at` が不変)。
    `last-seen` を省略した新しいクロールでは、`last_seen_at` だけが補われること。

    【前提と手順】
    前提: クロール 1(2 時間前開始)で文書 X を登録済み。
    手順: (1) 同じクロールで同じ内容を再登録 → (2) 新しいクロール 2(1 分前開始。クロール 1 は
    `superseded`)で `last-seen` を送らずに同じ内容を登録 → (3) クロール 2 でもう一度登録。

    【期待する結果とその根拠】
    (1) `change: unchanged`。`_seq_no` と `_source` 全体が不変(変更のない文書は PUT しない。api 4.3 手順 2(b)、
        arch K27)。`last_seen_at` はすでに `crawl_started_at` 以上なので補完の Update もない。
    (2) `change: unchanged` のまま、`last_seen_at` が `crawl_started_at` に更新される。それ以外の項目
        (`content`・`indexed_at` など)は不変。補完は `last_seen_at` だけの Update で、`_seq_no` は進む
        (api 4.3 (b)「4.2 が失敗・省略された場合にだけ補う」、arch K27)。
    (3) `change: unchanged`。`last_seen_at` が現在値以上なので書かず、`_seq_no` は不変(補完は古いときだけ)。

    【fake では確認できず実機で確認する点】
    実際の `_seq_no` が、書き込みの有無に応じて変わる/変わらないこと(楽観ロックの基本動作。arch U-31(2))。
    補完の Update(painless スクリプト。U-31(6))が実機で動くこと。
    """
    document = text_document("docs/unchanged.txt", "same body for the unchanged check")

    # クロール 1(2 時間前開始)で登録する
    crawl1 = crawler.begin(source_id, started_at=ago(hours=2))
    assert crawl1.register_ok([document])[0]["change"] == "created", "the first registration"
    first = _fetch_record(opensearch, source_id, document)

    # (1) 同じクロールで同じ内容を再登録する: 書き込みなし
    assert crawl1.register_ok([document])[0]["change"] == "unchanged", (
        "re-registering the same content in the same crawl must be unchanged"
    )
    second = _fetch_record(opensearch, source_id, document)
    assert second["_seq_no"] == first["_seq_no"], (
        f"an unchanged document must not be written: _seq_no {first['_seq_no']} -> {second['_seq_no']}"
    )
    assert second["_source"] == first["_source"], "an unchanged document must not change at all"

    # (2) 新しいクロール 2 で、last-seen を省略して同じ内容を登録する: last_seen_at だけ補われる
    crawl2_started_at = ago(minutes=1)
    crawl2 = crawler.begin(source_id, started_at=crawl2_started_at)
    superseded = crawl1.status()
    assert (superseded["status"], superseded["reason"]) == ("discarded", "superseded"), (
        f"the previous unfinished crawl must be superseded by the new start: {superseded}"
    )
    assert crawl2.register_ok([document])[0]["change"] == "unchanged", (
        "the same content in a new crawl must still be unchanged"
    )
    third = _fetch_record(opensearch, source_id, document)
    assert third["_source"]["last_seen_at"] == iso(crawl2_started_at), (
        f"last_seen_at must be filled in by the registration: {third['_source']['last_seen_at']}"
    )
    assert third["_seq_no"] > second["_seq_no"], "the last_seen_at update is a write"
    first_without_last_seen = {k: v for k, v in first["_source"].items() if k != "last_seen_at"}
    third_without_last_seen = {k: v for k, v in third["_source"].items() if k != "last_seen_at"}
    assert third_without_last_seen == first_without_last_seen, (
        "only last_seen_at may change (content and indexed_at must stay)"
    )

    # (3) もう一度登録する: last_seen_at が現在値以上なので、書かない
    assert crawl2.register_ok([document])[0]["change"] == "unchanged", "the repeated registration"
    fourth = _fetch_record(opensearch, source_id, document)
    assert fourth["_seq_no"] == third["_seq_no"], (
        "last_seen_at must be filled in only while it is behind crawl_started_at"
    )


# --- IT-13: 再登録 updated ---


def test_registering_changed_content_is_updated_and_last_seen_at_never_moves_back(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    本文が変わった再登録が `updated` になり、`content`・`text_hash`・`content_hash` が更新されること。
    `last_seen_at` が新しいクロールの値になり、さらに新しい値を持つ文書では古い値に戻らないこと(max 比較)。

    【前提と手順】
    前提: クロール 1(2 時間前開始)で文書 X(版 1)を登録済み。
    手順: (1) クロール 2(1 分前開始)で `last-seen` → 版 2 を登録。(2) 前提作りとして X の `last_seen_at` を
    未来の値に直接書き換え → 版 3 を登録。

    【期待する結果とその根拠】
    (1) `change: updated`。`content` が版 2、`text_hash` が版 2 の `content` の SHA-256、`content_hash` が
        版 2 の原本のハッシュ。`last_seen_at` はクロール 2 の `crawl_started_at`(api 4.3 手順 2(c))。
        検索は新しい語に当たり、古い語には当たらない(索引が置き換わっている)。
    (2) `change: updated`。`last_seen_at` は未来の値のまま(登録の PUT は、読んだ値と `crawl_started_at` の
        大きい方を書く。api 4.3 / arch 5 章、C-4)。通常の API の流れでは、受理中のクロールの
        `crawl_started_at` より新しい `last_seen_at` を作れないため、直接書き換えで前提を作る。

    【fake では確認できず実機で確認する点】
    実機の `_seq_no`・`_primary_term` を付けた条件付き PUT(`if_seq_no`)が、実際に受理されること
    (arch U-31(2))。日時を文字列でなく時刻として比べていること(ミリ秒の表記が揃っているので文字列比較でも
    通るが、max 比較の動作自体はここで確認する)。
    """
    version1 = text_document("docs/updated.txt", "first version with oldwordzero")
    version2 = version1.with_raw(b"second version with newwordone")
    version3 = version1.with_raw(b"third version with newwordtwo")

    # クロール 1(2 時間前開始)で版 1 を登録する
    crawl1 = crawler.begin(source_id, started_at=ago(hours=2))
    assert crawl1.register_ok([version1])[0]["change"] == "created", "the first version"
    before = _fetch_record(opensearch, source_id, version1)

    # (1) クロール 2(1 分前開始)で last-seen → 版 2 を登録する
    crawl2_started_at = ago(minutes=1)
    crawl2 = crawler.begin(source_id, started_at=crawl2_started_at)
    assert [r["result"] for r in crawl2.last_seen_ok([version1.document_id(source_id)])] == [
        "updated"
    ], "last-seen must move last_seen_at from crawl 1 to crawl 2"
    assert crawl2.register_ok([version2])[0]["change"] == "updated", "changed content is updated"
    after = _fetch_record(opensearch, source_id, version2)
    after_source = after["_source"]
    assert after["_seq_no"] > before["_seq_no"], "an updated document must be written"
    assert after_source["content"] == "second version with newwordone", (
        f"content must be replaced: {after_source['content']!r}"
    )
    assert (
        after_source["text_hash"]
        == hashlib.sha256(after_source["content"].encode("utf-8")).hexdigest()
    ), "text_hash must follow the new content"
    assert after_source["content_hash"] == version2.content_hash, "content_hash must follow"
    assert after_source["last_seen_at"] == iso(crawl2_started_at), (
        f"last_seen_at must be crawl 2's crawl_started_at: {after_source['last_seen_at']}"
    )
    assert len(opensearch.search_content(source_id, "newwordone")) == 1, (
        "the new word is searchable"
    )
    assert opensearch.search_content(source_id, "oldwordzero") == [], (
        "the old word must be gone from the index"
    )

    # (2) 未来の last_seen_at を直接用意して、版 3 を登録する: 古い値(crawl_started_at)に戻らない
    future = utc_now() + timedelta(hours=1)
    opensearch.force_last_seen_at(source_id, version2.external_id, future)
    assert crawl2.register_ok([version3])[0]["change"] == "updated", "the third version"
    latest = _fetch_record(opensearch, source_id, version3)["_source"]
    assert latest["content"] == "third version with newwordtwo", "content must follow version 3"
    assert latest["last_seen_at"] == iso(future), (
        f"last_seen_at must not move back to crawl_started_at (max): {latest['last_seen_at']}"
    )


# --- IT-14: 原本サイズ超過 ---


def test_oversize_documents_fail_individually_and_are_not_indexed(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    `MAX_RAW_BYTES`(compose.test.yaml で 64 KiB)を超える原本が、文書単位で `failed` / `oversize` に
    なり索引されないこと。同じバッチの他の文書は成功すること。

    【前提と手順】
    前提: Indexer は `LORELEY_INDEXER_MAX_RAW_BYTES=65536` で起動している。
    手順: 1 バッチに 4 件(小・実サイズ超過・申告サイズだけ超過・小)を入れて登録する。

    【期待する結果とその根拠】
    - 実サイズが 70,000 バイトの文書: `failed`・`oversize`(base64 の長さから推定してデコードせず拒否。
      api 4.3「サイズの防御」(a))。
    - 実サイズは小さいが申告 `size` が上限超: デコードしたあとに `failed`・`oversize`(同 (b))。
    - 前後の小さな文書は `ok`・`created`(文書単位の結果は互いに依存しない。api 3.1)。HTTP は 200
      (文書単位の失敗は本文で返す。api 3.4)。
    - 注: 実サイズ超過の文書は、base64 の長さからの推定(デコード前)で拒否されるのか、デコード後に拒否される
      のかを、このテストは区別できない(どちらも `failed` / `oversize`。API では観測できない)。
      「申告サイズだけ超過」(デコード後に拒否)と合わせて、どちらの経路でも `oversize` になることの確認まで。
    - `failed` の文書には `message` がある(api 4.3)。2 件の超過文書は索引にない(抽出も書き込みもしない。
      api 4.9)。件数照合での扱い(`oversize_document_ids`)は IT-30 で確認する。

    【fake では確認できず実機で確認する点】
    実際の設定値(環境変数 `MAX_RAW_BYTES`)が起動した Indexer に反映されていること、実際の base64 の
    リクエストでサイズ判定が働くこと。
    """
    small_before = text_document("docs/small-before.txt", "small document before")
    oversize = oversize_document("docs/oversize.txt")
    declared_oversize = replace(
        text_document("docs/declared-oversize.txt", "actually small"),
        declared_size=OVERSIZE_RAW_BYTES,
    )
    small_after = text_document("docs/small-after.txt", "small document after")

    # クロールを開始して、4 件を 1 バッチで登録する
    crawl = crawler.begin(source_id, started_at=ago(minutes=1))
    results = crawl.register_ok([small_before, oversize, declared_oversize, small_after])

    # 小さな文書は成功する
    for result in (results[0], results[3]):
        assert (result["status"], result["change"]) == ("ok", "created"), (
            f"a small document in the same batch must succeed: {result}"
        )
    # 超過した 2 件は、文書単位で oversize になる
    for result in (results[1], results[2]):
        assert result["status"] == "failed", f"an oversize document must fail: {result}"
        assert result["failure_type"] == "oversize", f"failure_type must be oversize: {result}"
        assert result.get("message"), f"a failed result must carry a message: {result}"

    # OpenSearch: 超過した 2 件は索引されていない
    assert opensearch.fetch_document(source_id, oversize.external_id) is None, (
        "an oversize document must not be indexed"
    )
    assert opensearch.fetch_document(source_id, declared_oversize.external_id) is None, (
        "a document whose declared size is oversize must not be indexed"
    )
    assert opensearch.count_source_documents(source_id) == 2, "only the 2 small documents exist"


def test_oversize_registration_keeps_the_existing_document_untouched(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    すでに索引にある文書が、のちに上限を超える原本として再送されても、既存の内容が書き換わらず残ること。

    【前提と手順】
    前提: 小さな文書 X を登録済み。
    手順: 同じ `external_id` で、原本を 70,000 バイトに差し替えて再登録する。

    【期待する結果とその根拠】
    `failed`・`oversize`。X の `_seq_no` と `_source` は不変。原本が上限を超えたことで、旧い内容を消さない
    (api 4.9、arch K65)。

    【fake では確認できず実機で確認する点】
    実 OpenSearch の文書が実際に書き換わっていないこと(`_seq_no` の不変)。
    """
    existing = text_document("docs/existing.txt", "existing body")
    crawl = crawler.begin(source_id, started_at=ago(minutes=1))

    # 小さな原本で登録する
    assert crawl.register_ok([existing])[0]["change"] == "created", "the first registration"
    before = _fetch_record(opensearch, source_id, existing)

    # 同じ文書を、上限を超える原本で再登録する
    oversized_version = existing.with_raw(b"y" * OVERSIZE_RAW_BYTES)
    result = crawl.register_ok([oversized_version])[0]

    assert (result["status"], result["failure_type"]) == ("failed", "oversize"), (
        f"the oversize re-registration must fail: {result}"
    )
    after = _fetch_record(opensearch, source_id, existing)
    assert after["_seq_no"] == before["_seq_no"], "the existing document must not be written"
    assert after["_source"] == before["_source"], "the existing document must stay as it was"


# --- IT-15: ロック不所有 ---


def _present_a_lock_that_is_not_owned(
    scenario: str, source_id: str, opensearch: OpenSearchProbe, owned: Lock
) -> Lock:
    """ロックを所有していない状態を作り、リクエストに添えるロックを返す。

    api 3.2: ロック文書がない・リースが期限切れ・`owner` か `job_id` が不一致、のいずれも「所有していない」。
    """
    if scenario == "other_owner":
        return Lock(owner="someone-else", job_id=owned.job_id)
    if scenario == "other_job":
        return Lock(owner=owned.owner, job_id="another-job")
    if scenario == "expired_lease":
        # 所有者は一致しているが、リースの期限が過去(時計のずれに耐える 1 時間前。EXPIRED_LEASE_AGE)
        opensearch.write_lock_document(source_id, owned, utc_now() - EXPIRED_LEASE_AGE)
        return owned
    if scenario == "no_lock_document":
        opensearch.delete_lock_document(source_id)
        return owned
    raise AssertionError(f"unknown scenario: {scenario}")


LOCK_SCENARIOS = ["other_owner", "other_job", "expired_lease", "no_lock_document"]


@pytest.mark.parametrize("scenario", LOCK_SCENARIOS)
def test_registration_without_lock_ownership_fails_per_document_and_writes_nothing(
    scenario: str, crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    ロックを所有していないバッチ登録が、文書単位の `failed` / `lock_not_owned` になり、何も書かれないこと。

    【前提と手順】
    前提: クロールは開始済み(受理条件 (1)〜(5) は満たす)。ロックだけが、シナリオごとに所有していない状態:
    別の `owner`、別の `job_id`、リース期限切れ、ロック文書なし。
    手順: 2 件のバッチを登録する。

    【期待する結果とその根拠】
    - HTTP 200 で、2 件とも `failed` / `lock_not_owned`。ロックを失ったあとの未処理の文書も、書かずに
      `lock_not_owned` にする(バッチの先頭で失敗しても全件。api 3.2「部分結果」、API-U-13)。リクエスト全体の
      409 にはしない(受理条件 (1)〜(5) の拒否とは別。api 3.4)。
    - 索引に何も書かれていない(`_count` が 0)。

    【fake では確認できず実機で確認する点】
    実際の `loreley-jobs` のロック文書(型付きマッピング)を Indexer が読み、`lease_expires_at` の
    ISO 8601 文字列を実際に解釈して所有を判定すること(README 6 章の仮定義)。
    """
    documents = [text_document("docs/lock-a.txt", "a"), text_document("docs/lock-b.txt", "b")]
    crawl = crawler.begin(source_id, started_at=ago(minutes=1))

    # ロックを所有していない状態を作って、登録する
    presented = _present_a_lock_that_is_not_owned(scenario, source_id, opensearch, crawl.lock)
    body = expect_json(crawl.register(documents, lock=presented), 200)

    results = body["results"]
    assert [(r["status"], r.get("failure_type")) for r in results] == [
        ("failed", "lock_not_owned"),
        ("failed", "lock_not_owned"),
    ], f"every document must fail with lock_not_owned ({scenario}): {results}"
    assert opensearch.count_source_documents(source_id) == 0, (
        f"nothing may be written without the lock ({scenario})"
    )


@pytest.mark.parametrize("scenario", LOCK_SCENARIOS)
def test_last_seen_without_lock_ownership_fails_per_document_and_writes_nothing(
    scenario: str, crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    ロックを所有していない `last-seen` が、文書単位の `lock_not_owned` になり、`last_seen_at` が
    更新されないこと。

    【前提と手順】
    前提: クロール 1(2 時間前開始)で文書 X を登録済み(`last_seen_at` = クロール 1 の開始時刻)。
    クロール 2(1 分前開始。更新されれば値が変わる)を開始し、そのロックをシナリオごとに所有していない状態にする。
    手順: クロール 2 として X の `last-seen` を送る。

    【期待する結果とその根拠】
    - HTTP 200 で、X の `result` が `lock_not_owned`(api 4.2。登録と同じ所有確認)。
    - X の `last_seen_at` はクロール 1 の値のまま。書き込まれていれば、クロール 2 の値になるはずなので、
      「何も書かれない」が確認できる。

    【fake では確認できず実機で確認する点】
    登録と同じく、実際のロック文書の解釈。Update API のスクリプトが実行されていないこと(値が不変)。
    """
    document = text_document("docs/lock-seen.txt", "seen")
    crawl1 = crawler.begin(source_id, started_at=ago(hours=2))
    assert crawl1.register_ok([document])[0]["change"] == "created", "the first registration"
    before = _fetch_record(opensearch, source_id, document)

    # クロール 2 を開始し、ロックを所有していない状態で last-seen を送る
    crawl2 = crawler.begin(source_id, started_at=ago(minutes=1))
    presented = _present_a_lock_that_is_not_owned(scenario, source_id, opensearch, crawl2.lock)
    response = crawl2.last_seen([document.document_id(source_id)], lock=presented)
    body = expect_json(response, 200)

    assert body["results"] == [
        {"document_id": document.document_id(source_id), "result": "lock_not_owned"}
    ], f"last-seen must fail with lock_not_owned ({scenario}): {body}"
    after = _fetch_record(opensearch, source_id, document)
    assert after["_source"]["last_seen_at"] == before["_source"]["last_seen_at"], (
        f"last_seen_at must not be written without the lock ({scenario})"
    )
    assert after["_seq_no"] == before["_seq_no"], f"nothing may be written ({scenario})"
