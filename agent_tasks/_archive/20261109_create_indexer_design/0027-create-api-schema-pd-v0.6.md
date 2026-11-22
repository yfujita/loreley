# 0027 api / Schema 2文書 / PD v0.16 の作成(F3)

## 概要
document-writer 3体が並列で作成した。architecture v0.6(0026)と整合させる指示。v0.5 系・PD v0.15・architecture v0.6 は変更していない。

## 変更したファイル(すべて新規)
- docs/v0.x/system-design/indexer/indexer-api-v0.6.md(約760行)
- docs/v0.x/system-design/opensearch/schema/search-index-v0.6.md
- docs/v0.x/system-design/opensearch/schema/loreley-deletions-v0.6.md
- docs/v0.x/product-design/product-design-v0.16.md
(`loreley-texts-v0.6` は作らない。v0.5 は履歴として残す。)

## 変更内容の要点
- **api v0.6**: 突合 API(旧 4.9)と `purpose` を削除(旧 4.10 は 4.9 に繰り上げ)。バッチ登録は 4.3 で、新規=`op_type=create` の PUT、変更なし=書かず(`last_seen_at` が古ければ Update)、変更あり=GET→`if_seq_no` 付き PUT。`change` は `created`/`updated`/`unchanged`。409 の読み直し上限超過は文書単位の失敗(`write_conflict`。名称は仮)。ソース削除は `delete_by_query`。`rewrite_mode`(開始通知の任意項目。案 P39。名称は仮)。新規 API-U-22(`rewrite_mode` の保持先と再送の一致検証)。API-U-11・API-U-18 は欠番。確定は K12・K18・K19。
- **search-index v0.6**: 唯一の正本、`_source.content` 保持必須、`index_status` は `indexed`/`extract_failed`、`size` を新設(型 long は仮置き)、`extractor_version`/`extract_fail_count` は予約項目、マッピング方針(strict、keyword 化、shards 1)を自身の方針として定義、`_reindex` のみ、復旧範囲の表、R-5 欠番。
- **loreley-deletions v0.6**: 受理条件の対象外をソース削除のみに、条件付き削除の競合は読み直して再判定、7章の方針を search-index v0.6 の参照に置換、スナップショットは運用者の任意。
- **PD v0.16**: 検索インデックスが唯一の正本(1.6、3章、4章、4.8、5.1、10章)、突合ジョブを MVP から削除(4.6、5.2 の4、8.1、8.2、10章)、6.2 を「バックアップと復旧」に(再クロール。スナップショットは任意。`_reindex`)、2章に主要リスク追加、9.1 に 2026-11-10 の決定事項(loreley-texts 廃止、突合削除、PUT 基本、K12 確定)。P39 や P34/P36/P37/P38 は PD に入れていない。

## 確認
- メインが禁止語を grep: api・search-index・loreley-deletions は `pending_index` `pending_since` `reconcile` `summary_text_hash` `summary_content_hash` `loreley-texts` `scripted_upsert` `突合` が 0 件。PD v0.16 は `突合`・`loreley-texts` が改訂履歴と 9.1 の決定事項にのみ残る。
- Schema 2文書から api への参照: `loreley-deletions-v0.6.md` が API-U-18 を3か所(約136、199行)で参照しているが、api v0.6 では API-U-18 は欠番(`purpose` 廃止で解消)。**不整合の疑い。レビューで確認し修正する。** search-index v0.6 の `api-v0.6.md 4.3` は存在する章。

## 判断・設計上の理由(writer が推測で置いた箇所)
- `write_conflict` の Crawler 側の扱い(リトライし、直らなければスキップ。連続 20 件の計数に含めるかは未決)。API-U-7 に含めた。
- `rewrite_mode` の指定経路(開始通知の任意項目)は推測。
- マッピング方針は architecture G-1 が「推測」扱いのため、search-index 10章に「ユーザー未確認」と注記。
- `size` を `documents[]` で Crawler が渡すか Indexer が求めるかは未決(api の決定待ち)。
- PD 9.1 に「Update は最後に見つかった日時の更新に限る」「本文が変わらない文書の要約は更新しない」を決定事項として記載(0025 のユーザー回答に基づく)。

## 未対応事項
- PD の残存: 8.2 最終行「スナップショットによるバックアップとリストアの手順を README に記載している」と 6.2「バックアップ・リストア手順を用意する」が、スナップショットは運用者の任意とする方針と食い違う可能性。PD は SD v0.8 参照(§3.6 を 5.2 末尾から外した。SD の中身は未確認)。`loreley-sources` の設定のインデックス喪失時の戻し方(6.2 は「設定ファイルをバックアップ」のまま)。
- `size` の扱い、G-9(通読確認)は未完了。
- ユーザー承認待ち(案): P34、P35、P36、P37、P38、P39、P40、P41、U-1 url/path、ソース削除ロック、API-U-21 の案A/案B、API-U-22。
- F4 レビューは未実施(次)。
