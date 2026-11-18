"""CIT-30: 2 回目のクロールでの TTL 削除(消えたファイルの削除)。

目的:
    クロール A で登録した文書のうち、ファイルが消えたものが、クロール B の終了後に Indexer の Deletion
    Manager によって TTL 削除されること。ファイルが残っている文書は、Crawler の `last-seen`・登録が
    `last_seen_at` を更新するので、期限切れでも削除されずに残ること。削除の判断・実行は Indexer の責務で、
    Crawler は終了通知(列挙の完了と件数)を送って結果を確認するだけ(README 1 章)。

参照する設計書の章:
    - crawler-architecture-v0.4.md 4.6(`last-seen` → 取得 → バッチ登録)、7.5(終了通知)、7.6(削除結果の確認)
    - indexer-architecture-v0.10.md 9.3(分母 D)、9.6(件数照合)、9.7(削除判定の順序)、
      9.8(割合ルール `ratio_threshold`・`min_delete_count`)

扱うシナリオ: CIT-30
"""

from datetime import timedelta

from support import (
    EXPIRED_AGE,
    CrawlerApi,
    OpenSearchProbe,
    SourceDirectory,
    parse_instant,
    register_source,
    run_crawl,
    utc_now,
)

OLD_KEPT2_TEXT = "kept two old text oldmarkerzeta"
NEW_KEPT2_TEXT = "kept two new text newmarkereta"


