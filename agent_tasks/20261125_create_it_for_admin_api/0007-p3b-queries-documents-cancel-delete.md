# 0007 P3b: クエリ・文書・取消とロック・ソース削除の IT(AIT-30・31・32・40・41・50・51・60)

日付: 2026-11-25
担当: code-implementer(実装)、メインエージェント(静的検査・残骸の再確認)

## 実施内容

- `test_30_queries.py`(AIT-30・31・32)、`test_40_documents.py`(AIT-40・41)、`test_50_cancel_and_lock.py`(AIT-50・51)、`test_60_source_deletion.py`(AIT-60)を追加
- `support.py` 追加: `format_instant`、待ちヘルパ(`wait_for_source_row`・`wait_for_job_list`・`wait_for_document_list`・`wait_for_finish_notice_started`)、`OpenSearchProbe` の直読み(`source_config_records`・`cluster_health`・`cat_rows`)と直接書き込み(`write_skip_record`・`write_lock_record`。AIT-41・51 の前提作りのみ)
- `conftest.py` 追加: `make_registered_source`(同一テストで登録済みソースを追加作成。AIT-50 の Y・AIT-60 の Z)
- `test_20_crawl.py` 小変更: 私的ヘルパ `_list_row` を `support.wait_for_source_row` に置き換え(重複解消、挙動同じ)

## 変更したファイル

`tests/integration/api/{test_30_queries.py,test_40_documents.py,test_50_cancel_and_lock.py,test_60_source_deletion.py}`(新規)、`support.py`・`conftest.py`・`test_20_crawl.py`(変更)。`apps/`・設計書は変更なし。

## 判断・設計上の理由

- AIT-30・31 はモジュールスコープのフィクスチャで 3 ソース(2 回・1 回・0 回クロール)を共有(読み取り専用。約 35 秒節約)。2 回目の前に md を足して文書数 3 とし、`last_crawl` が 2 回目を指すことを区別可能にした
- AIT-30 は `loreley-sources` 全行について `last_crawl`・`last_completed_at`・`delete_job`・`document_count`・`stalled`・`cancellable` を OpenSearch 直読みから独立計算し、API 応答と一致するまで 10 秒を上限にポーリング。独立計算が空や同じ誤りで通らないよう、3 ソースの値そのものも別にアサート
- AIT-32 は `indices` の並び(状態の悪い順 → 名前昇順。admin-api 7.1)も独立実装で照合。`cat.*` の引数は api と同じ
- AIT-40 は 1 回のクロールで `last_seen_at` が全文書同一になることを前提としてアサートし、同順位の `document_id` 昇順規則が効く状態で検証。`oversize` の `size`・`detected_by` は `loreley-jobs` の記録との一致を確認(`size` は決め打ちしない)
- AIT-41 は `last_skipped_at` に差をつけた 2 件を書き、既定の `-last_skipped_at` と `sort=last_skipped_at` の反転を検証。記録形式は crawler-architecture 3.3.3 と `document_records.py` の `create_fields` に合わせた
- AIT-50 は `finish_notice.send_started_at` を直読みで待ち、すでに終端なら窓を見逃したことが分かるメッセージで失敗させる
- AIT-51 のロック文書の形式は、実 Crawler が実行中に書いたロック文書を直読みして合わせた
- AIT-60 に、プランの表にない EP-08 の 409 `lock_in_use`(実行待ちの削除ジョブ)の確認を追加(追加コストなし)
- テストを実機に合わせて曲げた箇所はなし

## 検証結果

- ruff check・format、`pytest --collect-only`(20 件): OK(メインエージェントも再実行)
- クリーンな状態から `scripts/run-api-integration-test.sh`(`--keep` なし)を 2 回連続で全件実行: いずれも 20 passed、終了コード 0(pytest 171.5 秒・172.4 秒、スクリプト全体 248 秒)。不安定なテストは観測されなかった
- 件数内訳: test_01 が 5、test_10 が 5、test_20 が 2、test_30 が 3、test_40 が 2、test_50 が 2、test_60 が 1
- 終了後: `loreley-it` のコンテナ・ボリューム・ネットワーク・`data/` なし、ポート空き、`docker ps -a` は他プロジェクトの `opensearch-opensearch-1` のみ(メインエージェントが再確認)
- `apps/` 変更なしのため単体テスト・ruff は未実施。shellcheck 未実施

## 発見事項(実機の観測値。設計との食い違いなし)

- AIT-40: 31 ファイル(md 3・壊れた PDF 26・70,000 バイト 2)で `enumerated_count=31`・`created_count=29`・`oversize_count=2`・`error_count=26`・`skipped_count=0`、ジョブ `succeeded`。索引にあるのは 29 件で、上限超過 2 件は索引になく `loreley-jobs` の記録のみ。`extract_failed` の `title` はファイル名。同一クロールの文書は `last_seen_at` が全件同一
- 原本サイズ超過記録の `size`: 実 Crawler が検出した記録(`detected_by=crawler`)では null。EP-11 も `size: null`(設計 3.3.4「分かる場合だけ」と整合)。`size_hint` が付く場面は未確認
- AIT-50: `send_started_at` 観測から取消受付(202)まで約 0.03 秒、取消後 `cancelled` まで約 1.1 秒。警告は `[{"code":"polling_aborted","confirmation":"unconfirmed"}]`、`deletion.confirmation=unconfirmed`、`registration` は `partial=false`・`phase=final`。打ち切った時点の `deletion.summary` は `status=running`・`observed_at` あり・`deleted_count` 等は null。窓は約 10 秒で 2 回の実行とも見逃さなかった
- AIT-51: 孤児ロックの `lock.job` は `status=succeeded`・`job_type=crawl`・`trigger=manual` と `lease_expires_at`。EP-06 の 409 `details.existing_job` も同内容で `lock_state=orphan`。EP-08 は `released=true`・`failed_job_id=null`、再送は `released=false`。解放しても終端ジョブの `status` は変わらない
- AIT-60: 実行待ちの間、S の設定 `status` は `active` のまま(`deleting` は実行開始から。crawler-architecture 8.1 の順 0 と一致)。完了後 EP-08 は `released=false`(削除ジョブがロックを自分で消す)。S のジョブ記録は削除後も EP-10 で読める
- 検索系 EP(EP-01・09・11・EP-02 の最終クロール)の反映遅れは最大約 1 秒(P3a の観測どおり)
- 所要時間: test_30 約 35 秒、test_40 約 23 秒、test_50 約 25 秒、test_60 約 33 秒、全 20 件約 172 秒

## 未対応事項・次にやること

- 未検証のまま(結果文書に記録): EP-09 の複数ページ(26 件以上のジョブが必要)、AAPI-U-7(実 Crawler が書いたスキップ記録の形式との照合。AIT-41 は直接書き込み)、`summary_pending` は空確認のみ(AAPI-U-8。LLM 要約の実装後)、`size_hint` の経路
- 次: P4(障害系 AIT-90〜92)。`ComposeControl` の実 docker 実行は初。P4 冒頭で compose v2.3.3 の `stop/start` の挙動(依存サービスが止まらないこと)を確認する
