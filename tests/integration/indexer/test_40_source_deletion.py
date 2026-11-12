"""IT-40〜IT-42: ソース削除(Crawler がソースを削除するときの 3 つの要請)。

目的:
    ソース削除ジョブが順に呼ぶ 3 つの API を、実 OpenSearch に対して確かめる。
      1. `POST /sources/{source_id}/deletions:discard`(終端でない削除結果を `discarded` にする)
      2. `DELETE /sources/{source_id}/documents`(`delete_by_query` でソースの文書をすべて削除する)
      3. `DELETE /sources/{source_id}/deletion-records`(`loreley-deletions` の記録を削除する)
    いずれも再実行できる(冪等)こと、他のソースに影響しないことを確認する。
    DELETE にロック所有情報を JSON ボディで載せる運び方(api 3.2)が、実際の HTTP で通ることの確認でもある。

参照する設計書の章:
    - indexer-api-v0.10.md 3.2(`lock` の運び方。DELETE も JSON ボディ)、4.6〜4.8(ソース削除 1〜3)
    - indexer-architecture-v0.10.md 9.14(データソースの削除)、K20・K28(`delete_by_query` と
      実行前 refresh・完了後 `_count`)、K60・K61(`lock` の所有確認)、U-31(5)(11)
    - apps/indexer/README.md 6 章(DELETE は `lock` を JSON ボディで運ぶ)

扱うシナリオ: IT-40(ソース削除 1)、IT-41(ソース削除 2)、IT-42(ソース削除 3)
"""

from support import (
    DELETIONS_INDEX,
    SEARCH_INDEX,
    CrawlerClient,
    Lock,
    OpenSearchProbe,
    ago,
    expect_error,
    expect_json,
    text_document,
)


def test_discard_marks_unfinished_results_as_discarded_and_is_idempotent(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str, other_source_id: str
) -> None:
    """【何を確認するか】
    ソース削除 1 が、そのソースの終端状態でない削除結果(`running`)を `discarded`(理由
    `source_deleted`)にして `discarded_crawl_ids` で返すこと。すでに終端状態の結果と、他のソースの結果には
    触れないこと。再実行は空の一覧を返すこと(冪等)。

    【前提と手順】
    前提: 専用の `source_id`。そのソースの過去のクロール C0(`deleted` で終了済み)と、終了通知前の
    クロール C1(`running`)。別のソースにも終了通知前のクロール(`running`)。
    手順: ソース削除 1 を呼ぶ → 各クロールの Status を確認 → もう一度呼ぶ。

    【期待する結果とその根拠】
    - 200 `{"discarded_crawl_ids": [C1]}`(終端状態でない結果だけが対象。api 4.6、arch 9.14)。
    - C1 の Status は `discarded`・`reason=source_deleted`・`finished_at` あり(arch 9.10)。
      `loreley-deletions` の記録を直接読んでも、同じ `status`・`reason`。
    - C0 は `deleted` のまま、別ソースのクロールは `running` のまま(対象はこのソースの終端でない結果だけ)。
    - 再実行は `{"discarded_crawl_ids": []}`(破棄済みで、対象がない。api 4.6「何度でも再実行できる」)。

    【fake では確認できず実機で確認する点】
    実 OpenSearch での、終端でない削除結果の一覧(`loreley-deletions` の `record_type`・`status`・`source_id`
    の term 検索)と、`if_seq_no` の条件付き更新による `discarded` の書き込み。
    """
    # C0: このソースの過去のクロール。終了して `deleted` になっている
    crawl0 = crawler.begin(source_id, started_at=ago(hours=2))
    crawl0.register_ok([text_document("docs/old.txt", "old")])
    assert crawl0.finish_and_wait(enumerated_count=1)["status"] == "deleted", "C0 must be terminal"

    # C1: 終了通知前のクロール(running)。別のソースにも running のクロールを置く
    crawl1 = crawler.begin(source_id, started_at=ago(minutes=1))
    other_crawl = crawler.begin(other_source_id, started_at=ago(minutes=1))

    # ソース削除 1 を呼ぶ
    body = expect_json(crawler.discard(source_id, crawl1.lock), 200)

    assert body == {"discarded_crawl_ids": [crawl1.crawl_id]}, (
        f"only the unfinished result of this source must be discarded: {body}"
    )
    discarded = crawl1.status()
    assert (discarded["status"], discarded["reason"]) == ("discarded", "source_deleted"), (
        f"C1 must be discarded with the reason source_deleted: {discarded}"
    )
    assert "finished_at" in discarded, f"a terminal result must have finished_at: {discarded}"
    # Status API だけに頼らず、`loreley-deletions` の記録を直接読んで確認する
    stored = opensearch.fetch_source(DELETIONS_INDEX, f"deletion_result-{crawl1.crawl_id}")
    assert stored is not None, "the discarded result must still exist in loreley-deletions"
    assert (stored["status"], stored["reason"]) == ("discarded", "source_deleted"), (
        f"the stored result must be discarded with the reason source_deleted: {stored}"
    )
    assert crawl0.status()["status"] == "deleted", "a terminal result must not be touched"
    assert other_crawl.status()["status"] == "running", "another source must not be affected"

    # もう一度呼ぶ: 対象がないので空(冪等)
    again = expect_json(crawler.discard(source_id, crawl1.lock), 200)
    assert again == {"discarded_crawl_ids": []}, f"a rerun must find nothing to discard: {again}"


