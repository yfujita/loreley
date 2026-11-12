"""IT-02: `document_id` のテスト側算出(テストの土台の検証)。

目的:
    結合テストは、文書を ID で取得する・`last-seen` の `document_ids` を作るために、`document_id` を
    Crawler と同じ規則でテスト側で算出する。その独立実装(`support.compute_document_id`。Indexer の
    コードは import しない)が、設計書の規則と Indexer の実装の両方と一致することを先に確かめる。
    ここが食い違うと、以降のテストの失敗が「テストの誤り」か「Indexer の誤り」か切り分けられない。

参照する設計書の章:
    - indexer-api-v0.10.md 3.3(`document_id` の規則)、4.3(応答例の `document_id`)
    - apps/indexer/README.md 6 章「`document_id` の算出」
    - apps/indexer/tests/documents/test_document_id.py の `API_EXAMPLE_VECTORS`(api 4.3 の応答例)

扱うシナリオ: IT-02
"""

import hashlib
import unicodedata

import pytest

from support import (
    SEARCH_INDEX,
    CrawlerClient,
    OpenSearchProbe,
    SourceDocument,
    ago,
    compute_document_id,
    text_document,
)

# api 4.3 の応答例(source_id `src-docs`)の document_id。
# `apps/indexer/tests/documents/test_document_id.py` の API_EXAMPLE_VECTORS と同じ値(設計書が出所)。
API_EXAMPLE_VECTORS = [
    ("src-docs", "page-10023", "6b5851d90534fc00e388eeb8bd8c79ae48b8bf5c58e4fb0191e708afa28674d7"),
    ("src-docs", "page-10024", "7f2216b2a91e74fe53ce071ed0bd8dcebccaa904f9a8d8004f592b0a4210a9c5"),
    ("src-docs", "page-10025", "48ea91b73f76334d8cf88f6a77438e740ba9d54a338970ad1433aa2f504c2c40"),
]


@pytest.mark.parametrize(
    ("source_id", "external_id", "expected"),
    API_EXAMPLE_VECTORS,
    ids=[external_id for _, external_id, _ in API_EXAMPLE_VECTORS],
)
def test_independent_implementation_matches_the_api_example_vectors(
    source_id: str, external_id: str, expected: str
) -> None:
    """【何を確認するか】
    テスト側の `compute_document_id` が、設計書 api 4.3 の応答例の `document_id` と一致すること。

    【前提と手順】
    前提: なし(純粋な計算。スタックの疎通確認は全テスト共通の session フィクスチャが行う)。
    手順: 応答例の (`source_id`, `external_id`) から算出し、設計書の値と比べる。

    【期待する結果とその根拠】
    3 件とも一致。api 4.3 は、この値を「Crawler との算出の一致の確認に使える」と位置づけている
    (共有のテストベクタは API-U-7 で未決のため、設計書の応答例が唯一の出所)。

    【fake では確認できず実機で確認する点】
    なし(算出の独立性の確認。Indexer との一致は次のテストで実機で確認する)。
    """
    # 独立実装で算出する
    actual = compute_document_id(source_id, external_id)

    assert actual == expected, (
        f"independent document_id for ({source_id}, {external_id}) must match api 4.3: {actual}"
    )


