# 0026 indexer-architecture-v0.6 の作成(F2)

## 概要
document-writer が `docs/v0.x/system-design/indexer/indexer-architecture-v0.6.md`(1146行)を新規作成した(v0.5 は変更していない)。F2 は2回、ユーザー操作で停止され(0023、0025 の方針変更)、3回目の依頼で完了。方針は 0022、0023、0025 に従う。

## 変更したファイル
- docs/v0.x/system-design/indexer/indexer-architecture-v0.6.md(新規)

## 変更内容の要点(章ごと)
- 1〜3章: 検索インデックスが唯一の正本。`_source.content` 保持が必須。get_document は Search API が ID で GET して範囲切り出し(Indexer API にエンドポイントは追加しない)。Repository の対象は sources / jobs / deletions のみ。
- 4.3 / 5章: 書き込みは「全文書き込み(PUT。新規は `op_type=create`、既存は GET→`if_seq_no`/`if_primary_term` 付き)」と「`last_seen_at` 部分更新(Update。現在値以上なら noop、404 は何もしない)」の2種。要約の書き戻しは PUT(生成元の `content_hash`/`text_hash` が現在値と一致するときのみ。不一致は破棄、409 は読み直し)。全件処理は、取得・抽出して比較し、変更ありだけ PUT、変更なしは `last_seen_at` が古ければ Update で補う。
- 6〜8章: 整合性・排他を `if_seq_no`、`op_type=create`、`_reindex` 後の `_seq_no` 振り直しに書き換え。書き込み排他(P27)を削除。
- 9.8 / 9.14: 削除は TTL 再確認 → `if_seq_no` 付き削除、409 は読み直して再判定(上限超過は次の期限削除に委ねる)。ソース削除は `delete_by_query`(`conflicts=proceed`、`version_conflicts≠0` なら再実行)。
- 10章: 「食い違いの扱い」に置換。11章: `_reindex` のみ(スナップショットは運用者の任意と1文)。14章: 復旧範囲(マッピング等の変更→`_reindex`、索引喪失・抽出ロジック変更→再クロール、要約ロジック変更→再書き込みモード)。
- 16章: 突合・pending_index・メタデータ分離・P27・P30 の観点を欠番にし、追加: C-18〜C-23、D-87〜D-90、R-8、E-44(既存の C-10 ほかは新方式に合わせて修正)。
- 17章: 確定欄に K12(P31)、K18(loreley-texts 廃止)、K19(書き込みは PUT 基本)。新規の案: P39(再書き込みモード)、P40(書き込みの細部)、P41(`delete_by_query`)。未決: U-30(Admin API の索引読み取り)、U-31(実機確認項目と数値)。17.5 に欠番一覧。

## 確認
- メインが禁止語を grep: `pending_index` `pending_since` `pending_content_hash` `突合` `reconcile` `summary_text_hash` `summary_content_hash` `Store 層からの再構築` `scripted_upsert` `従来` `変更点` `v0.5` は 17章(K18 の決定文、17.5 の欠番一覧)以外で 0 件。`loreley-texts` も同様。「現行世代」は削除の世代管理の用語として残る(旧版への言及ではない)。

## 判断・設計上の理由(writer が推測で置いた箇所)
- 再書き込みモード: v0.5 に差分チェックなしのモードがなかったため、案 P39(名称仮。開始通知で渡す経路は推測)とした。
- 全件処理: 0025 の「本文が変わらなければ要約も更新しない」を当てはめ、「変更なしは PUT しない」に改めた。変更なしでも `last_seen_at` が古ければ Update で補う(導出)。
- `deleted_count`: すでに削除済みの文書は数えない(推測。U-31 で実機確認)。
- `size` も検索インデックスの文書に持つ前提(search-index v0.6 で定義が必要)。
- 要約の再走査は `summary_status=pending` を検索で列挙し、`content` から再生成する(P15)。

## 未対応事項・次にやること
- F3 への申し送り: api v0.6(再書き込みモードの指定経路、`change` 区分、API-U-18 `purpose` 廃止、API-U-19 のエラー名)、search-index v0.6(`size`、`content` を `_source` に保持、`extractor_version`/`extract_fail_count` の置き場)、loreley-deletions v0.6(14章の記述との整合)。
- ユーザー承認待ち: P39、P40、P41、および v0.5 から引き継いだ案(P34、P36、P37、P38、P35、U-1 url/path、ソース削除ロック)。確定欄は K12、K18、K19 のみ。
- G-9(通読による整合確認)は未完了。reviewer の確認が必要。
- F3: api / Schema 2文書 / PD v0.16 の作成、F4 以降は未実施。
