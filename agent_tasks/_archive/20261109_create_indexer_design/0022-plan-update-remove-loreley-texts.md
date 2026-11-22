# 0022 プラン更新: loreley-texts の廃止

## ユーザー指示(方針変更)
「loreley-texts は二重管理になり制御が複雑になっているので削除する」(2026-11-10)。外部意見(貼り付け)を採用: 検索インデックスを本文・メタデータ・要約・処理状態・last_seen_at の唯一の正本にする。U-21 は「廃止」で確定。
方針が変わる(構成・スコープ・設計判断)ため、プランを更新する。planner の草案をもとに、下記のユーザー回答を反映した。

## ユーザー確認済みの回答(2026-11-10)
- Q1 突合ジョブ: **MVP から完全に削除する**(P14/P19/P20/P28、U-27、`POST /sources/{id}/reconcile`、pending 警告も削除。13.4 に将来拡張として1行残してよい)。
- Q2 版の方針: **Indexer 2文書・search-index・loreley-deletions は v0.6 を新規作成、PD は v0.16 を新規作成**。loreley-texts は v0.6 を作らず、v0.5 は履歴として残す。
- Q3 K12(P31): **確定扱いにする**(PD v0.15 に反映済み)。P28 は突合削除で消える。

## 確定事項
- 検索インデックスが唯一の正本。`_source` に `content` を保持することが必須。「検索インデックスは Store 層から作る派生物」の方針を撤回。
- 廃止: loreley-texts、Store→索引の2段階更新、pending_index(pending_since / pending_content_hash)、Store 更新成功・索引失敗の復旧、突合、Store 側 summary_text_hash(summary_content_hash 含む)、二重削除、P26(メタデータ分離)、P27(書き込み排他)、P30。
- `index_status` は `indexed` / `extract_failed`。`last_seen_at` の部分更新(max)は維持。要約は `content_hash` と `text_hash` の一致を条件に条件付き更新(生成元ハッシュは非同期処理のコンテキストで保持)。`text_hash` は存続。
- 削除は TTL 再確認 → `if_seq_no` / `if_primary_term` 付き条件付き削除。競合(409)は読み直して再判定。リトライ上限超過なら削除せず次の期限削除に委ねる。
- loreley-sources / loreley-jobs / loreley-deletions は維持。Repository 抽象の対象はこの3つ(検索インデックスは対象外)。
- get_document は Search API が検索インデックスを ID で GET し、アプリ側で範囲を切り出す(Indexer API にエンドポイントは追加しない)。
- 復旧範囲を明文化: マッピング/アナライザ変更は `_reindex`、インデックス喪失はスナップショットからリストア、スナップショットもなければ再クロール(`last_seen_at` 初期化、要約再生成)、抽出ロジック変更は再クロール。
- メンテナンスフラグ(P10)は存続。`_reindex` 前のスナップショットと旧インデックス保持を追加(推奨)。
- ソース削除: delete_by_query で `source_id` の文書を削除。ロックの採否は Crawler 設計に引き渡し、Crawler 向け要件(1)〜(4)は前提として残す。
- `purpose`(API-U-18)は突合が消えるため廃止(推奨)。
- 置いた前提: 章番号は維持(10章は「食い違いの扱い」に置換)/ v0.6 各文書は旧版・経緯に言及しない(経緯は作業記録と PD 改訂履歴のみ)/ テスト ID は付け替えず欠番/ Admin API が索引を読み取り専用で読む件は Admin API 設計に委ね未決として記録。
- system-design-v0.x.md は修正しない。0000 は書き換えない。

## 成果物
- 新規: `indexer-architecture-v0.6.md`、`indexer-api-v0.6.md`、`search-index-v0.6.md`、`loreley-deletions-v0.6.md`、`product-design-v0.16.md`
- 作らない: `loreley-texts-v0.6.md`(v0.5 は変更しない)
- 各文書の見出し単位の影響範囲は planner 草案(1-A〜1-G)に従う。P/U/K の扱いは、廃止(P14/P19/P20/P22/P23/P26/P27/P28/P30、U-17、U-27、G-3)、縮小(U-1、U-18、U-22、P29、P35、U-9、U-11、U-13)、存続(その他)、新規は P39 以降(欠番再利用なし)、K18=loreley-texts 廃止。

## フェーズ
- F1 技術確認(tech-advisor): `if_seq_no`/`if_primary_term`(スクリプト update 含む)、`_reindex` が `_source` から再構築できること、`_source` 保持のサイズ増、スクリプト update の noop 判定、スナップショットのリストア影響、`delete_by_query` の競合。
- F2 architecture v0.6(document-writer 1体)。完了後、禁止語を grep(`pending_index` `loreley-texts`(K18 決定文を除く)`突合` `reconcile` `summary_text_hash` `summary_content_hash` `pending_since` `pending_content_hash` `Store 層からの再構築`)。
- F3 並列 document-writer 3体: api v0.6 / search-index + loreley-deletions v0.6 / PD v0.16。
- F4 レビュー(並列): document-reviewer ×3(architecture / api+Schema2文書 / PD)、code-reviewer(設計書内のマッピング JSON・script・API 例の妥当性)、test-reviewer(16章の観点の妥当性)。
- F5 指摘対応: Critical/Important を解消するまで F4〜F5 を繰り返す。
- F6 作業記録(メイン)。引き渡し事項: ソース削除ロックの採否、Admin API が索引を読む件、get_document の範囲切り出し、スナップショット運用。0021 の未対応事項(PD v0.15 の未レビュー、P34/P36 との照合)の扱いも明記。
- F7 task-reviewer。

## 主なリスク
- `_source` 保持によるサイズ増と get_document の取得量 → 15.4 に実測項目を追加。
- 唯一の正本になることによる誤操作の影響 → スナップショット運用と旧インデックス保持を明文化。
- 要約再生成コスト(再クロール時) → 復旧範囲の表に明記。
- 競合制御の見落とし → F4 の観点とテスト観点に追加。

## 未決事項
- 全文書き込みを GET+`if_seq_no` にするかスクリプトにするか(F1 の結果で確定)。
- 削除競合のリトライ上限、ソース削除ロックの採否(Crawler 領域)、スナップショット周期(U-13)、Admin API の索引読み取り設計。

## ステータス
ユーザーの承認待ち(承認後に F1 から実施)。
