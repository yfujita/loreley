# 0034 v0.7 / PD v0.17 の作成

## 概要
0033 のプランに従い、document-writer 3体が並列で作成した(architecture / api+search-index+loreley-deletions / PD)。いずれも v0.6(PD は v0.16)のコピーから新規作成し、v0.6 以前は変更していない。`loreley-texts-v0.7` は作らない。

## 変更したファイル(すべて新規)
- docs/v0.x/system-design/indexer/indexer-architecture-v0.7.md(1181行)
- docs/v0.x/system-design/indexer/indexer-api-v0.7.md(781行)
- docs/v0.x/system-design/opensearch/schema/search-index-v0.7.md(347行)
- docs/v0.x/system-design/opensearch/schema/loreley-deletions-v0.7.md(212行)
- docs/v0.x/product-design/product-design-v0.17.md(510行)

## 変更内容の要点
- **外部レビュー①(スナップショット)**: K21 は維持。「取得時点の状態に復元できる。整合した復元は、関連する書き込み(クロール、削除、要約の書き戻し)を止めて取得した場合。停止せず取得したものは、設定・ジョブ・削除結果・文書の時点がずれうる(取得時点はシャードごとに異なりうる)」。architecture 1.1・14.1・14.2・12章・K21・16.1、search-index 6章・10章、loreley-deletions 7章・9章、api 6章の K21 行、PD 2章・6.2・8.2・9.1・改訂履歴。PD には実装語を入れていない。
- **K30(U-32 解消)**: `indexed` が抽出失敗になったら旧 `content`・`text_hash`・要約を消して `extract_failed`(`summary_status=disabled`)。最終成功時の本文は MVP では保持しない。E-45 の期待結果に追記。
- **K22〜K29(案の確定)**: K22=P35(`text_hash`)、K23=P36(登録の受理条件6条件。U-28 の(a)〜(e)を含む)、K24=P37(開始通知再送の検証)、K25=P34 案B(終了通知の異なる再送は 409)、K26=P39(再書き込みモード。名称・指定経路・保持先は仮のまま)、K27=P40(GET→`if_seq_no` 付き PUT)、K28=P41(`delete_by_query`。再実行上限は設定、値は U-31(5))、K29=ソース削除のロックは最後まで保持(U-22 解消。Crawler 要件(1)〜(4)として確定)。確定は K12、K18〜K30。確定した項目は 17.2/17.3 から外して 17.5 の欠番記録へ(api・search-index・loreley-deletions は、確定した項目を欠番にせず「確定(Kxx)」として表の位置を保つ)。
- **K25 の設計(writer が具体化)**: 終了通知の内容のダイジェストを、最初の受理と同じ書き込みで `deletion_result` に保存。再送は一致なら 202、不一致なら 409 `finish_content_mismatch`(名称は案)。architecture 9.5・9.12・12章・13.3・1.3・2.2・8章、api 1章・3.4・4.4・6章、loreley-deletions 2.2 に反映。ダイジェスト項目名は未決。D-91(ダイジェスト方式の検証)を新設。
- **外部レビュー③④(性能)**: architecture 15.3 に「変更なしでも全列挙文書に `last_seen_at` の Update が発生し、書き込み負荷は変更の有無に依存しない」。15.4 に測定項目(`last_seen_at` Update の処理時間・インデックスサイズ・マージ負荷、要約書き戻しの処理時間と競合回数)。api 4.2、search-index 5.2・10章に参照。
- **PUT 基本の方針は変更なし**。

## 確認(メイン)
- 禁止語(`reconcile` `summary_*_hash` `scripted_upsert` `v0.6` `従来` `変更点`)は4文書で 0 件。`pending_index` は architecture の K18 決定文の1件のみ。
- architecture の K20〜K30 が 0033 の対応表と一致。「案(ユーザー承認待ち)」が残るのは確定対象外の項目(U-16 url/path、P38 change 区分、P33 T>D ガード)と冒頭の凡例のみ。ダイジェストは architecture・api・loreley-deletions で一貫して記載(項目名は未決)。
- PD v0.17 は v0.16 との diff で、ヘッダ・改訂履歴・2章・6.2・8.2・9.1 の範囲のみ。PD と K22〜K30 の矛盾は見つからなかった(writer が検索で確認)。

## 判断・設計上の理由(writer の推測・解釈)
- K23 に U-28 の(a)〜(e)(「終端状態は拒否」を含む)を含めた(「P36 を採用」に含まれるとみなした)。
- K25: 受理済みかどうかの判定を `finish_received_at` ではなくダイジェストの記録の有無にした(`failed`/`cancelled` では `finish_received_at` を記録しないため。推測)。ダイジェスト保存前の遅れた終了通知は比較せず 202(api writer の補足)。
- K27 の範囲: 「変更なしは PUT しない」(G-10)と「`last_seen_at` を補う Update」(G-11)を含めた。G-10/G-11 は導出のままの区分で、「K27 の範囲に含む」と注記。**範囲の取り方は要確認**。
- P29 のうちロック保持だけを K29 へ。`discarded` の優先と応答のタイミングは案のまま。U-22 の残り(停止確認の細部は P7、PIT の要否・100万件のメモリは P33 と15.4、リース切れは K29 の要件(1)(2))は私(writer)の整理(推測)。

## 未対応事項
- document-reviewer / test-reviewer によるレビューは未実施(次)。task-reviewer も未実施。
- ユーザー判断待ち: 409 の本文に受理済みの状態を載せるか Status API で照会するか(U-4)、「削除中」の状態の置き場所(U-4)、K27 の範囲(G-10/G-11 を含めるか)。
- 未決・案のまま: U-1(url/path)、P38(change 区分)、P33(T>D ガード)、API-U-7(`write_conflict`/`update_conflict`)、API-U-19(拒否の応答コード・エラー名)、API-U-20(K24 の比較前の正規化)、API-U-22(`rewrite_mode` の名称・指定経路・保持先)、ダイジェストの項目名、各種の数値(上限・`retry_on_conflict` など)、G-10〜G-12、U-30(Admin API の索引読み取り)、U-31(実機確認項目)。
- 引き渡し(次の Crawler / Search API / Admin API 設計): ソース削除ロックの保持と Crawler 要件(1)〜(4)(K29)、Admin API の索引読み取り、get_document の範囲切り出し(Search API)、`write_conflict`/`update_conflict` の Crawler 側の扱い、要約の再試行方針、SD v0.8 の改版(旧 Store 層・突合・再構築の記述の更新)。
- 外部レビューの「次は実装して OpenSearch で競合試験・性能試験を始める」は、設計書の範囲外。U-31 の実機確認項目が実装時の試験項目になる。