def test_independent_implementation_follows_the_normalization_rules() -> None:
    """【何を確認するか】
    テスト側の算出が、README 6 章の正規化規則(NFC、`\\`→`/`、先頭 `/` は除去しない、大文字小文字を
    区別する、NUL 区切り)に従うこと。

    【前提と手順】
    前提: なし(純粋な計算)。
    手順: 規則ごとに、同値になるべき組と異なるべき組を算出して比べる。

    【期待する結果とその根拠】
    - 素の定義: SHA-256(`source_id` + NUL + `external_id`)の小文字 16 進(api 3.3)。
    - NFD と NFC は同じ ID(ハッシュの前に NFC へ正規化。api 3.3)。
    - `\\` と `/` は同じ ID(パス区切りの統一。api 3.3)。
    - `/a` と `a` は別の ID(先頭の `/` は除去しない。api 3.3 の K58)。
    - 大文字小文字は別の ID(区別したまま扱う。api 3.3)。

    【fake では確認できず実機で確認する点】
    なし(テスト側の実装の確認)。
    """
    source_id = "src"

    # 素の定義と一致すること(NUL 区切りの連結の SHA-256)
    expected_plain = hashlib.sha256(b"src\x00a/b.txt").hexdigest()
    assert compute_document_id(source_id, "a/b.txt") == expected_plain, (
        "document_id must be SHA-256 of source_id + NUL + external_id in lowercase hex"
    )

    # NFD(結合文字)と NFC は同じ ID になる
    nfc = unicodedata.normalize("NFC", "がぎぐ.txt")
    nfd = unicodedata.normalize("NFD", "がぎぐ.txt")
    assert nfc != nfd, "the fixture must really differ before normalization"
    assert compute_document_id(source_id, nfd) == compute_document_id(source_id, nfc), (
        "NFD and NFC external_ids must give the same document_id"
    )

    # バックスラッシュとスラッシュは同じ ID になる
    assert compute_document_id(source_id, "dir\\a.txt") == compute_document_id(
        source_id, "dir/a.txt"
    ), "backslash and slash must give the same document_id"

    # 先頭の `/` は除去されないので別の ID になる
    assert compute_document_id(source_id, "/a.txt") != compute_document_id(source_id, "a.txt"), (
        "a leading slash must not be stripped"
    )

    # 大文字小文字は区別される
    assert compute_document_id(source_id, "A.txt") != compute_document_id(source_id, "a.txt"), (
        "case must be kept"
    )

    # NUL 区切りがあるので、連結が同じになる別の組は別の ID になる
    assert compute_document_id("a", "bc") != compute_document_id("ab", "c"), (
        "the NUL separator must keep different (source_id, external_id) pairs apart"
    )


