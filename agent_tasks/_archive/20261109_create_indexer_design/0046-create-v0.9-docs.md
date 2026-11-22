# 0046 v0.9 / PD v0.18 の作成(0044 への回答の反映)

## 概要
0045 のプランに従い、document-writer 3体が並列で作成した(architecture / api+search-index+loreley-deletions / PD v0.18+テスト結果の雛形)。v0.8 以前と PD v0.17 は変更していない。`loreley-texts` は v0.9 も作らない。

## 変更したファイル(すべて新規)
- docs/v0.x/system-design/indexer/indexer-architecture-v0.9.md(1265行)
- docs/v0.x/system-design/indexer/indexer-api-v0.9.md(808行)
- docs/v0.x/system-design/opensearch/schema/search-index-v0.9.md(344行)
- docs/v0.x/system-design/opensearch/schema/loreley-deletions-v0.9.md(242行)
- docs/v0.x/product-design/product-design-v0.18.md
- docs/v0.x/test-results/opensearch-performance.md(雛形。状態は「未実施」。測定値・評価なし)

## 変更内容の要点
- **K34〜K56 を確定欄(architecture 17.1)に追加**(確定は K12、K18〜K56)。解消した案・未決(P42(1)〜(4)、P33、P38 の区分、U-4 の 409 本文・エラー名・「削除中」、U-14 の5項目名、U-16 の `url`/`path`・`fetched_at`・`metadata`、U-6 の保存した ID 一覧のマッピング、U-25、U-30 の読み取りの可否、U-9 の要約の基本方針、API-U-7・API-U-20 の `rewrite_mode`・API-U-22)は 17.5 に記録。U-4・U-6・U-9・U-14・U-16・U-30 は、解消した部分だけ外し残余を 17.3 に残した(writer の解釈)。
- **項目名(K42)**: `finish_request_digest`、`skipped_document_ids`(保存したスキップ文書 ID 一覧)、`oversize_document_ids`(保存したサイズ超過文書 ID 一覧)、`skip_and_oversize_id_count`、`skip_and_oversize_id_limit_exceeded`。architecture 1.3 に「終了通知のダイジェスト」「保存した ID 一覧」の用語行、16.1 にテスト観点内の用語対応を追加。「一覧」だけの曖昧な記述は全箇所を洗い出して修正(9.9 の待ち行列、9.13(7)、E-44、D-92 など)。
- **K34〜K38**: 上限超過の終了通知は 202 で受理し ID 一覧は保存せず件数と超過の事実だけ記録、判定の順番で `validation_failed`(HTTP ボディサイズ上限は別の制限)。終端状態への遷移と同じ書き込みで保存した ID 一覧を削除(ダイジェストは残す)。`failed`/`cancelled` は ID 一覧を保存しない。`rewrite_mode` の省略は `false` に正規化、再送の比較も正規化後の値。終了通知の処理順は 400 → `source_id` 照合 409 → ダイジェストによる再送判定 → 初回受理。
- **K39**: 設計書上の数値は未決のまま。architecture に 15.7「実装時の仮値」を新設(仮値は設定として管理し必ず上限を設ける)。
- **K40〜K43**: 409 のエラー名 `finish_source_mismatch`/`finish_content_mismatch` を確定。409 の本文は共通エラー形式でコードと短いメッセージのみ(Status API で確認)。「削除中」は `status=running` のまま、進捗は `deletion_started_at` と記録済みの `deleted_count`(途中経過が未保存なら推測して表示しない)。
- **K44〜K46**: `url`/`path` は独立2項目。`fetched_at`・`metadata` は MVP で保存せず、api の `documents[]` と search-index の項目表・マッピングから削除。`summary_embedding` はマッピングから除外。
- **K47〜K52**: P33 を確定(PIT なし、厳密なスナップショットを保証しない、T と D の不整合・TTL 再確認は実機試験で検証、問題があれば PIT を再検討。T > D で `validation_failed` も確定扱いにした=writer の判断)。`delete_by_query` の再実行上限(数値は実測後)、上限で完了しなければソース削除のジョブ `failed`、残りは後続の再実行で削除。要約並列数の仮の既定値は 1。`change` は本文・メタデータの変更区分で `last_seen_at` だけの更新は `unchanged`。`write_conflict`/`update_conflict` を採用、上限付きリトライで解消しなければジョブ `failed`・期限削除なし・文書固有のスキップ対象にしない。保存した ID 一覧のマッピングは `keyword`・`index: false`・`doc_values: false`(`enabled: false` は文字列配列に指定しない)。
- **K53〜K56**: Admin API は検索インデックスを読み取り専用で参照(書き込まない。形は Admin API 設計)。要約の基本方針(7.3〜7.5。詳細は U-9 に未決)。U-31 は実装時の必須試験項目。性能測定結果は `docs/v0.x/test-results/opensearch-performance.md` に記録(削除処理も個別に測る)。
- **テスト観点**: 「案」注記を確定に更新(C-27(b)、D-94(c)(d)(e)、D-91(o)(p)(q)、D-90(c)、C-10a/b、C-17、C-18b、C-21(d)、E-20)。D-94(e) は省略と `false` が同じ値なので 409 にならず成功(K37 から導出)。D-94(f)(真偽値以外)は期待結果未決のまま。E2: 16.3 の C-23 は Indexer 側の観点のみ、16.10 は「C-23(`get_document` の範囲の切り出し部分)」と表記して重複をなくした。新設 ID なし(欠番再利用なし)。
- **PD v0.18**: 「最後に見つかった日時」と `last_seen_at` を「存在確認日時」に統一し、10章の用語集に定義を置いた(E1)。K34〜K56 は PD には入れていない。

