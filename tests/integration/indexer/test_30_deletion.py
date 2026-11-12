"""IT-30・IT-31: 期限(TTL)による削除(終了通知を起点に、削除ワーカーが非同期に実行する)。

目的:
    クロール A(2 時間前開始)で複数の文書を登録し、クロール B(1 分前開始、`ttl=600`)で一部だけを見て
    終了通知を送ると、B で見なかった文書だけが削除され、見た文書は残ることを、実 OpenSearch で確認する。
    件数照合(`N_seen`・`E_missing`)・割合ルール(`T`・`D`)・分割実行(`search_after`、複数バッチ)が、
    設計書の定義どおりの値で Status API と記録に現れることも確かめる。

    実時間では待たない。`crawl_started_at` を過去に置いて「期限切れ」と「期限内」を決定的に作る
    (support.py の EXPIRED_AGE・RECENT_AGE・TTL_SECONDS)。待つのは、削除ワーカーの走査
    (compose.test.yaml で 1 秒間隔)だけで、Status を 0.5 秒間隔・上限 30 秒でポーリングする。

参照する設計書の章:
    - indexer-architecture-v0.10.md 9.2(期限による削除)、9.3(割合ルール。T・D の定義)、
      9.6(件数照合 `enumerated_count == N_seen + E_missing`)、9.7(削除判定の順序)、
      9.8(削除の実行。`search_after`、バッチ、TTL の再確認)、K31・K35(ID 一覧の保存と削除)、U-31(12)
    - indexer-api-v0.10.md 4.4(終了通知・件数照合)、4.5(Status API)、4.9(原本サイズ超過)
    - loreley-deletions-v0.10.md(`deletion_result` の項目)

扱うシナリオ: IT-30(TTL 削除)、IT-31(TTL 削除の分割実行)

期待値の定義(設計書 9.3・9.6 に基づく):
    - `N_seen` = 当該 `source_id` で `last_seen_at >= crawl_started_at`(B の開始時刻)の文書数。
    - `E_missing` = `skipped_document_ids` と `oversize_document_ids` の和集合のうち、索引にないものの数。
    - `T`(`target_count`)= `last_seen_at + TTL < 判定時刻` の文書数(スキップ文書を除く)。
    - `D`(`denominator`)= 削除前の同じ `source_id` の登録文書数(索引の件数。TTL の期限内の文書も含む)。
"""

from support import (
    DELETIONS_INDEX,
    LONG_TTL_SECONDS,
    SEARCH_INDEX,
    TTL_SECONDS,
    CrawlerClient,
    OpenSearchProbe,
    ago,
    oversize_document,
    sample_document,
    text_document,
)


