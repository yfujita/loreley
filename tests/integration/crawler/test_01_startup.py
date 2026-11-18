"""CIT-01: 起動疎通とスキーマ(compose で起動した直後の状態の確認)。

目的:
    compose(`opensearch` → `opensearch-init` → `indexer` → `crawler`)で立ち上げた Crawler が、実
    OpenSearch に接続して起動時の回復を終え、`opensearch-init` が作ったスキーマの上で動いていることを
    確かめる。fake を使う単体テストでは、実 OpenSearch への接続と実マッピングの組み合わせ、実コンテナの
    起動順を確認できない。

参照する設計書の章:
    - crawler-api-v0.4.md 4.7(`GET /healthz`。契約外の運用 API)
    - crawler-architecture-v0.4.md 3.1(`loreley-sources`・`loreley-jobs` のマッピング案)、
      5.8(起動時の回復)、10 章(起動順)
    - apps/crawler/README.md 3 章(Docker)、6 章(起動順。回復が終わるまで接続できない)、9 章(infra の前提作業)

扱うシナリオ: CIT-01
"""

from typing import Any

from support import (
    DELETIONS_INDEX,
    JOBS_INDEX,
    SEARCH_INDEX,
    SOURCES_INDEX,
    CrawlerApi,
    OpenSearchProbe,
    expect_json,
)


def _fetch_mapping(opensearch: OpenSearchProbe, index: str) -> dict[str, Any]:
    """`GET /{index}/_mapping` の応答から、(エイリアスを解決した)実体の mappings を取り出す。"""
    body = expect_json(opensearch.request("GET", f"/{index}/_mapping"), 200)
    assert len(body) == 1, f"{index} must resolve to exactly one concrete index: {list(body)}"
    return dict(next(iter(body.values()))["mappings"])


def test_crawler_is_healthy_after_the_startup_recovery(crawler_api: CrawlerApi) -> None:
    """【何を確認するか】
    Crawler が起動を完了し、`/healthz` が 200 `{"status": "ok"}` を返すこと。

    【前提と手順】
    前提: compose で起動済み(`opensearch-init` の完了と `indexer` の healthy の後に `crawler` が起動する)。
    手順: `GET /healthz` を呼ぶ。

    【期待する結果とその根拠】
    200 と `{"status": "ok"}`。Crawler は、起動時の回復(OpenSearch への読み書き)が終わるまで HTTP を
    開かない(README 6 章)ので、接続できて 200 が返ること自体が、実 OpenSearch に接続して回復を終えた
    証拠になる。内部情報(版・設定・ジョブの状態)は返さない(api 4.7)。

    【fake では確認できず実機で確認する点】
    実 OpenSearch・実コンテナでの起動順と、イメージの `HEALTHCHECK` が通ること(起動の待機は、スクリプトが
    `healthy` を待つ)。
    """
    # ヘルスチェックを呼ぶ(起動が終わっていなければ、接続拒否になる)
    response = crawler_api.healthz()

    body = expect_json(response, 200)
    assert body == {"status": "ok"}, f"/healthz must return only the status: {body}"


def test_all_four_indices_exist_and_the_search_index_is_an_alias(
    opensearch: OpenSearchProbe,
) -> None:
    """【何を確認するか】
    Crawler・Indexer が使う 4 つの索引(`loreley-documents`・`loreley-deletions`・`loreley-jobs`・
    `loreley-sources`)が存在し、検索インデックスがエイリアスであること。

    【前提と手順】
    前提: `opensearch-init` が 4 つを作成済み。
    手順: 各索引のマッピングを読む。検索インデックスは、エイリアスの定義も読む。

    【期待する結果とその根拠】
    - `loreley-sources` が存在する: Crawler は索引を作らない(README 1 章)。作るのは `opensearch-init`
      (README 9 章)で、無いまま Crawler が書くと、動的マッピングの別の索引ができうる。
    - 検索インデックスは、エイリアスが実体 1 つを指す(実体の名前そのものではない)。

    【fake では確認できず実機で確認する点】
    `opensearch-init` が `loreley-sources` を実際に作ること(フェーズ 1 の変更)。
    """
    # 3 つの通常の索引: 存在すれば 200 で、実体 1 つのマッピングが返る
    for index in (DELETIONS_INDEX, JOBS_INDEX, SOURCES_INDEX):
        mappings = _fetch_mapping(opensearch, index)
        assert "properties" in mappings, f"{index} must have a mapping: {mappings}"

    # 検索インデックス: エイリアスが実体 1 つを指す
    aliases = expect_json(opensearch.request("GET", f"/_alias/{SEARCH_INDEX}"), 200)
    assert len(aliases) == 1, f"the alias {SEARCH_INDEX} must point to one index: {list(aliases)}"
    assert next(iter(aliases)) != SEARCH_INDEX, f"{SEARCH_INDEX} must be an alias: {list(aliases)}"