def test_indexer_computes_the_same_document_id_as_the_independent_implementation(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    Indexer が実際に算出して返す `document_id`(応答と OpenSearch の `_id`)が、テスト側の独立実装と
    一致すること。正規化(NFD→NFC、`\\`→`/`)を実機の経路で通しても一致すること。

    【前提と手順】
    前提: 専用の `source_id`。クロールを開始済み(ロック書き込みと開始通知)。
    手順: NFD の日本語とバックスラッシュを含む `external_id` の文書を 1 件登録し、応答の
    `document_id`、OpenSearch の `_id`、保存された `external_id` を確かめる。

    【期待する結果とその根拠】
    - 応答の `document_id` とドキュメントの `_id` が、テスト側の算出値と一致する。Crawler は `last-seen`
      でこの規則どおりに ID を算出して渡すので、食い違いは同じ文書を指せなくなる(api 3.3、K58)。
    - 保存される `external_id` は正規化後(NFC、`/` 区切り)の値(arch 3.2。ハッシュの前に正規化する)。

    【fake では確認できず実機で確認する点】
    `document_id` が実 OpenSearch の `_id` として使われ(512 バイト以内)、ID 指定の取得で読めること。
    """
    external_id = "dir\\sub/" + unicodedata.normalize("NFD", "がぎぐ.txt")
    expected_document_id = compute_document_id(source_id, external_id)
    expected_stored_external_id = "dir/sub/" + unicodedata.normalize("NFC", "がぎぐ.txt")
    document: SourceDocument = text_document(external_id, "document id check")

    # クロールを開始して、1 件登録する
    crawl = crawler.begin(source_id, started_at=ago(minutes=1))
    results = crawl.register_ok([document])

    # 応答の document_id を確かめる
    assert results[0]["document_id"] == expected_document_id, (
        f"the returned document_id must match the independent implementation: {results[0]}"
    )

    # OpenSearch の _id と、保存された external_id を確かめる
    stored = opensearch.fetch(SEARCH_INDEX, expected_document_id)
    assert stored is not None, "the document must be stored under the expected _id"
    assert stored["_source"]["external_id"] == expected_stored_external_id, (
        f"external_id must be stored normalized: {stored['_source']['external_id']!r}"
    )


def test_leading_slash_and_case_give_distinct_document_ids_in_the_indexer(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    Indexer が、先頭の `/` を除去せず、大文字小文字を区別して `document_id` を算出すること。

    【前提と手順】
    前提: 専用の `source_id`。クロール開始済み。
    手順: `external_id` が `/a.txt`・`a.txt`・`A.txt` の 3 文書を、同じバッチで登録する。

    【期待する結果とその根拠】
    3 件の `document_id` がすべて異なり、それぞれテスト側の独立実装と一致する。OpenSearch にも 3 件が
    別々の文書として存在する(api 3.3、K58: 先頭の `/` は Crawler が渡す値の前提で、Indexer は除去しない。
    大文字小文字は区別したまま扱う)。

    【fake では確認できず実機で確認する点】
    実 OpenSearch の `_id` としても、3 つが別の文書になること。
    """
    external_ids = ["/a.txt", "a.txt", "A.txt"]
    documents = [
        text_document(external_id, f"body of {external_id}") for external_id in external_ids
    ]
    crawl = crawler.begin(source_id, started_at=ago(minutes=1))

    # 3 件を同じバッチで登録する
    results = crawl.register_ok(documents)

    returned_ids = [result["document_id"] for result in results]
    assert returned_ids == [compute_document_id(source_id, e) for e in external_ids], (
        f"the returned document_ids must match the independent implementation: {results}"
    )
    assert len(set(returned_ids)) == 3, f"the 3 document_ids must all differ: {returned_ids}"
    assert [r["change"] for r in results] == ["created"] * 3, f"3 separate documents: {results}"
    assert opensearch.count_source_documents(source_id) == 3, "3 documents must exist"


NORMALIZATION_CASES = [
    # (ケース名, external_id, 保存されるべき正規化後の external_id)
    (
        "nfd_only",
        unicodedata.normalize("NFD", "がぎぐ.txt"),
        unicodedata.normalize("NFC", "がぎぐ.txt"),
    ),
    ("backslash_only", "dir\\sub\\a.txt", "dir/sub/a.txt"),
]


@pytest.mark.parametrize(
    ("external_id", "expected_stored_external_id"),
    [case[1:] for case in NORMALIZATION_CASES],
    ids=[case[0] for case in NORMALIZATION_CASES],
)
def test_each_normalization_rule_alone_matches_the_independent_implementation(
    external_id: str,
    expected_stored_external_id: str,
    crawler: CrawlerClient,
    opensearch: OpenSearchProbe,
    source_id: str,
) -> None:
    """【何を確認するか】
    NFC 正規化だけ、`\\` → `/` の統一だけを、それぞれ単独で通した `external_id` でも、Indexer の
    `document_id` がテスト側の独立実装と一致すること(複合ケースだけだと、片方の規則の誤りが隠れうる)。

    【前提と手順】
    前提: 専用の `source_id`。クロール開始済み。
    手順: 規則 1 つだけに当たる `external_id` の文書を 1 件登録する。

    【期待する結果とその根拠】
    応答の `document_id` が独立実装と一致し、OpenSearch に同じ `_id` で保存され、保存される `external_id` は
    正規化後の値(api 3.3、arch 3.2)。

    【fake では確認できず実機で確認する点】
    正規化した `external_id` が実 OpenSearch の keyword に保存されること。
    """
    document = text_document(external_id, "single normalization rule")
    crawl = crawler.begin(source_id, started_at=ago(minutes=1))

    # 1 件登録して、応答と保存内容を確かめる
    result = crawl.register_ok([document])[0]

    expected_document_id = compute_document_id(source_id, external_id)
    assert result["document_id"] == expected_document_id, (
        f"the returned document_id must match the independent implementation: {result}"
    )
    stored = opensearch.fetch(SEARCH_INDEX, expected_document_id)
    assert stored is not None, "the document must be stored under the expected _id"
    assert stored["_source"]["external_id"] == expected_stored_external_id, (
        f"external_id must be stored normalized: {stored['_source']['external_id']!r}"
    )
