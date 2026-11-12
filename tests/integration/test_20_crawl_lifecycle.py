"""IT-20〜IT-22: クロールの開始通知・`last-seen`・終了通知と Status。

目的:
    Crawler 役として開始通知・`last_seen_at` の部分更新・終了通知を送り、Indexer が実 OpenSearch に
    作る記録(`loreley-deletions`)と文書(検索インデックス)を直接読んで確かめる。fake の単体テスト
    では確認できない次の点を実機で確認する: `dynamic: strict` のマッピングへの書き込み、painless の
    max 比較スクリプトと日時(`Instant`)のパース、404 の応答形(`document_missing_exception`)。

参照する設計書の章:
    - indexer-api-v0.10.md 3.4(エラー形式)、3.6(日時の正規化)、4.1(開始通知)、
      4.2(`last-seen`)、4.4(終了通知)、4.5(Status API)
    - indexer-architecture-v0.10.md 3.3(日時)、5 章(`last_seen_at` の Update)、9.4(`loreley-deletions` の
      記録と設定スナップショット)、9.5(開始通知・終了通知・Status API の受理)、U-31(6)(7)(9)
    - loreley-deletions-v0.10.md(記録の項目)

扱うシナリオ: IT-20(開始通知)、IT-21(`last-seen`)、IT-22(終了通知と Status)
"""

from datetime import timedelta

from support import (
    DELETIONS_INDEX,
    MILLIS_INSTANT_PATTERN,
    TTL_SECONDS,
    CrawlerClient,
    OpenSearchProbe,
    ago,
    compute_document_id,
    expect_error,
    expect_json,
    iso,
    iso_in_jst,
    text_document,
    unique_id,
    utc_now,
)

# --- IT-20: 開始通知 ---