def test_sources_index_is_strict_and_jobs_index_defines_the_fields_crawler_queries(
    opensearch: OpenSearchProbe,
) -> None:
    """【何を確認するか】
    `loreley-sources` が `dynamic: strict` で、データソース設定の項目の型が定義されていること。
    `loreley-jobs` が `dynamic: false` で、Crawler が絞り込み・並べ替えに使う項目(`record_type`・
    `status`・`source_id`・`queued_at` など)と、Indexer が読む 4 項目が定義されていること。

    【前提と手順】
    前提: `opensearch-init` が作成済み。
    手順: 各索引のマッピングを読む。

    【期待する結果とその根拠】
    - sources は strict: 定義にない項目の書き込みを OpenSearch に拒否させ、Crawler の書き込み項目の誤りを
      実機で検出するため(architecture 3.1)。`ratio_threshold` は double(整数で始まる値から動的に
      long と推定されないため、定義が要る。README 9 章)、`connector_config` は索引しない object。
    - jobs は `dynamic: false`: 項目の追加を妨げない(未定義の項目は索引せず保存する)。Crawler は
      `record_type`・`status`・`source_id`・`queued_at` で記録を絞り込み・並べ替えるので、これらが
      定義されていないと、Job Runner の `queued` ジョブの検出などが動かない(README 9 章)。
    - Indexer が読む 4 項目(`owner`・`job_id` は keyword、`lease_expires_at` は date、`enabled` は
      boolean)の型は、拡張しても変わらない。

    【fake では確認できず実機で確認する点】
    実際のマッピングの型。fake の Repository はマッピングを持たない。
    """
    # sources のマッピングを読む
    sources = _fetch_mapping(opensearch, SOURCES_INDEX)

    assert sources["dynamic"] == "strict", (
        f"loreley-sources must reject undefined fields (dynamic: strict): {sources['dynamic']}"
    )
    source_types = {
        "source_id": "keyword",
        "connector_type": "keyword",
        "status": "keyword",
        "schedule_cron": "keyword",
        "ttl": "long",
        "min_delete_count": "long",
        "ratio_threshold": "double",
        "updated_at": "date",
    }
    for field_name, expected_type in source_types.items():
        assert sources["properties"][field_name]["type"] == expected_type, (
            f"loreley-sources.{field_name} must be {expected_type}: "
            f"{sources['properties'].get(field_name)}"
        )
    connector_config = sources["properties"]["connector_config"]
    assert connector_config.get("enabled") is False, (
        f"connector_config must not be indexed (enabled: false): {connector_config}"
    )

    # jobs のマッピングを読む
    jobs = _fetch_mapping(opensearch, JOBS_INDEX)

    assert str(jobs["dynamic"]).lower() == "false", (
        f"loreley-jobs must tolerate unknown fields (dynamic: false): {jobs['dynamic']}"
    )
    job_types = {
        # Indexer が読む 4 項目(型は変えない)
        "owner": "keyword",
        "job_id": "keyword",
        "lease_expires_at": "date",
        "enabled": "boolean",
        # Crawler が絞り込み・並べ替えに使う項目(architecture 3.1)
        "record_type": "keyword",
        "source_id": "keyword",
        "job_type": "keyword",
        "status": "keyword",
        "document_id": "keyword",
        "queued_at": "date",
    }
    for field_name, expected_type in job_types.items():
        assert jobs["properties"][field_name]["type"] == expected_type, (
            f"loreley-jobs.{field_name} must be {expected_type}: "
            f"{jobs['properties'].get(field_name)}"
        )