def test_ttl_deletion_removes_only_documents_not_seen_by_the_latest_crawl(
    crawler: CrawlerClient,
    opensearch: OpenSearchProbe,
    source_id: str,
    other_source_id: str,
) -> None:
    """【何を確認するか】
    クロール B の終了通知後、B で見なかった(期限切れの)文書だけが削除され、B で見た文書(新規・変更・
    変更なし・抽出失敗)は残ること。Status の件数が設計書の定義どおりの値になること。他のソースの期限切れ
    文書は消えないこと。クロール A 自体の終了は、対象 0 件の `deleted` になること。

    【前提と手順】
    前提: すべて専用の `source_id`。
    クロール A(2 時間前開始、`ttl=1 日`)で 5 件(kept1・kept2・gone1・gone2・gone3)を登録して終了通知。
    別ソースにも、2 時間前の文書を 1 件登録する(期限切れだが、別ソースなので消えてはいけない)。
    クロール B(1 分前開始、`ttl=600`、`ratio_threshold=0.5`、`min_delete_count=0`)で、列挙した 5 件を
    `last-seen` → 登録 → 終了通知。
      - kept1: 変更なしで再登録(`unchanged`)
      - kept2: 本文を変更(`updated`)
      - new1: 新規(`created`)
      - new2: 原本サイズ超過の新規(`oversize`。索引に入らない。`oversize_document_ids` で終了通知に載せる)
      - new3: 壊れた PDF の新規(`extract_failed` として索引に入る)
      - gone1〜gone3: B では見ない(列挙されない)

    【期待する結果とその根拠】
    クロール A の結果: `deleted`、`deleted_count=0`、`target_count=0`、`n_seen=5`、`e_missing=0`
    (A の TTL が 1 日で、A が登録した文書は期限内。arch 9.7 の順 4「対象が 0 件なら deleted」)。

    クロール B の結果(`status=deleted`):
      - `enumerated_count=5`(Crawler が数えた列挙件数。new2 を含む)。
      - `n_seen=4`(`last_seen_at >= B の開始時刻` の文書: kept1・kept2・new1・new3。抽出失敗の new3 も
        索引にあるので数える。api 4.4)。
      - `e_missing=1`(`oversize_document_ids` の new2。索引にないので数える。arch 9.6)。
        件数照合 `5 == 4 + 1` が成立するので、削除の判断に進む。
      - `target_count=3`(gone1〜gone3。`last_seen_at` が 2 時間前で、`TTL=600 秒` を大きく過ぎる。
        kept・new は B の開始(1 分前)で更新済みで期限内)。
      - `denominator=7`(削除前の索引の件数: A が登録した 5 件 + B が登録した new1・new3。arch 9.3)。
      - `deleted_count=3`、`forced=false`。割合ルール: `T/D = 3/7 ≈ 0.43 ≤ 0.5`(しきい値)なので削除する
        (`skipped_by_ratio` にならない)。
    OpenSearch: gone1〜gone3 は消え、残りの 4 件(kept1・kept2・new1・new3)は残る。別ソースの文書は残る。
    終端状態の記録から、保存した ID 一覧(`oversize_document_ids` など)は消え、`finish_request_digest` は
    残る(arch K35)。

    【fake では確認できず実機で確認する点】
    実 OpenSearch での、削除対象の検索(`last_seen_at` の range、`source_id` の絞り込み)、`N_seen` の `_count`
    (refresh 後)、文書ごとの TTL 再確認と `if_seq_no` 付きの条件付き削除(`_seq_no` の実際の動作)、
    `deletion_result` の更新(strict マッピングへの全項目の書き込み)。
    """
    kept_unchanged = text_document("docs/kept-unchanged.txt", "kept document, same body")
    kept_updated = text_document("docs/kept-updated.txt", "kept document, first body")
    gone = [text_document(f"docs/gone-{i}.txt", f"gone document {i}") for i in (1, 2, 3)]
    new_document = text_document("docs/new.txt", "new document found by crawl B")
    new_oversize = oversize_document("docs/new-oversize.txt")
    new_corrupt = sample_document("corrupt.pdf", external_id="docs/new-corrupt.pdf")
    other_expired = text_document("docs/other-source-expired.txt", "expired but another source")

    # 別のソースに、2 時間前の文書を 1 件登録する(クロールは終了させない)
    other_crawl = crawler.begin(other_source_id, started_at=ago(hours=2))
    other_crawl.register_ok([other_expired])

    # クロール A(2 時間前、TTL 1 日)で 5 件を登録して終了する: 対象 0 件の deleted になる
    crawl_a = crawler.begin(source_id, started_at=ago(hours=2), ttl=LONG_TTL_SECONDS)
    crawl_a.register_ok([kept_unchanged, kept_updated, *gone])
    result_a = crawl_a.finish_and_wait(enumerated_count=5)
    assert result_a["status"] == "deleted", f"crawl A must end as deleted: {result_a}"
    assert result_a["target_count"] == 0, f"crawl A's documents are within its TTL: {result_a}"
    assert result_a["deleted_count"] == 0, f"nothing may be deleted by crawl A: {result_a}"
    assert (result_a["n_seen"], result_a["e_missing"]) == (5, 0), f"A's reconciliation: {result_a}"
    assert opensearch.count_source_documents(source_id) == 5, "all 5 documents must remain"

    # クロール B(1 分前、TTL 600 秒)を開始する
    crawl_b = crawler.begin(
        source_id,
        started_at=ago(minutes=1),
        ttl=TTL_SECONDS,
        ratio_threshold=0.5,
        min_delete_count=0,
    )

    # B で列挙した 5 件を、取得より前に last-seen する(既存は updated、新規は not_found)
    enumerated = [kept_unchanged, kept_updated, new_document, new_oversize, new_corrupt]
    seen = crawl_b.last_seen_ok([d.document_id(source_id) for d in enumerated])
    assert [r["result"] for r in seen] == [
        "updated",
        "updated",
        "not_found",
        "not_found",
        "not_found",
    ], f"existing documents are updated and new ones are not_found: {seen}"

    # B で 5 件を登録する(変更なし・変更・新規・サイズ超過・抽出失敗)
    registered = crawl_b.register_ok(
        [kept_unchanged, kept_updated.with_raw(b"kept document, second body"), *enumerated[2:]]
    )
    outcomes = [(r["status"], r.get("change") or r.get("failure_type")) for r in registered]
    assert outcomes == [
        ("ok", "unchanged"),
        ("ok", "updated"),
        ("ok", "created"),
        ("failed", "oversize"),
        ("ok", "created"),
    ], f"unexpected registration results: {registered}"
    assert registered[4]["extract_failed"] is True, (
        f"the corrupt PDF must fail extraction: {registered}"
    )

    # B の終了通知を送る(サイズ超過の ID を oversize_document_ids に載せる)。削除の完了を待つ
    result_b = crawl_b.finish_and_wait(
        enumerated_count=5, oversize_document_ids=[new_oversize.document_id(source_id)]
    )

    # Status: 件数照合と削除の結果が、設計書の定義どおりの値になっている
    assert result_b["status"] == "deleted", f"crawl B must end as deleted: {result_b}"
    assert result_b["enumerated_count"] == 5, f"enumerated_count: {result_b}"
    assert result_b["n_seen"] == 4, f"N_seen = kept1, kept2, new1 and new3: {result_b}"
    assert result_b["e_missing"] == 1, f"E_missing = the oversize new document: {result_b}"
    assert result_b["target_count"] == 3, f"T = gone1..gone3: {result_b}"
    assert result_b["denominator"] == 7, f"D = documents before deletion (5 + 2 new): {result_b}"
    assert result_b["deleted_count"] == 3, f"all 3 targets must be deleted: {result_b}"
    assert result_b["forced"] is False, f"this is not a forced deletion: {result_b}"
    assert result_b["ttl"] == TTL_SECONDS, f"the snapshot's ttl must be returned: {result_b}"

    # OpenSearch: B で見なかった 3 件だけが消え、見た 4 件は残る
    for document in gone:
        assert opensearch.fetch_document(source_id, document.external_id) is None, (
            f"{document.external_id} was not seen by crawl B and must be deleted"
        )
    for document in (kept_unchanged, kept_updated, new_document, new_corrupt):
        assert opensearch.fetch_document(source_id, document.external_id) is not None, (
            f"{document.external_id} was seen by crawl B and must remain"
        )
    assert opensearch.count_source_documents(source_id) == 4, "exactly the 4 seen documents remain"

    # 他のソースの期限切れ文書は、削除の対象にならない
    assert opensearch.fetch_document(other_source_id, other_expired.external_id) is not None, (
        "an expired document of another source must not be deleted"
    )

    # 終端状態の記録: 保存した ID 一覧は消え、終了通知のダイジェストは残る(arch K35)
    record = opensearch.fetch_source(DELETIONS_INDEX, f"deletion_result-{crawl_b.crawl_id}")
    assert record is not None, "the deletion result must exist"
    assert "oversize_document_ids" not in record, f"stored id lists must be removed: {record}"
    assert "skipped_document_ids" not in record, f"stored id lists must be removed: {record}"
    assert "finish_request_digest" in record, f"the digest must remain: {record}"