def test_delete_documents_removes_all_documents_of_the_source_only(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str, other_source_id: str
) -> None:
    """【何を確認するか】
    ソース削除 2 が、そのソースの文書をすべて削除して件数を返すこと。**登録直後で検索可能になっていない
    文書も**削除できる(Indexer が `delete_by_query` の前に refresh する)こと。他のソースの文書は残ること。
    再実行は 0 件で成功すること。ロックを所有していなければ 409 `lock_not_owned` で、何も消えないこと。

    【前提と手順】
    前提: 専用の `source_id` に 3 件、別のソースに 2 件を登録する。**登録の間、検索インデックスの
    `refresh_interval` を `-1`(自動 refresh なし)にする**(テストの最後に必ず既定へ戻す)。
    手順: (0) 事前確認: 3 件は ID 取得(GET)では読めるが、refresh しない `_count` では 0 件(検索可能でない)。
    (1) 所有していないロックで DELETE → 409。(2) 正しいロックで DELETE → 応答と、`delete_by_query` の実行回数を確認。
    (3) 完了後、テスト側が refresh して `_count` を数える。(4) 再実行。

    【期待する結果とその根拠】
    - (0) 検索可能でない状態を、テスト内で保証する。実機で確認した事実: この状態で素の `delete_by_query` を
      呼ぶと `deleted` は 0 になる(未 refresh の文書を見つけられない)。したがって Indexer が実行前に
      refresh しなければ、1 回目の `delete_by_query` は何も消さない。
    - (2) 200 `{"deleted_count": 3}`、かつ `delete_by_query` の実行が **1 回**(`scroll_total` の差分が 1)。
      `deleted_count` の値だけでは、実行前 refresh の有無を区別できない(refresh がなくても、Indexer は
      完了後の refresh と `_count` で残りを見つけて再実行し、再実行分を合算するので、合計は 3 になる)。
      区別できるのは実行回数で、実行前 refresh が欠ければ 1 回目が空振りして 2 回になる(`scroll_total` が
      2 になる。素の `delete_by_query` が 0 件でも 1 回と数えられることを実機で確認済み)。
      実行前 refresh が働いた証拠になる(api 4.7 の手順 1、arch K20、U-31(5)(11))。
      実測: 実行 1 回で `scroll_total` の差分は 1、`deleted_count` は 3。
    - (1) 409 `lock_not_owned`。文書は ID 取得で 3 件のまま(所有確認に失敗したら何も書かない。
      api 3.2・4.7、K60)。このチェックは件数照会(refresh を伴う)を使わない。使うと、テスト側の refresh が
      (2) の前提を壊すため。
    - (3) 完了後の `_count` は 0(手順 3)。別のソースは 2 件のまま。
    - (4) 200 `{"deleted_count": 0}`(すでに削除済みでも成功。冪等)。

    【この検出が依存する前提】
    - (a) `runs == 1` は、`delete_by_query` の内部実装(1 シャード、スライスなし。1 回の実行が
      `scroll_total` を 1 つ進める)に依存する。シャード数・スライスを変えると、期待する差分が変わる。
    - (b) ID 取得(realtime GET)が、未 refresh の文書を読んでも refresh を起こさないこと(OpenSearch
      2.19.7 で実測。3.9.0 でも、事前確認 (0) が通ることを確認した)。起こす版では、事前確認 (0) の
      `_count` が 0 にならずに落ちる(検出が効かない状態を黙って通さない)。
    - (c) 「素の `delete_by_query` が未 refresh の文書に対して 0 件を返す」事実は、実装担当が実機で確認
      したが、このテストでは確認していない(テストが確認するのは、事前確認 (0) と `runs == 1`)。

    【fake では確認できず実機で確認する点】
    実際の `delete_by_query`(`conflicts=proceed`、専用クライアント)の応答 `deleted` の件数、実行前 refresh
    と完了後 `_count`=0 の動作(arch U-31(5)(11))。DELETE に JSON ボディで `lock` を載せられること
    (HTTP クライアントとサーバの両方。README 6 章)。
    """
    documents = [text_document(f"docs/doc-{i}.txt", f"document {i}") for i in range(3)]
    other_documents = [text_document(f"docs/other-{i}.txt", f"other {i}") for i in range(2)]
    crawl = crawler.begin(source_id, started_at=ago(minutes=1))
    other_crawl = crawler.begin(other_source_id, started_at=ago(minutes=1))
    not_owner = Lock(owner="someone-else", job_id=crawl.lock.job_id)

    # 登録の間は自動 refresh を止める(終了時に必ず既定へ戻る)
    with opensearch.refresh_disabled(SEARCH_INDEX):
        crawl.register_ok(documents)
        other_crawl.register_ok(other_documents)

        # (0) 事前確認: ID 取得では読めるが、検索可能ではない(refresh していない `_count` は 0 件)
        for document in documents:
            assert opensearch.fetch_document(source_id, document.external_id) is not None, (
                f"{document.external_id} must be readable by ID"
            )
        searchable = opensearch.count_without_refresh(
            SEARCH_INDEX, {"term": {"source_id": source_id}}
        )
        assert searchable == 0, (
            f"the test must start from a state where the documents are not searchable: {searchable}"
        )

        # (1) ロックを所有していない呼び出し: 409 で、何も消えない(ID 取得で確認する)
        expect_error(crawler.delete_documents(source_id, not_owner), 409, "lock_not_owned")
        for document in documents:
            assert opensearch.fetch_document(source_id, document.external_id) is not None, (
                "nothing may be deleted without the lock"
            )

        # (2) 正しいロックで削除する: 検索可能でない文書も、実行前の refresh で対象になる
        stats_before = opensearch.search_stats(SEARCH_INDEX)
        body = expect_json(crawler.delete_documents(source_id, crawl.lock), 200)
        stats_after = opensearch.search_stats(SEARCH_INDEX)
        assert body == {"deleted_count": 3}, f"all 3 documents must be deleted: {body}"
        runs = stats_after["scroll_total"] - stats_before["scroll_total"]
        assert runs == 1, (
            f"delete_by_query must finish in one run because the pre-run refresh makes the "
            f"documents visible (2 runs mean the first one found nothing): {runs}"
        )

    # (3) 完了後の件数(ここはテスト側の refresh でよい)
    assert opensearch.count_source_documents(source_id) == 0, "no document of the source may remain"
    assert opensearch.count_source_documents(other_source_id) == 2, (
        "documents of another source must remain"
    )

    # (4) 再実行する: 0 件で成功する
    rerun = expect_json(crawler.delete_documents(source_id, crawl.lock), 200)
    assert rerun == {"deleted_count": 0}, f"a rerun must delete nothing and succeed: {rerun}"