## 確認(メイン)
- 禁止語(`reconcile` `summary_*_hash` `scripted_upsert` `v0.8` `従来` `変更点`)は4文書で 0 件、`pending_index` は architecture の K18 決定文のみ。architecture の K34〜K56 は23行。表の ID の重複なし。`fetched_at` は api と search-index に残っていない。「案(ユーザー承認待ち)」は api に2件のみ(K34〜K56 の対象外の API-U-19 など)。PD に残る `last_seen_at`(1件)・「最後に見つかった日時」(2件)は、writer の報告では改訂履歴内の旧表記(レビューで確認)。

## 判断・設計上の理由(writer の推測・解釈)
- P33 の「T > D で `validation_failed`」も K47 に含めて確定扱いにした(api/Schema の writer の判断)。
- 書き込み競合を「連続20件の計数」に含めないとした(K51 の「文書固有のスキップ対象としない」からの導出。推測)。
- P38 の再送時の集計規則(最初に受け取れた結果を保持)は K50 の対象外のため、P-ID を立てず「案(Crawler 領域)」として残した(api の API-U-16、architecture 4.3)。
- G-12(起動契機)は根拠を確認できなかったため推測のまま(C11)。
- 作業環境: 並行作業中の writer 間で scratchpad が共有されていた(成果物には影響なしとの報告)。

## 未対応事項
- document-reviewer と test-reviewer のレビュー(E3。各1回。次)、task-reviewer。
- **PD と Indexer 設計の矛盾の疑い(writer 報告。変更なし。ユーザー判断待ち)**: (1) PD は Admin API を「ジョブ状態と削除結果を Store 層から読み取りのみ」(4章の構成図の注記と責務表)としているが、4.6 の Admin View は抽出失敗・要約未生成・スキップ文書の確認を載せており、これらは検索インデックスにある。K53(Admin API が検索インデックスを読み取り専用で参照してよい)に比べ PD の記述が狭い。(2) PD 9.2 #13 は要約の後日有効化・`failed` の再試行を「後で再検討。未決」のままで、K54 の基本方針は PD に未反映(矛盾はしない)。反映する場合は PD v0.19 を作成する。
- **ユーザー判断待ち(案)・未決**: API-U-19(登録の拒否のエラーコード名)、API-U-1/4/5/6/8/10/12/13/14/15/17(設定スナップショットの項目名、数値、Crawler 側の具体など)、U-1/2/3/5/8/9 の詳細/12/14 の残り/15/16 の `path`、U-30 の具体(Admin API の形)、U-31 の数値、D-94(f)、D-79(c)、G-12、P38 の再送時の集計規則、`rewrite_mode` の複写の項目名(loreley-deletions U-1)。数値は設計書上は未決のまま(K39)。
- 次の工程: 重大な指摘がなければ、設計書の改訂を続けず Indexer の実装と OpenSearch の実機試験に進む(E4。この設計タスクの範囲外)。
- 引き渡し事項(次の Crawler / Search API / Admin API 設計)・SD v0.8 の改版(旧構成の記述の更新が必要)は 0043 のとおり。