def test_files_that_disappeared_are_deleted_and_the_files_that_remain_survive(
    crawler_api: CrawlerApi,
    opensearch: OpenSearchProbe,
    source_directory: SourceDirectory,
    other_source_directory: SourceDirectory,
) -> None:
    """【何を確認するか】
    クロール B の後、消えたファイル(gone1・gone2)の文書だけが削除され、残ったファイル(kept1・kept2・
    kept3)と新しいファイル(new1)の文書は残ること。kept2 は本文の変更が反映されること。別のソースの
    文書は、期限切れでも影響を受けないこと。

    【前提と手順】
    前提: ソース S(`ttl=600`、`ratio_threshold=0.5`、`min_delete_count=0`)に 5 ファイル(kept1・kept2・
    kept3・gone1・gone2)、別のソース O に 1 ファイル。
    手順:
      1. S・O をクロール A する(S は 5 件、O は 1 件が索引される)。
      2. **S と O の全文書の `last_seen_at` を 2 時間前に書き換える**(`force_last_seen_at`。実時間で待たずに
         「前回のクロールで見た文書が期限切れ」を作る。Crawler は `crawl_started_at` を自分の時計で決める
         ので、クロールの時刻を過去にはできない)。
      3. S の gone1・gone2 を消し、kept2 の本文を変え、new1 を足す。
      4. S をクロール B する。

    【期待する結果とその根拠】
    - 全文書が期限切れ(2 時間前 + `ttl` 600 秒 < 現在)の状態から、B が `last_seen_at` を更新した文書だけが
      残る。B で残る kept1・kept2・kept3・new1 は、Crawler の `last-seen`(kept1・kept3)と登録(kept2・
      new1)が `last_seen_at` を更新したから残る。更新されなかった gone1・gone2 が削除対象になる。
      つまり「残ること」は、Crawler が期限切れの前に `last_seen_at` を更新した証拠になる。
    - B の削除結果は `deleted`: `enumerated_count=4`(kept1・kept2・kept3・new1)、`n_seen=4`、`e_missing=0`、
      件数照合は 4 == 4 + 0。`target_count=2`(T: gone1・gone2)、`denominator=6`(D: 削除前の S の文書数 =
      5 + new1)、`deleted_count=2`。割合 T/D = 2/6 ≒ 0.33 は `ratio_threshold` 0.5 以下なので
      `skipped_by_ratio` にならない(境界値を避けている)。
    - 検索インデックス: gone1・gone2 は存在しない。kept1・kept2・kept3・new1 は存在する。kept2 の本文は新しい
      語で命中し、古い語では命中しない。残った文書の `last_seen_at` は 1 時間以内(書き換えた 2 時間前ではない)。
    - O の文書は残る(削除は `source_id` ごと。O は B の対象でなく、期限切れでも削除の判断が行われない)。

    【fake では確認できず実機で確認する点】
    実 Indexer の `last-seen`・バッチ登録・終了通知・Deletion Manager の削除と、Crawler の削除結果の
    ポーリングが、実 OpenSearch で通ること。実 Indexer の件数照合・割合ルールが、実際のクロールの件数で
    設計どおりの値になること。
    """
    source_id = source_directory.source_id
    other_source_id = other_source_directory.source_id
    for name in ("kept1.txt", "kept3.txt", "gone1.txt", "gone2.txt"):
        source_directory.write(name, f"text of {name} firstmarker".encode())
    source_directory.write("kept2.txt", OLD_KEPT2_TEXT.encode())
    other_source_directory.write("other1.txt", b"text of the other source")
    register_source(crawler_api, source_directory)
    register_source(crawler_api, other_source_directory)

    # 1. クロール A: S の 5 件と O の 1 件が索引される(TTL の期限内で、何も削除されない)
    job_a = run_crawl(crawler_api, opensearch, source_id)
    run_crawl(crawler_api, opensearch, other_source_id)
    assert job_a["registration"]["created_count"] == 5, f"A must create 5: {job_a['registration']}"
    assert opensearch.count_source_documents(source_id) == 5, "S must have 5 documents after A"

    # 2. 全文書の last_seen_at を 2 時間前にする(期限切れの状態を作る)
    expired_at = utc_now() - EXPIRED_AGE
    assert opensearch.force_last_seen_at(source_id, expired_at) == 5, "S: 5 documents"
    assert opensearch.force_last_seen_at(other_source_id, expired_at) == 1, "O: 1 document"

    # 3. gone1・gone2 を消し、kept2 の本文を変え、new1 を足す
    source_directory.remove("gone1.txt")
    source_directory.remove("gone2.txt")
    source_directory.write("kept2.txt", NEW_KEPT2_TEXT.encode())
    source_directory.write("new1.txt", b"text of new1 secondmarker")

    # 4. クロール B(終了通知の後、Indexer が削除し、Crawler が結果を確認するまで待つ)
    job_b = run_crawl(crawler_api, opensearch, source_id)

    result = opensearch.fetch_deletion_result(job_b["job_id"])
    assert result is not None, "the deletion result of B must exist in loreley-deletions"
    assert result["status"] == "deleted", (
        f"B must delete (not skipped_by_ratio or validation_failed): {result}"
    )
    assert (result["enumerated_count"], result["n_seen"], result["e_missing"]) == (4, 4, 0), (
        f"B: 4 enumerated = 4 seen + 0 missing: {result}"
    )
    assert (result["target_count"], result["denominator"], result["deleted_count"]) == (2, 6, 2), (
        f"B: T=2 (gone1, gone2), D=6 (5 + new1), deleted 2: {result}"
    )
    # 設定(ttl・割合ルール)が、Crawler から Indexer の削除判断に渡っている(architecture 12 #3)
    assert (result["ttl"], result["ratio_threshold"], result["min_delete_count"]) == (
        600,
        0.5,
        0,
    ), f"B: the source settings must reach the Indexer: {result}"
    registration_b = job_b["registration"]
    assert (registration_b["created_count"], registration_b["updated_count"]) == (1, 1), (
        f"B: new1 is created and kept2 is updated: {registration_b}"
    )
    # 削除される文書と残る文書
    for name in ("gone1.txt", "gone2.txt"):
        assert opensearch.fetch_document(source_id, name) is None, f"{name} must be deleted"
    for name in ("kept1.txt", "kept2.txt", "kept3.txt", "new1.txt"):
        document = opensearch.fetch_document(source_id, name)
        assert document is not None, f"{name} must remain"
        last_seen_at = parse_instant(document["last_seen_at"])
        assert last_seen_at > utc_now() - timedelta(hours=1), (
            f"{name} survives because the Crawler renewed last_seen_at, not the backdated one: "
            f"{document['last_seen_at']}"
        )
    assert opensearch.count_source_documents(source_id) == 4, "S must have 4 documents after B"
    new_hits = opensearch.search_content(source_id, "newmarkereta")
    assert [hit["_id"] for hit in new_hits] == [
        source_directory.external_id_to_document_id("kept2.txt")
    ], "kept2 must be searchable by its new text"
    assert opensearch.search_content(source_id, "oldmarkerzeta") == [], (
        "kept2 must no longer be searchable by its old text"
    )
    # 別のソースは影響を受けない
    assert opensearch.count_source_documents(other_source_id) == 1, (
        "the document of another source must remain even if it is expired"
    )