def test_start_notification_creates_the_generation_and_the_deletion_result(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    開始通知が 200 `running` を返し、`deletion-{source_id}`(現行世代)と `deletion_result-{crawl_id}`
    (削除結果)が `loreley-deletions` に作られ、設定スナップショットが複写されること。

    【前提と手順】
    前提: 専用の `source_id` / `crawl_id`。ロック文書は作らない(api 4.1 の開始通知にロック所有情報の
    記載はなく、所有確認もしないので、ロック文書なしで通ることが正しい)。
    手順: `crawl_started_at` を JST(+09:00)・マイクロ秒つきの表記で、設定値(`ttl=600`、
    `ratio_threshold=0.25`、`min_delete_count=7`、`force_delete=true`)つきで開始通知を送る →
    応答、OpenSearch の 2 つの記録、Status API を確認する。

    【期待する結果とその根拠】
    - 200 `{"crawl_id", "status": "running"}`(api 4.1)。
    - `deletion_result-{crawl_id}`: `status=running`、`source_id`、設定スナップショットの複写
      (`ttl`・`ratio_threshold`・`min_delete_count`、`force_delete` は `forced` として)、`rewrite_mode` は
      省略が `false` に正規化されて保存、`crawl_started_at` は UTC・ミリ秒に正規化された値
      (入力は JST のマイクロ秒表記。api 3.6、arch 9.4)。`finish_received_at` はまだない。
      入力のマイクロ秒(456μs)は、切り捨てでも四捨五入でもミリ秒の値が同じになる大きさにしてあり、
      このテストは、切り捨てか四捨五入かを区別しない(api 3.6 は「ミリ秒精度」としか定めていない)。
    - `deletion-{source_id}`: 現行世代として `crawl_id`・`crawl_started_at`・スナップショットを持つ(arch 9.4)。
    - Status API は同じ設定値を返し、`finish_received_at` を含まない(api 4.5「値のない項目はキーごと省く」)。
    - 2 つの記録が書けたこと自体が、`loreley-deletions` の `dynamic: strict` マッピングに Indexer の書き込み項目
      がすべて通ることの確認になる(定義漏れは `strict_dynamic_mapping_exception` で失敗する)。

    【fake では確認できず実機で確認する点】
    strict マッピングへの実書き込み、date 型への正規化済み日時の受理、`double`(ratio_threshold)・`long` の型。
    """
    crawl_id = unique_id("crawl")
    # マイクロ秒つきの入力。保存されるのは、ミリ秒に切り捨てた UTC の値
    started_at = ago(minutes=1)
    started_at_with_micros = started_at + timedelta(microseconds=456)

    # 設定スナップショットつきで開始通知を送る
    response = crawler.start(
        {
            "crawl_id": crawl_id,
            "source_id": source_id,
            "crawl_started_at": iso_in_jst(started_at_with_micros),
            "ttl": TTL_SECONDS,
            "ratio_threshold": 0.25,
            "min_delete_count": 7,
            "force_delete": True,
        }
    )

    body = expect_json(response, 200)
    assert body == {"crawl_id": crawl_id, "status": "running"}, f"unexpected start response: {body}"

    # 削除結果: 設定スナップショットが複写されている
    result = opensearch.fetch_source(DELETIONS_INDEX, f"deletion_result-{crawl_id}")
    assert result is not None, "the deletion result must be created by the start notification"
    assert result["record_type"] == "deletion_result", f"record_type must be set: {result}"
    assert (result["status"], result["source_id"]) == ("running", source_id), (
        f"the result must be running for this source: {result}"
    )
    assert result["crawl_started_at"] == iso(started_at), (
        f"crawl_started_at must be normalized to UTC milliseconds: {result['crawl_started_at']}"
    )
    assert (result["ttl"], result["ratio_threshold"], result["min_delete_count"]) == (
        TTL_SECONDS,
        0.25,
        7,
    ), f"the settings snapshot must be copied: {result}"
    assert result["forced"] is True, f"force_delete must be copied as forced: {result}"
    assert result["rewrite_mode"] is False, f"an omitted rewrite_mode must be false: {result}"
    assert MILLIS_INSTANT_PATTERN.match(result["started_at"]), f"started_at format: {result}"
    assert "finish_received_at" not in result, f"no finish has been received yet: {result}"

    # 現行世代: 直近の開始通知の内容
    generation = opensearch.fetch_source(DELETIONS_INDEX, f"deletion-{source_id}")
    assert generation is not None, "the current generation must be created"
    assert generation["record_type"] == "deletion", f"record_type must be set: {generation}"
    assert generation["crawl_id"] == crawl_id, (
        f"the generation must point to this crawl: {generation}"
    )
    assert generation["crawl_started_at"] == iso(started_at), (
        f"the generation must hold the normalized crawl_started_at: {generation}"
    )
    assert (generation["ttl"], generation["force_delete"]) == (TTL_SECONDS, True), (
        f"the generation must hold the snapshot: {generation}"
    )

    # Status API: 同じ設定値を返し、値のない項目は省く
    status = expect_json(crawler.status(crawl_id), 200)
    assert status["status"] == "running", f"the crawl must be running: {status}"
    assert (status["ttl"], status["ratio_threshold"], status["min_delete_count"]) == (
        TTL_SECONDS,
        0.25,
        7,
    ), f"Status must return the snapshot: {status}"
    assert status["forced"] is True, f"Status must return forced: {status}"
    assert "finish_received_at" not in status, f"absent values must be omitted: {status}"


# --- IT-21: last-seen(部分更新) ---


def test_last_seen_updates_the_timestamp_by_max_comparison_with_the_real_script(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    `last-seen` が、既存の文書は `updated`、同値の再送は `unchanged`(書かない)、存在しない ID は
    `not_found` になること。現在値のほうが新しい文書は、古い値で上書きしないこと(max 比較)。

    【前提と手順】
    前提: クロール 1(2 時間前開始)で文書 X を登録済み(`last_seen_at` = クロール 1 の開始時刻)。
    手順: クロール 2(3 分前開始)で X と未登録の ID を `last-seen` → 同じ内容を再送 →
    前提作りとして X の `last_seen_at` を未来の値に直接書き換えて再送。

    【期待する結果とその根拠】
    - 初回: X は `updated`、未登録 ID は `not_found`(upsert しない。新規文書では正常。api 4.2)。
      X の `last_seen_at` はクロール 2 の `crawl_started_at`。
    - 再送: X は `unchanged`(現在値以上なので noop。api 4.2、arch K27)。`_seq_no` が進まない
      (noop は書き込みにならない)。
    - 未来の値を持つ X: `unchanged`。`last_seen_at` は未来の値のまま(古い値に戻らない)。
    - `not_found` は、404 のうち `document_missing_exception`(文書なし)のときだけ。索引の異常は
      503 になり、ここには現れない(api 4.2、arch U-31(9))。

    【fake では確認できず実機で確認する点】
    - painless スクリプト(params で値を渡し、本体を固定した形)が実機で動くこと(arch U-31(6))。
    - 実 OpenSearch の `update` が文書なしで返す 404 の本文の形を、Indexer が `not_found` に分類できること
      (U-31(9))。
    - 日時を `Instant` にパースして比較する動作(U-31(7))。
    """
    document = text_document("docs/seen.txt", "last seen check")
    document_id = document.document_id(source_id)
    missing_id = compute_document_id(source_id, "docs/never-registered.txt")

    # クロール 1(2 時間前)で X を登録する
    crawl1 = crawler.begin(source_id, started_at=ago(hours=2))
    assert crawl1.register_ok([document])[0]["change"] == "created", "the first registration"

    # クロール 2(3 分前)で、X と未登録の ID を last-seen する
    crawl2_started_at = ago(minutes=3)
    crawl2 = crawler.begin(source_id, started_at=crawl2_started_at)
    results = crawl2.last_seen_ok([document_id, missing_id])

    assert results == [
        {"document_id": document_id, "result": "updated"},
        {"document_id": missing_id, "result": "not_found"},
    ], f"an existing document is updated and a missing one is not_found: {results}"
    updated = opensearch.fetch_document_by_id(document_id)
    assert updated is not None, "the document must exist"
    assert updated["_source"]["last_seen_at"] == iso(crawl2_started_at), (
        f"last_seen_at must be crawl 2's crawl_started_at: {updated['_source']['last_seen_at']}"
    )

    # 同じ内容を再送する: 現在値以上なので書かない
    resent = crawl2.last_seen_ok([document_id])
    assert resent == [{"document_id": document_id, "result": "unchanged"}], (
        f"a resend with the same value must be unchanged: {resent}"
    )
    after_resend = opensearch.fetch_document_by_id(document_id)
    assert after_resend is not None and after_resend["_seq_no"] == updated["_seq_no"], (
        "an unchanged last-seen must not write (no _seq_no increase)"
    )

    # X の last_seen_at を未来の値にして再送する: 古い値で上書きしない
    future = utc_now() + timedelta(hours=1)
    opensearch.force_last_seen_at(source_id, document.external_id, future)
    behind = crawl2.last_seen_ok([document_id])
    assert behind == [{"document_id": document_id, "result": "unchanged"}], (
        f"an older crawl_started_at must not overwrite a newer last_seen_at: {behind}"
    )
    final = opensearch.fetch_document_by_id(document_id)
    assert final is not None and final["_source"]["last_seen_at"] == iso(future), (
        "last_seen_at must stay at the newer value"
    )


def test_last_seen_normalizes_microsecond_and_second_precision_inputs(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    `last-seen` の `crawl_started_at` が、マイクロ秒つき・JST の表記でも、秒精度の表記でも、UTC・ミリ秒に
    正規化されて保存され、更新・noop が正しく判定されること。

    【前提と手順】
    前提: クロール 1(2 時間前開始)で文書 Y を登録済み。
    手順: (1) クロール 3(2 分前開始。JST・マイクロ秒つきの表記)で `last-seen` → 同じ表記で再送。
    (2) クロール 4(1 分前開始。秒精度の `Z` 表記)で `last-seen` → 再送。

    【期待する結果とその根拠】
    - (1)(2) とも初回は `updated`、再送は `unchanged`。保存される `last_seen_at` は、UTC・ミリ秒の正規形
      (マイクロ秒は切り捨て。秒精度は `.000Z`)(api 3.6、arch 3.3)。
    - このテストが判別できるのは、「painless スクリプトが実機で動き、正規化した値で更新・noop の判定が
      できること」と「正規化の結果(保存される文字列)」まで。Indexer は、保存・比較の前に UTC・ミリ秒の固定幅の
      形式へ正規化するので、保存値どうしの文字列比較と `Instant` の比較は同値になる。したがって、スクリプトが
      本当に `Instant` で比べているか(文字列で比べていないか)は、このテストでは判別できない(U-31(7) の
      一部は未確認として残る)。
    - 順序: クロール 1 < 3 < 4 なので、(1)(2) とも新しい値で更新される。

    【fake では確認できず実機で確認する点】
    実際の painless スクリプトでの `Instant` のパースと比較、date 型のマッピングとの整合(U-31(7))。
    """
    document = text_document("docs/precision.txt", "precision check")
    document_id = document.document_id(source_id)

    # クロール 1(2 時間前)で Y を登録する
    crawler.begin(source_id, started_at=ago(hours=2)).register_ok([document])

    # (1) クロール 3: JST・マイクロ秒つきの表記
    crawl3_started_at = ago(minutes=2)
    crawl3 = crawler.begin(
        source_id,
        started_at=crawl3_started_at,
        started_at_text=iso_in_jst(crawl3_started_at + timedelta(microseconds=456)),
    )
    assert crawl3.last_seen_ok([document_id])[0]["result"] == "updated", "crawl 3 moves it forward"
    assert crawl3.last_seen_ok([document_id])[0]["result"] == "unchanged", "crawl 3 resend"
    stored = opensearch.fetch_document_by_id(document_id)
    assert stored is not None and stored["_source"]["last_seen_at"] == iso(crawl3_started_at), (
        f"a JST microsecond input must be stored as UTC milliseconds: {stored}"
    )

    # (2) クロール 4: 秒精度の Z 表記(ミリ秒以下を持たない)
    crawl4_started_at = ago(minutes=1).replace(microsecond=0)
    crawl4 = crawler.begin(
        source_id,
        started_at=crawl4_started_at,
        started_at_text=crawl4_started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    assert crawl4.last_seen_ok([document_id])[0]["result"] == "updated", "crawl 4 moves it forward"
    assert crawl4.last_seen_ok([document_id])[0]["result"] == "unchanged", "crawl 4 resend"
    stored = opensearch.fetch_document_by_id(document_id)
    assert stored is not None and stored["_source"]["last_seen_at"] == iso(crawl4_started_at), (
        f"a second-precision input must be stored as UTC milliseconds: {stored}"
    )


# --- IT-22: 終了通知と Status ---


def test_finish_notification_is_accepted_and_status_reaches_a_terminal_state(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    終了通知が 202(ボディなし)で受理され、受理の事実が Status API の `finish_received_at` で見えること。
    削除結果が非同期に終端状態へ進むこと。

    【前提と手順】
    前提: クロールを開始し、文書を 1 件登録済み。TTL は 1 日(削除対象が出ない)。
    手順: 終了通知(`enumeration_completed`、`enumerated_count=1`)を送る → 202 を確認 → 直後の Status →
    終端状態になるまでポーリング(間隔 0.5 秒、上限 30 秒)。

    【期待する結果とその根拠】
    - 202 でボディなし(api 4.4)。
    - 直後の Status に `finish_received_at`(ミリ秒の正規形)がある。受理の事実は 202 を返す前に永続化される
      (api 4.4、arch 9.5)。受理の有無は `finish_received_at` で読む(api 4.5)。
    - 終端状態は `deleted`(対象 0 件。`last_seen_at + TTL` が過ぎた文書がないため。arch 9.7 の順 4)。
      `n_seen=1`(登録した 1 件。`last_seen_at >= crawl_started_at`)、`enumerated_count=1`、`e_missing=0`、
      `finished_at` がある(件数照合 `1 == 1 + 0`。arch 9.6)。
    - `loreley-deletions` の `deletion_result-{crawl_id}` を直接読んでも `status=deleted`・
      `outcome=enumeration_completed` で、`reason` はない(Status API の応答だけに頼らない)。

    【fake では確認できず実機で確認する点】
    実際の削除ワーカーの走査(`loreley-deletions` の検索)、`N_seen` を数える実 `_count`(refresh 後)、
    受理の書き込み(`if_seq_no` の条件付き更新)が実 OpenSearch で通ること。
    """
    crawl = crawler.begin(source_id, started_at=ago(minutes=1))
    crawl.register_ok([text_document("docs/finish.txt", "finish check")])

    # 終了通知を送る
    response = crawl.finish(enumerated_count=1)

    assert response.status_code == 202, f"finish must be accepted with 202: {response.status_code}"
    assert response.content == b"", f"a 202 must have no body: {response.content!r}"

    # 直後の Status: 受理の事実が見える
    accepted = crawl.status()
    assert MILLIS_INSTANT_PATTERN.match(accepted.get("finish_received_at", "")), (
        f"finish_received_at must be recorded before the 202 is returned: {accepted}"
    )

    # 削除結果が終端状態になるまで待つ
    final = crawler.wait_for_terminal(crawl.crawl_id)
    assert final["status"] == "deleted", f"no target means deleted: {final}"
    assert final["enumerated_count"] == 1, f"enumerated_count must be recorded: {final}"
    assert final["n_seen"] == 1, f"the registered document must be counted as seen: {final}"
    assert final["e_missing"] == 0, f"there are no skipped or oversize documents: {final}"
    assert MILLIS_INSTANT_PATTERN.match(final.get("finished_at", "")), (
        f"a terminal result must have finished_at: {final}"
    )

    # Status API だけに頼らず、`loreley-deletions` の記録を直接読んで終端状態を確認する
    record = opensearch.fetch_source(DELETIONS_INDEX, f"deletion_result-{crawl.crawl_id}")
    assert record is not None, "the deletion result must exist in loreley-deletions"
    assert (record["status"], record["outcome"]) == ("deleted", "enumeration_completed"), (
        f"the stored result must be deleted by enumeration_completed: {record}"
    )
    assert "reason" not in record, f"a normal deletion has no reason: {record}"


def test_unknown_crawl_id_is_404_for_status_and_ignored_by_finish(
    crawler: CrawlerClient, opensearch: OpenSearchProbe, source_id: str
) -> None:
    """【何を確認するか】
    未知の `crawl_id` の Status が 404 `crawl_not_found` になること。未知の `crawl_id` への終了通知が
    202 で受け付けられ、記録は作られず、Status は 404 のままであること。

    【前提と手順】
    前提: 開始通知を受けていない `crawl_id`。
    手順: Status を呼ぶ → 同じ `crawl_id` に終了通知を送る → Status と `loreley-deletions` を確認する。

    【期待する結果とその根拠】
    - Status は 404 `crawl_not_found`(エラー形式 `{"error": {"code", "message", "retryable"}}`。
      api 3.4・4.5)。
    - 終了通知は 202(開始通知を受けていない `crawl_id` は破棄して 202。api 4.4 の分岐 2、arch K7)。
      202 は受理の確認ではない(api 4.4)ので、記録が作られていないこと(Status が 404 のまま、
      `deletion_result-*` なし)を確認する。

    【fake では確認できず実機で確認する点】
    実 OpenSearch の 404(文書なし)を「未知の crawl_id」として扱う分類、および未知の `crawl_id` の終了通知が
    `loreley-deletions` に何も書かないこと。
    """
    unknown_crawl_id = unique_id("unknown-crawl")

    # 未知の crawl_id の Status を問い合わせる
    expect_error(crawler.status(unknown_crawl_id), 404, "crawl_not_found")

    # 未知の crawl_id に終了通知を送る
    response = crawler.finish(
        unknown_crawl_id,
        {
            "source_id": source_id,
            "outcome": "enumeration_completed",
            "enumerated_count": 0,
            "skipped_document_ids": [],
            "oversize_document_ids": [],
            "finished_at": iso(utc_now()),
        },
    )

    assert response.status_code == 202, f"an unknown crawl_id is still 202: {response.status_code}"
    expect_error(crawler.status(unknown_crawl_id), 404, "crawl_not_found")
    assert opensearch.fetch(DELETIONS_INDEX, f"deletion_result-{unknown_crawl_id}") is None, (
        "no deletion result may be created for an unknown crawl_id"
    )