def test_delete_deletion_records_removes_the_records_of_the_source_only(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str, other_source_id: str
) -> None:
    """【何を確認するか】
    ソース削除 3 が、そのソースの `deletion-{source_id}` と `deletion_result-*` を削除し、Status が 404 に
    なること。他のソースの記録は残ること。再実行は `deleted: false` で成功すること。

    【前提と手順】
    前提: 専用の `source_id` でクロールを終了(`deleted`)まで進めた状態。別のソースにも開始済みのクロール。
    手順: 記録の存在を確認 → ソース削除 3 を呼ぶ → 記録と Status を確認 → もう一度呼ぶ。

    【期待する結果とその根拠】
    - 呼ぶ前: `deletion-{source_id}` と `deletion_result-{crawl_id}` が存在する(前提の確認)。
    - 200 `{"deleted": true}`(削除した場合 true。api 4.8)。2 つの記録は消え、Status は 404
      `crawl_not_found`(記録がないクロールは 404。api 4.5)。
    - 別のソースの `deletion-*`・`deletion_result-*` は残る(対象はこのソースだけ。arch 9.14)。
    - 再実行は 200 `{"deleted": false}`(すでに記録がなければ false で成功。冪等。api 4.8)。

    【fake では確認できず実機で確認する点】
    実際の `delete_by_query`(または記録の削除)が `loreley-deletions` の strict マッピング上で
    `source_id` の絞り込みどおりに動くこと、削除直後の Status が 404 になること。
    """
    crawl = crawler.begin(source_id, started_at=ago(minutes=1))
    crawl.register_ok([text_document("docs/record.txt", "record")])
    assert crawl.finish_and_wait(enumerated_count=1)["status"] == "deleted", "the crawl must end"
    other_crawl = crawler.begin(other_source_id, started_at=ago(minutes=1))
    generation_id = f"deletion-{source_id}"
    result_id = f"deletion_result-{crawl.crawl_id}"

    # 呼ぶ前に、削除対象の記録が存在することを確認する
    assert opensearch.fetch(DELETIONS_INDEX, generation_id) is not None, "the generation exists"
    assert opensearch.fetch(DELETIONS_INDEX, result_id) is not None, "the deletion result exists"

    # ソース削除 3 を呼ぶ
    body = expect_json(crawler.delete_deletion_records(source_id, crawl.lock), 200)

    assert body == {"deleted": True}, f"existing records must be deleted: {body}"
    assert opensearch.fetch(DELETIONS_INDEX, generation_id) is None, "the generation must be gone"
    assert opensearch.fetch(DELETIONS_INDEX, result_id) is None, "the deletion result must be gone"
    expect_error(crawler.status(crawl.crawl_id), 404, "crawl_not_found")
    assert opensearch.fetch(DELETIONS_INDEX, f"deletion-{other_source_id}") is not None, (
        "the generation of another source must remain"
    )
    assert (
        opensearch.fetch(DELETIONS_INDEX, f"deletion_result-{other_crawl.crawl_id}") is not None
    ), "the deletion result of another source must remain"

    # もう一度呼ぶ: 記録がないので false で成功する(冪等)
    rerun = expect_json(crawler.delete_deletion_records(source_id, crawl.lock), 200)
    assert rerun == {"deleted": False}, f"a rerun must report that nothing was deleted: {rerun}"


