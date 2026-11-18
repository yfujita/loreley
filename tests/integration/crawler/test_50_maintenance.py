"""CIT-50: メンテナンスフラグ。

目的:
    `loreley-jobs` にメンテナンスフラグが立っていると、クロール起動が 409 `maintenance_enabled` で
    拒否され、ジョブ記録・ロックが作られないこと。フラグを下ろすとクロールを起動できることを確かめる。
    フラグは運用者が手動で書く(Crawler は読むだけ)。実 OpenSearch に書いた文書の形式を、Crawler が
    実際に読めることの確認でもある。

参照する設計書の章:
    - crawler-architecture-v0.4.md 7.9(メンテナンスフラグの読み取り。fail-closed)、4.3(受付の手順 2)
    - crawler-api-v0.4.md 4.1(クロール起動。409 `maintenance_enabled`)
    - apps/crawler/README.md 6 章(メンテナンスフラグ。形式: `loreley-jobs` の ID `maintenance`)

扱うシナリオ: CIT-50

注意: フラグが残ると、他のテストのクロール起動と、Indexer の削除判断が止まる。`try/finally` で
必ず削除し、削除したことも確認する。
"""

from support import (
    JOBS_INDEX,
    MAINTENANCE_RECORD_ID,
    CrawlerApi,
    OpenSearchProbe,
    SourceDirectory,
    expect_error,
    run_crawl,
)


def test_crawl_is_rejected_while_the_maintenance_flag_is_set(
    crawler_api: CrawlerApi, opensearch: OpenSearchProbe, registered_source: SourceDirectory
) -> None:
    """【何を確認するか】
    メンテナンスフラグが立っている間、クロール起動が 409 `maintenance_enabled` になり、ジョブ記録・ロックが
    作られないこと。フラグを削除すると、クロール起動が受け付けられ、`succeeded` まで進むこと。

    【前提と手順】
    前提: 登録済みのソースに `sample.txt` を 1 件置く。
    手順: フラグを書く(`{"record_type": "maintenance", "enabled": true}`。README 6 章の手順どおり)→
    クロール起動 → ジョブ記録・ロックを確認 → フラグを削除する(`finally`)→ クロール起動 → 完了を待つ。

    【期待する結果とその根拠】
    - フラグあり: 409 `maintenance_enabled`。受付は、設定を読んだ後、ロックを取る前にフラグを読んで
      拒否する(architecture 4.3 の手順 2)ので、`loreley-jobs` にこのソースのジョブ記録とロックは作られない。
      フラグは `enabled` が真偽値の `false` と明示されているとき以外は「立っている」とみなす(fail-closed。
      CA-K-18)ので、`enabled: true` は確実に「立っている」。
    - フラグ削除後: 文書がない(`found: false`)は「立っていない」(7.9)。クロール起動は 202 で、
      ジョブは `succeeded`。フラグの後始末が確実に効いたことの確認でもある。

    【fake では確認できず実機で確認する点】
    実 OpenSearch に運用者が書いたフラグの文書(README 6 章の形式)を、Crawler が実際に読んで判断すること。
    フラグがないとき、実 OpenSearch の 404(`found: false`)を「立っていない」と扱うこと。
    """
    registered_source.copy_sample("sample.txt")
    source_id = registered_source.source_id

    try:
        # フラグを立てて、クロールを起動する
        opensearch.set_maintenance_flag(enabled=True)
        response = crawler_api.start_crawl(source_id)

        expect_error(response, 409, "maintenance_enabled")
        assert opensearch.job_records_of(source_id) == [], "no job record may be created"
        assert opensearch.fetch_lock(source_id) is None, "no lock may be taken"
    finally:
        # 他のテストと Indexer の削除判断を止めないよう、必ず削除する
        opensearch.delete_maintenance_flag()

    assert opensearch.fetch(JOBS_INDEX, MAINTENANCE_RECORD_ID) is None, "the flag must be removed"

    # フラグを削除した後は、クロールが通る
    job = run_crawl(crawler_api, opensearch, source_id)

    assert job["registration"]["created_count"] == 1, f"the crawl must work: {job['registration']}"