# IT-31 の削除対象の件数。SEARCH_AFTER_PAGE_SIZE=2 なら 11 ページ(2 件ずつ 10 回 + 1 件)になる。
GONE_COUNT = 21


def test_ttl_deletion_runs_in_multiple_batches_and_pages(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    削除対象が `DELETION_BATCH_SIZE`(2)と `SEARCH_AFTER_PAGE_SIZE`(2)よりはるかに多いとき、
    複数ページの取り込みと複数バッチの削除が漏れ・重複なく完了し、`deleted_count` が対象件数と一致すること。

    【前提と手順】
    前提: Indexer は compose.test.yaml の `DELETION_BATCH_SIZE=2`・`SEARCH_AFTER_PAGE_SIZE=2` で起動している
    (対象 21 件は、11 ページ・11 バッチになる)。
    クロール A(2 時間前開始、`ttl=1 日`)で 22 件(kept 1 件 + gone 21 件)を登録して終了通知。
    クロール B(1 分前開始、`ttl=600`、`min_delete_count=100`)で kept だけを見て終了通知。

    【期待する結果とその根拠】
    - `status=deleted`、`target_count=21`、`deleted_count=21`、`denominator=22`。
      T = gone の 21 件(A の開始が 2 時間前で TTL 600 秒を過ぎ、kept だけが B で更新される)、
      D = 削除前の同ソースの登録数 22 件(arch 9.3)。
      対象は `document_id` の昇順ソートの `search_after` で、全 ID を取りこぼし・重複なく取り込む
      (arch 9.8、K47、U-31(12))。ページが分かれても件数が合うことが、その確認になる。
    - 割合ルールは `T/D = 21/22 > 0.5` だが、`T=21 ≤ min_delete_count=100` なので、最小件数ルールで削除する
      (arch 9.3 の判定 1「T が最小件数以下なら、率に関わらず削除する」)。ここは割合ルールの確認ではなく、
      分割実行の確認なので、削除されるように設定している。
    - 索引には kept の 1 件だけが残る。
    - **ページ数の実測**: 終了通知から削除完了までの、検索インデックスの `query_total`(検索の累計回数)の
      差分が 10 以上。`query_total` は索引の統計 `GET /loreley-documents/_stats/search` から読む。この間にテストが
      検索インデックスを検索することはない(Status API は `loreley-deletions` を読む)。差分の内訳は、`N_seen` の
      `_count` 1 回、D の `_count` 1 回、`search_after` のページ 11 回(2 件ずつ 10 回 + 1 件)で、
      **実測は 13**(`_count` 2 回 + ページ 11 回。4 回の実行で同じ値)。
      ページサイズが既定の 1,000 に戻っていれば、ページは 1 回で、差分は 3 程度になる(**この値は未実測の
      推定**。以前の 7 件の構成で実測した 6 = `_count` 2 回 + ページ 4 回、からの推定)。したがって `>= 10`
      で落ちる。`>=` なのは、Indexer が他の用途で検索することがあっても落ちないため。
      Settings は未知の環境変数を無視する(`extra="ignore"`)ので、環境変数名を誤ると既定値に黙って戻る。
      この assert が、`SEARCH_AFTER_PAGE_SIZE` の設定が効いていることの確認になる。

    【この確認の限界(バッチ数)】
    `DELETION_BATCH_SIZE=2` が効いていること(11 バッチ)は、API・ログ・統計のどれでも直接観測できない。
    バッチ数は設定値と件数からの推定で、バッチサイズの設定が効いていなくても、このテストは通る。
    一方、全 gone 文書の `last_seen_at` は同値(クロール A の開始時刻)なので、`search_after` の
    ソートが `document_id` の tiebreak を欠く実装なら、ページ境界で取りこぼし・重複が出て、
    `deleted_count == 21` や索引の残り 1 件のどちらかで落ちる。

    【fake では確認できず実機で確認する点】
    実際の `search_after`(`document_id` の昇順ソート、`keyword` 型のソート)の複数ページの動作、
    複数バッチの条件付き削除(`if_seq_no`)、バッチごとの `deleted_count` の記録(条件付き更新)。
    """
    kept = text_document("docs/kept.txt", "kept document")
    gone = [text_document(f"docs/gone-{i}.txt", f"gone document {i}") for i in range(GONE_COUNT)]
    total = 1 + GONE_COUNT

    # クロール A(2 時間前、TTL 1 日)で 22 件を登録して終了する
    crawl_a = crawler.begin(source_id, started_at=ago(hours=2), ttl=LONG_TTL_SECONDS)
    crawl_a.register_ok([kept, *gone])
    assert crawl_a.finish_and_wait(enumerated_count=total)["target_count"] == 0, "A deletes nothing"

    # クロール B(1 分前、TTL 600 秒)で kept だけを見る
    crawl_b = crawler.begin(
        source_id,
        started_at=ago(minutes=1),
        ttl=TTL_SECONDS,
        ratio_threshold=0.5,
        min_delete_count=100,
    )
    crawl_b.last_seen_ok([kept.document_id(source_id)])
    assert crawl_b.register_ok([kept])[0]["change"] == "unchanged", "kept is unchanged"
    # 終了通知から削除完了までの間に Indexer が行う検索の回数を、索引の統計の差分で測る
    # (この間にテストが検索インデックスを検索することはない。Status API は deletions を読む)
    stats_before = opensearch.search_stats(SEARCH_INDEX)
    result = crawl_b.finish_and_wait(enumerated_count=1)
    stats_after = opensearch.search_stats(SEARCH_INDEX)
    searches = stats_after["query_total"] - stats_before["query_total"]

    # 21 件が 11 ページ・11 バッチに分かれて、漏れなく削除される
    assert result["status"] == "deleted", f"the deletion must complete: {result}"
    assert result["target_count"] == GONE_COUNT, f"T = the gone documents: {result}"
    assert result["denominator"] == total, f"D = documents before deletion: {result}"
    assert result["deleted_count"] == GONE_COUNT, f"every target must be deleted once: {result}"
    assert searches >= 10, (
        f"{GONE_COUNT} targets with SEARCH_AFTER_PAGE_SIZE=2 need 11 search_after pages "
        f"(page size 1000 would give about 1): {searches} searches in total"
    )
    assert opensearch.count_source_documents(source_id) == 1, "only the kept document remains"
    assert opensearch.fetch_document(source_id, kept.external_id) is not None, (
        "the kept document must remain"
    )
