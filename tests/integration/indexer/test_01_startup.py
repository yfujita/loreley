"""IT-01: 起動疎通とスキーマ(compose で起動した直後の状態の確認)。

目的:
    compose(`opensearch` → `opensearch-init` → `indexer`)で立ち上げた Indexer が、実 OpenSearch に
    接続して起動時の整理を終え、`opensearch-init` が作ったスキーマの上で動いていることを確かめる。
    fake を使う単体テストでは、実 OpenSearch への接続と実マッピングの組み合わせを確認できない。

参照する設計書の章:
    - indexer-api-v0.10.md 1 章(`GET /healthz`。起動時の整理が終わるまでは受け付けない)
    - indexer-architecture-v0.10.md 9.8(起動時の整理)、12 章(起動順)
    - search-index-v0.10.md 4.1(マッピング。`dynamic: strict`)、5.2(エイリアス経由)
    - loreley-deletions-v0.10.md 7 章(`dynamic: strict`、`record_type`・`status`・`source_id` は keyword)
    - apps/indexer/README.md 5 章(起動順)、6 章(仮定義。`loreley-jobs`)

扱うシナリオ: IT-01
"""

from typing import Any

import httpx

from support import (
    DELETIONS_INDEX,
    JOBS_INDEX,
    SEARCH_INDEX,
    CrawlerClient,
    OpenSearchProbe,
    expect_error,
    expect_json,
)

CONCRETE_SEARCH_INDEX = "loreley-documents-000001"


def _fetch_mapping(opensearch: OpenSearchProbe, index: str) -> dict[str, Any]:
    """`GET /{index}/_mapping` の応答から、(エイリアスを解決した)実体の mappings を取り出す。"""
    response = opensearch.request("GET", f"/{index}/_mapping")
    body = expect_json(response, 200)
    assert len(body) == 1, f"{index} must resolve to exactly one concrete index: {list(body)}"
    return dict(next(iter(body.values()))["mappings"])


def test_healthz_returns_ok_after_the_startup_cleanup(indexer: httpx.Client) -> None:
    """【何を確認するか】
    Indexer が起動を完了し、`/healthz` が 200 `{"status": "ok"}` を返すこと。

    【前提と手順】
    前提: compose で起動済み(`opensearch-init` の完了後に `indexer` が起動する)。
    手順: `GET /healthz` を呼ぶ。

    【期待する結果とその根拠】
    200 と `{"status": "ok"}`。起動時の整理(`loreley-deletions` の読み取りと、再起動前に受理した削除
    結果の `failed` 化)が終わるまでは、`/healthz` を含むすべてのパスを受け付けない
    (api 1 章、README 5 章)。つまり 200 は、Indexer が実 OpenSearch に接続し、起動時の整理を
    完了した証拠になる。

    【fake では確認できず実機で確認する点】
    実 OpenSearch への接続(URL・タイムアウト・クライアント生成)と、実際の `loreley-deletions` に対する
    起動時の整理の読み取りが成功すること。
    """
    # ヘルスチェックを呼ぶ(起動が終わっていなければ、接続拒否か 503 になる)
    response = indexer.get("/healthz")

    body = expect_json(response, 200)
    assert body == {"status": "ok"}, f"/healthz must return only the status: {body}"


def test_indexer_reads_the_real_deletions_index(
    crawler: CrawlerClient,
) -> None:
    """【何を確認するか】
    起動直後の簡易な疎通確認として、`loreley-deletions` が実際に読めること(未知の `crawl_id` の Status が
    404 になる)。同じ 404 は IT-22(未知の `crawl_id`)でも確認する重複した確認で、ここでは「起動直後に
    索引を読めている」ことの確認に絞る。

    【前提と手順】
    前提: スタック起動済み。
    手順: 存在しない `crawl_id` で Status API を呼ぶ。

    【期待する結果とその根拠】
    404 `crawl_not_found`。索引が存在し、文書だけがない状態(実 OpenSearch の `found: false` の 404)を、
    Indexer が「記録なし」として扱えている(api 4.5)。

    【設計との関係(コードを確認した事実)】
    設計書の api 4.5 は、404 の条件に「`loreley-deletions` を失った場合」を含め、区別しないと定める
    (K66)。実装は、404 のうち、文書がない応答(`found: false` など)だけを「記録なし(404)」と分類し、
    索引そのものがない応答(`index_not_found_exception`)は OpenSearch 全体の異常として 503 `unavailable`
    にする(`infrastructure/opensearch/classification.py` の `UNAVAILABLE_ERROR_TYPES`)。
    「失った」が「索引は残るが記録が消えた」を指すなら一致する。「索引ごと失った」を指すなら、実装は
    404 ではなく 503 になるので、設計との差の可能性がある(このテストの範囲外。報告で扱う)。

    【fake では確認できず実機で確認する点】
    実 OpenSearch が返す 404 の本文の形を、Indexer が「文書なし」として正しく解釈すること。
    """
    # 存在しない crawl_id の Status を問い合わせる
    response = crawler.status("it-never-started-crawl")

    expect_error(response, 404, "crawl_not_found")


