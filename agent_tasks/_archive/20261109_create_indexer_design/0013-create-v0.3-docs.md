# 0013 v0.3 の作成 作業記録

## 概要
0012 のプランに基づき、document-writer 3体が Indexer 5文書の v0.3 を新規ファイルで並行作成した。v0.2(および v0.1)は変更していない。SD への言及・「変更点」章・旧版への言及なし(各担当が grep で0件を確認)。ユーザー未確定の設計判断はすべて「案」「未決」として記載し、確定扱いにしていない。

## 作成したファイル
- docs/v0.x/system-design/indexer/indexer-architecture-v0.3.md
- docs/v0.x/system-design/indexer/indexer-api-v0.3.md
- docs/v0.x/system-design/opensearch/schema/search-index-v0.3.md
- docs/v0.x/system-design/opensearch/schema/loreley-texts-v0.3.md
- docs/v0.x/system-design/opensearch/schema/loreley-deletions-v0.3.md

## 反映内容(案の ID は architecture 17.2 の P26〜P34)
- P26 同一 content_hash: 原本ハッシュ一致かつ text 一致→Store を書かず検索の全文 upsert のみ(要約は引き継ぐ)。原本ハッシュ一致で text 不一致→pending_index 経路、要約と summary_content_hash を無効化。text_hash は導入しない。G-3 を推測から案(P26)に変更。
- P27 削除排他: 文書単位の削除処理を登録・last_seen 更新と同じ書き込み排他(プロセス内ロック)に含め、Store 削除を if_seq_no 条件付きにした。削除順序 Store→検索は維持。Store 削除の 404 は成功扱い、窓で Store 文書が消えたときの確定更新の 404 は文書単位の失敗(再試行可能)。
- P28 突合は検索のみの文書を検出・表示のみ。
- P29 ソース削除: ジョブは source_id ロックを最後まで保持しロック文書の削除は最後。discard 要請の応答は実行中バッチの終了後。バッチ内ハングは待ち続ける(受容事項)。Crawler 側ロック設計の決定が前提(未決)。
- P30 要約: Store の summary_status は検索反映成功まで pending。再走査は pending かつハッシュ一致→反映のみ、不一致→再生成。
- P31 K12: K12 の文言は変えず、適用範囲の明確化と受理後の応答喪失の例外を案として併記(ユーザー確認待ち)。
- P32 oversize_document_ids を skipped_document_ids と別項目で追加し、E_missing の対象に含める(上限は合計)。deletion_result の複写項目に crawl_started_at を追加。拒否主体は未決。
- P33 削除対象の取得: 開始時に1回抽出してメモリ上で処理、または search_after。from/size は使わない。
- P34 終了通知の再送は常に冪等な 202(先着採用)、409 廃止。
- api 4.3 に crawl_started_at を必須で追加(開始通知と異なる値の検証は必須にしない案=API-U-18)。新規 API-U-15(content_hash 照合)、-16(再送集計)、-17(raw_content の運び方と実測)、-18。architecture に U-26(content_hash 照合)を追加。
- テスト追加(architecture 16章): C-12、C-13、E-40〜E-42、D-73〜D-76。既存 C-10、E-11、D-14、E-30、D-15、D-21、D-39 の文言調整(ID は不変)。search-index 8章に E-7〜E-10 を追加(本書ローカル ID)。
- 15.4 に base64 の実測項目を追加。

## 担当エージェントによる補足(0012 に明示のない判断。すべて案)
- (b)経路(原本ハッシュ一致・text 不一致)では、Store の要約と summary_content_hash を pending_index への書き込みと同時に消す。再走査の「ハッシュ一致→反映のみ」で旧 text 向けの要約が反映されるのを防ぐため。要約生成中に(b)が走った場合の旧要約の保存防止(生成開始時の if_seq_no を条件にする等)は未決として architecture U-9 に追記。
- api 4.6 のソース削除手順: スキップ記録の削除 → 削除の記録 → 設定削除 → ロック文書の削除(最後)。案。
- 突合で検索のみの文書を削除しない場合、元ファイルがなければ last_seen_at が古いまま期限削除の対象になる(検索起点の抽出からの導出)。
- Store 削除の 404 を成功扱いとした(上記と整合)。
- api の突合結果項目: `not_deleted` を `search_only`(形の例。名称は未決)に置換。API-U-9 に change の `unchanged` 追加の選択肢。
- search-index のテスト ID E-7〜E-10 は本書ローカルで、architecture の E-* と番号が重なりうる。

## 未対応事項・次にやること
- 5文書の整合確認(ID 参照、章番号参照、architecture 節番号(9.14、15.4)の参照、テスト ID の重複)と v0.3 の妥当性レビュー(document-reviewer)。
- 各担当は反映後の全文再読を未実施(grep 等のみ)。
- ユーザー判断待ち: P28、P29(Crawler 側のロック設計)、P31(K12 の適用範囲)、P32(拒否主体 U-5)、P34(409 廃止)。U-21(loreley-texts 廃止)は未決のまま。
- プロダクト設計 v0.14(K12 に関わる保証範囲)の修正は本タスクの対象外。別途ユーザー判断。