def test_delete_deletion_records_removes_every_result_of_the_source(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str, other_source_id: str
) -> None:
    """【何を確認するか】
    同じソースに複数の `deletion_result` がある場合も、ソース削除 3 がすべてを削除すること。
    他のソースの記録は残ること。

    【前提と手順】
    前提: 専用の `source_id` に、終了済み(`deleted`)の削除結果が 2 つある状態を、実際の API の流れで作る。
    クロール C0(2 時間前開始)を終了通知まで済ませて `deleted` にしてから、クロール C1(1 分前開始)を
    開始して終了通知まで済ませる(C0 が終端状態なので、C1 の開始通知で C0 が `superseded` になることはなく、
    2 つの結果がそのまま並ぶ。C1 は自分で見た 1 件を列挙するので、件数照合は `1 == 1 + 0` で成立する)。
    別のソースにも、開始済みのクロールがある。
    手順: 記録が 2 つあることを確認 → ソース削除 3 を呼ぶ → すべて消えたことを確認。

    【期待する結果とその根拠】
    - 呼ぶ前: `deletion_result-{C0}` と `deletion_result-{C1}` が、ともに存在する(前提の確認)。
    - 200 `{"deleted": true}`。`deletion-{source_id}` と、このソースの `deletion_result-*` がすべて消え、
      どちらのクロールの Status も 404(api 4.8: 当該ソースの `deletion_result-*` をすべて削除する)。
    - 別のソースの `deletion-*`・`deletion_result-*` は残る(arch 9.14)。

    【fake では確認できず実機で確認する点】
    `source_id` による実際の `delete_by_query`(または一括削除)が、複数の記録をすべて消すこと。
    """
    # C0 を終了まで進め(deleted)、そのあとで C1 を開始して終了まで進める
    crawl0 = crawler.begin(source_id, started_at=ago(hours=2))
    crawl0.register_ok([text_document("docs/first.txt", "first")])
    assert crawl0.finish_and_wait(enumerated_count=1)["status"] == "deleted", "C0 must be terminal"
    crawl1 = crawler.begin(source_id, started_at=ago(minutes=1))
    crawl1.register_ok([text_document("docs/second.txt", "second")])
    assert crawl1.finish_and_wait(enumerated_count=1)["status"] == "deleted", "C1 must be terminal"
    other_crawl = crawler.begin(other_source_id, started_at=ago(minutes=1))

    # 呼ぶ前に、このソースの削除結果が 2 つあることを確認する
    result_ids = [f"deletion_result-{crawl.crawl_id}" for crawl in (crawl0, crawl1)]
    for result_id in result_ids:
        assert opensearch.fetch(DELETIONS_INDEX, result_id) is not None, f"{result_id} must exist"

    # ソース削除 3 を呼ぶ
    body = expect_json(crawler.delete_deletion_records(source_id, crawl1.lock), 200)

    assert body == {"deleted": True}, f"existing records must be deleted: {body}"
    for result_id in result_ids:
        assert opensearch.fetch(DELETIONS_INDEX, result_id) is None, f"{result_id} must be gone"
    assert opensearch.fetch(DELETIONS_INDEX, f"deletion-{source_id}") is None, (
        "the generation must be gone"
    )
    for crawl in (crawl0, crawl1):
        expect_error(crawler.status(crawl.crawl_id), 404, "crawl_not_found")
    assert (
        opensearch.fetch(DELETIONS_INDEX, f"deletion_result-{other_crawl.crawl_id}") is not None
    ), "the deletion result of another source must remain"
