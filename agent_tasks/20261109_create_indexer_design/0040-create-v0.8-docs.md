# 0040 v0.8 の作成(外部レビュー(2回目)の反映)

## 概要
0039 のプランに従い、document-writer 2体が並列で作成した(architecture / api+search-index+loreley-deletions)。v0.7 は変更していない。`product-design-v0.17.md` は変更不要のため新版なし(PD は v0.17 のまま)。

## 変更したファイル(すべて新規)
- docs/v0.x/system-design/indexer/indexer-architecture-v0.8.md(1231行)
- docs/v0.x/system-design/indexer/indexer-api-v0.8.md(802行)
- docs/v0.x/system-design/opensearch/schema/search-index-v0.8.md(347行。版の更新と K33 参照のみ)
- docs/v0.x/system-design/opensearch/schema/loreley-deletions-v0.8.md(227行)

## 変更内容の要点
- **K31(指摘①)**: 終了通知の受理時に、ダイジェストと `finish_received_at` と同じ書き込みで `skipped_document_ids`/`oversize_document_ids`(正規化した一覧)を `deletion_result` に保存。9.4(項目。項目名は未決 U-14)、9.5、9.6(`E_missing` と除外は保存した一覧を使う)、9.7、9.8、9.9(待機中の削除も判定時まで参照できる)、9.12、12章、15.6(容量。新設)。終端状態で一覧を削除し、ダイジェストは残す。再起動時の `failed(indexer_restart)` は変えず、待機中の削除も実行しない。loreley-deletions 2.2・2.3・4〜7章・9章で「ID リスト自体の保存先は本書では未記載」を解消。
- **K32(指摘②)**: 終了通知の処理の前に `source_id` と `deletion_result.source_id` を照合、不一致は 409(状態・ダイジェスト・一覧は変えない)。「ダイジェストに `source_id` を含めない(意図。推測)」を事前照合に置き換え。未知の `crawl_id` は 202 のまま。
- **K33(指摘③)**: `rewrite_mode` を `deletion_result` の設定スナップショットに保持。バッチ登録時は受理条件の確認で取得した `deletion_result` から参照。開始通知の再送の一致検証の比較項目に `rewrite_mode` を追加(異なれば 409)。API-U-22 の保持先・再送判定は解消、名称(仮)と指定経路(推測)は未決。
- **テスト観点(architecture 16章)**: 新設 D-92(削除 B の待機。上限超過の (c) を含む)、D-93(待機中の再起動)、D-94(`rewrite_mode` の再送)、C-27(複数バッチ)。D-91(m) を 409 に変更し (m1)〜(m3) に分割。D-16、D-79、D-80、C-22(c) を変更。16.1 の決定的再現の手段に D-92/D-93。
- **17章**: K31〜K33 を確定欄に追加(ユーザー確定 2026-11-10)。確定は K12、K18〜K33。案として P42 を新設(writer の推測: `failed`/`cancelled` の受理では一覧を保存しない、一覧の件数が U-2 の上限を超える通知では一覧を保存せず超過の事実と合計件数だけを記録し `validation_failed` にする、一覧の削除は終端状態への遷移と同じ書き込みで行う)。

## 確認(メイン)
- 禁止語(`reconcile` `summary_*_hash` `scripted_upsert` `v0.7` `従来` `変更点`)は4文書で 0 件。`pending_index` は architecture の K18 決定文のみ。ID の重複は C-23(16.10 の既知の行)のみ。K34 以降への参照なし。
- **食い違いを発見**: 終了通知の `source_id` 不一致の 409 のエラー名が、architecture(9.5 の拒否の分類表。登録の拒否と同じ `crawl_source_mismatch` を流用する案)と api(`finish_source_mismatch`(案)を 3.4 と 4.4 で定義)で異なる。どちらも案。→ api の `finish_source_mismatch`(終了通知専用)に統一する方針で、再レビュー後の修正で architecture と loreley-deletions を直す。

## 判断・設計上の理由(writer の推測)
- 一覧の保存条件・上限超過時・削除タイミングは P42(案)。api writer は「一覧の削除を終端状態の更新と同じ書き込みで行うかは実装時に決める」、architecture writer は「同じ書き込みで削除する(案)」と書き、表現が異なる(再レビューで確認)。
- `source_id` の照合は、形式検証(400)の後、再送判定より前に置く(api)。

## 未対応事項
- 再レビュー(document-reviewer、test-reviewer)、task-reviewer は未実施(次)。
- 上記の食い違い(エラー名)、P42 の扱い(ユーザー判断待ち)。
- ユーザー承認待ち・未決: U-1(url/path)、P38、P33、P42、G-12、API-U-7/19/20/22(名称と指定経路)、ダイジェスト・一覧の項目名(U-14)、一覧の件数上限(U-2)、409 のコード名(`finish_content_mismatch`、`finish_source_mismatch`)、U-4、U-30、U-31、数値。確定は K12、K18〜K33。
- 外部レビューの「既存の未決事項」の表(`url`/`path`、`fetched_at`、`metadata`、`summary_embedding`、P33、`delete_by_query` の再実行上限、要約生成の負荷制御)は今回反映していない(ユーザー未承認)。
- 引き渡し事項・SD v0.8 の改版・外部レビューの「実装して試験」は 0038 のとおり。
