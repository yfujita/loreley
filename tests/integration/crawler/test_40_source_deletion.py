"""CIT-40: ソース削除ジョブ(`POST /sources/{source_id}/delete-jobs`)。

目的:
    ソース削除ジョブ(順 0〜6)が、実 OpenSearch・実 Indexer に対して最後まで通り、削除したソースの
    データ(Indexer 側の文書・削除記録、Crawler 側の原本サイズ超過記録・設定)がすべて消え、別のソースの
    データは残ることを確かめる。不可逆なデータ削除なので、削除の範囲が他のソースに及ばないことを重視する。

参照する設計書の章:
    - crawler-architecture-v0.4.md 8.1(ソース削除ジョブの順 0〜6)、8.3(再実行)
    - crawler-api-v0.4.md 4.6(ソース削除ジョブ起動)、4.1(削除後のクロール起動は 404)
    - indexer-api-v0.10.md 4.6〜4.8(ソース削除 1〜3。`discard`・文書の全削除・削除記録の削除)
    - apps/crawler/README.md 8 章(実 Indexer が必要な項目: DELETE のボディの `lock`)

扱うシナリオ: CIT-40
"""

from support import (
    JOBS_INDEX,
    OVERSIZE_RAW_BYTES,
    CrawlerApi,
    OpenSearchProbe,
    SourceDirectory,
    expect_error,
    register_source,
    run_crawl,
    run_source_delete,
    wait_for_lock_released,
)


def _fill_source(directory: SourceDirectory) -> None:
    """通常のファイル(`sample.txt`・`sample.md`)と、原本サイズ超過のファイル(`big.txt`)を置く。"""
    directory.copy_sample("sample.txt")
    directory.copy_sample("sample.md")
    directory.write("big.txt", b"x" * OVERSIZE_RAW_BYTES)


def test_source_delete_removes_everything_of_the_source_and_leaves_the_other_source(
    crawler_api: CrawlerApi,
    opensearch: OpenSearchProbe,
    source_directory: SourceDirectory,
    other_source_directory: SourceDirectory,
) -> None:
    """【何を確認するか】
    ソース S のソース削除ジョブが `succeeded` で終わり、S の文書・Indexer の削除記録・原本サイズ超過記録・
    設定・ロックがすべて消えること。別のソース O の文書・記録・設定は残ること。削除後の S へのクロール起動が
    404 になること。

    【前提と手順】
    前提: S・O のどちらにも、通常のファイル 2 件と原本サイズ超過のファイル 1 件を置いて登録し、クロール済み
    (文書 2 件、`deletion-*`・`deletion_result-*`、`oversize-*` 記録、設定がある)。
    手順: 削除前の状態を確認 → S に `POST .../delete-jobs`(202)→ `succeeded` を待つ → S と O の状態を
    OpenSearch から直接読む → S のクロール起動を試みる。

    【期待する結果とその根拠】
    - ソース削除ジョブは `succeeded`。順 0 で設定を `deleting` にし、順 1(Indexer の破棄)、順 2(文書の全削除)、
      順 3(S の `skip`・`oversize` 記録の削除)、順 4(Indexer の削除記録の削除)、順 5(設定の削除)、順 6
      (最終状態)の順に進む(architecture 8.1)。DELETE のボディの `lock`(所有情報)が実 Indexer に
      受理されることも、`succeeded` が示す(受理されなければ `lock_not_owned` で `failed` になる)。
    - S: 検索インデックスの文書 0 件、`loreley-deletions` の S の記録が 0 件、`loreley-jobs` の S の
      `oversize` 記録が 0 件、`loreley-sources` の S の設定がなし、ロック文書 `lock-S` なし(ジョブの終了後に
      Job Runner が解放する。有限のポーリングで待つ)。
    - O: 文書 2 件、`loreley-deletions` の記録(`deletion-O`・`deletion_result-*`)、`oversize` 記録 1 件、
      設定がすべて残る(削除は `source_id` ごと。architecture 8.1・Indexer arch 9.14)。
    - 削除後の S のクロール起動は 404 `source_config_not_found`(設定がない。api 4.1)。

    【fake では確認できず実機で確認する点】
    実 Indexer のソース削除 1〜3(特に `delete_by_query` と、DELETE への JSON ボディの `lock`)、
    実 OpenSearch での `skip`・`oversize` 記録のソース単位の削除(全件走査とバルク削除)、
    ジョブの終了後のロックの解放。
    """
    source_id = source_directory.source_id
    other_source_id = other_source_directory.source_id
    _fill_source(source_directory)
    _fill_source(other_source_directory)
    register_source(crawler_api, source_directory)
    register_source(crawler_api, other_source_directory)
    crawl_job_s = run_crawl(crawler_api, opensearch, source_id)
    crawl_job_o = run_crawl(crawler_api, opensearch, other_source_id)

    # 削除前の状態: S・O とも、文書・Indexer の記録・oversize 記録・設定がある(前提の確認)
    for target in (source_id, other_source_id):
        assert opensearch.count_source_documents(target) == 2, f"{target}: 2 documents"
        assert opensearch.deletion_records_of(target), f"{target}: deletion records exist"
        assert len(opensearch.oversize_records(target)) == 1, f"{target}: 1 oversize record"
        assert opensearch.fetch_source_config(target) is not None, f"{target}: config exists"

    # S のソース削除ジョブを起動して、完了(succeeded)を待つ
    delete_job = run_source_delete(crawler_api, opensearch, source_id)

    assert delete_job["job_type"] == "source_delete", (
        f"job_type must be source_delete: {delete_job}"
    )
    assert opensearch.count_source_documents(source_id) == 0, "S: no document may remain"
    assert opensearch.deletion_records_of(source_id) == [], "S: Indexer's records must be gone"
    assert opensearch.fetch_deletion_result(crawl_job_s["job_id"]) is None, (
        "S: the deletion result of its crawl must be gone"
    )
    assert opensearch.oversize_records(source_id) == [], "S: oversize records must be gone"
    assert opensearch.fetch_source_config(source_id) is None, "S: the configuration must be gone"
    wait_for_lock_released(opensearch, source_id)

    # O は影響を受けない
    assert opensearch.count_source_documents(other_source_id) == 2, "O: documents must remain"
    assert opensearch.fetch_source(JOBS_INDEX, crawl_job_o["job_id"]) is not None, (
        "O: its job record must remain"
    )
    assert opensearch.fetch_deletion_result(crawl_job_o["job_id"]) is not None, (
        "O: the deletion result must remain"
    )
    assert len(opensearch.oversize_records(other_source_id)) == 1, "O: oversize record must remain"
    assert opensearch.fetch_source_config(other_source_id) is not None, (
        "O: the configuration must remain"
    )

    # 削除後の S のクロール起動は拒否される(設定がない)
    expect_error(crawler_api.start_crawl(source_id), 404, "source_config_not_found")