def test_search_index_is_reachable_through_the_alias_with_strict_mapping(
    opensearch: OpenSearchProbe,
) -> None:
    """【何を確認するか】
    検索インデックスが、エイリアス `loreley-documents` 経由で見えること。マッピングが
    `dynamic: strict` で、Indexer が書く主要項目が定義されていること。

    【前提と手順】
    前提: `opensearch-init` が実体 `loreley-documents-000001` とエイリアスを作成済み。
    手順: エイリアスの定義と、エイリアス経由のマッピングを読む。

    【期待する結果とその根拠】
    エイリアス `loreley-documents` が実体 1 つを指す(実体の名前そのものではない)。Indexer は
    設定の既定 `SEARCH_INDEX_NAME=loreley-documents` で読み書きするので、エイリアス経由で動く必要がある
    (search-index 5.2、README 3 章・6 章)。`dynamic: strict` は、定義にない項目の書き込みを
    OpenSearch に拒否させ、Indexer の書き込み項目の誤りを実機で検出できるようにする
    (search-index 4.1)。

    【fake では確認できず実機で確認する点】
    実際のマッピングの型(`last_seen_at` が date など)。fake はマッピングを持たない。
    """
    # エイリアスの定義を読む(エイリアスでなく実体の名前だった場合は 404 になる)
    alias_response = opensearch.request("GET", f"/_alias/{SEARCH_INDEX}")
    aliases = expect_json(alias_response, 200)
    assert list(aliases) == [CONCRETE_SEARCH_INDEX], (
        f"the alias {SEARCH_INDEX} must point to {CONCRETE_SEARCH_INDEX} only: {list(aliases)}"
    )

    # エイリアス経由でマッピングを読む
    mappings = _fetch_mapping(opensearch, SEARCH_INDEX)

    assert mappings["dynamic"] == "strict", (
        f"the search index must reject undefined fields (dynamic: strict): {mappings['dynamic']}"
    )
    properties = mappings["properties"]
    expected_types = {
        "document_id": "keyword",
        "source_id": "keyword",
        "content": "text",
        "text_hash": "keyword",
        "last_seen_at": "date",
        "indexed_at": "date",
        "source_updated_at": "date",
    }
    for field_name, expected_type in expected_types.items():
        assert properties[field_name]["type"] == expected_type, (
            f"{field_name} must be {expected_type}: {properties.get(field_name)}"
        )


def test_deletions_index_is_strict_and_jobs_index_is_tolerant(
    opensearch: OpenSearchProbe,
) -> None:
    """【何を確認するか】
    `loreley-deletions` が `dynamic: strict` で、Indexer が前提とする項目(`record_type`・`status`・
    `source_id`)が keyword であること。`loreley-jobs` が存在し、`dynamic: false` であること。

    【前提と手順】
    前提: `opensearch-init` が 3 つのインデックスを作成済み。
    手順: 各インデックスのマッピングを読む。

    【期待する結果とその根拠】
    - deletions は strict: Indexer が定義外の項目を書いたら実機で失敗として検出するため
      (loreley-deletions 7 章。infra/opensearch/schema/deletions.json の方針)。
    - `record_type`・`status`・`source_id` が keyword: 削除結果の検索・並べ替えの前提
      (arch 9.4、README 6 章の「マッピング」の仮定義)。
    - jobs は `dynamic: false`: Crawler の設計確定までは項目の追加を妨げない最小定義
      (README 6 章。結合テスト用の仮定義)。

    【fake では確認できず実機で確認する点】
    Indexer が実際に書く削除記録の全項目が、strict のマッピングに通ること(この確認自体は IT-20 以降の
    書き込みで成立する。ここでは定義の形だけを確認する)。
    """
    # deletions のマッピングを読む
    deletions = _fetch_mapping(opensearch, DELETIONS_INDEX)

    assert deletions["dynamic"] == "strict", (
        f"loreley-deletions must be strict to catch undefined fields: {deletions['dynamic']}"
    )
    for field_name in ("record_type", "status", "source_id"):
        assert deletions["properties"][field_name]["type"] == "keyword", (
            f"{field_name} must be a keyword: {deletions['properties'].get(field_name)}"
        )

    # jobs のマッピングを読む
    jobs = _fetch_mapping(opensearch, JOBS_INDEX)

    assert str(jobs["dynamic"]).lower() == "false", (
        f"loreley-jobs must tolerate unknown fields (dynamic: false): {jobs['dynamic']}"
    )
