# 0032 タスクレビューと完了(loreley-texts 廃止の作業範囲: 0022〜0032)

## プラン承認の記録
- 0022(loreley-texts 廃止のプラン)は、ユーザーが 2026-11-10 に「プランを承認する」と承認した。0022 のステータス欄は「承認待ち」のままだが、0022 は書き換えない(既存の作業記録は書き換えない運用)。承認済みはこの記録を正とする。
- 承認後のプラン変更: 0023(スナップショット復旧を設計の対象外に)、0025(書き込みは PUT 基本)。いずれもユーザー自身の指示による範囲の縮小・調整で、再承認は不要と判断した。0029 はレビュー後のユーザー判断(J1〜J3)。

## task-reviewer の結果
- 完了可(差し戻し不要)。Critical / Important なし。要件(0000)と 0022〜0029 のユーザー指示が5成果物に一貫して反映。確定は K12、K18〜K21 のみ。作業記録の連番(0022〜0031)に抜け・重複なし。
- Suggestion: (1) プラン承認の記録 → 上記で対応。(2) 最終ラウンド修正後の再確認が未実施 → 下記「未対応事項」に引き継ぎ。(3) PD 403 行付近の既存の実装語(D1 の `last_seen_at`。v0.15 から変更なし) → 下記に引き継ぎ。
- Nitpick: 「ユーザーが決めたこと」と「writer の導出」の区別は PD 9.1 と api の確認状況で分けられており、対応不要。

## 成果物(v0.5 までの版は履歴として変更していない)
- docs/v0.x/system-design/indexer/indexer-architecture-v0.6.md
- docs/v0.x/system-design/indexer/indexer-api-v0.6.md
- docs/v0.x/system-design/opensearch/schema/search-index-v0.6.md
- docs/v0.x/system-design/opensearch/schema/loreley-deletions-v0.6.md
- docs/v0.x/product-design/product-design-v0.16.md
- (`loreley-texts-v0.6` は作らない。system-design-v0.x.md は要件どおり修正しない)

## 未対応事項(最新)
- **再確認が未実施**: 0031 の修正(復旧範囲の書き分け、PD の実装語、architecture の細部の注記)の後の document-reviewer による再レビュー。architecture の G-9(通読による整合確認)は「再レビューで通読済み。修正後の再通読は未実施」。0030 で変更した architecture 16章のテスト観点の test-reviewer による再確認も未実施(軽量な再確認でよい)。
- **PD 403 行付近**: D1 の記述に実装語(`last_seen_at`)が残る(v0.15 から変更なし)。次版で整理するか、ユーザーに確認。
- **ユーザー承認待ち(案)**: P34〜P41(K20 で確定した分を除く)、U-1(url/path)、API-U-7(`write_conflict`/`update_conflict` の Crawler 側の扱い)、API-U-18(受理条件 P36 の採否)、API-U-21(案A/案B)、API-U-22(`rewrite_mode` の保持先)、G-10〜G-12(導出・推測)、P39(再書き込みモード。名称と開始通知の指定経路は仮)、`update_conflict` の名称、ソース削除の再実行上限(U-31(5))。
- **未決(実機確認・方針)**: U-22(ソース削除ロックの採否。Crawler 設計)、U-30(Admin API の索引読み取り)、U-31(実機確認項目: Delete の `not_found`、`if_seq_no` 付き操作の応答、`retry_on_conflict` の値、読み直し上限、日付形式、`_reindex` 中断)、U-32(`indexed`→`extract_failed` の旧 `content`・要約の扱い)、スナップショットが時点を揃える保証(推測)。要約の有効化後の既存文書と `failed` の再試行は後で再検討(PD 9.2、architecture 7.3、U-9)。
- **引き渡し事項(次の Crawler / Search API / Admin API 設計)**: ソース削除ロックの採否と Crawler 向け要件(1)〜(4)、Admin API が検索インデックスを読む設計、get_document の範囲切り出し(Search API が ID で GET して切り出す)、`write_conflict`/`update_conflict` の Crawler 側の扱い、要約の再試行方針。
- system-design-v0.8 は旧方針のまま(PD 改訂履歴に「次の SD 改版で追従。それまでは PD を正」と注記済み)。
- 0021 の未対応事項のうち、PD v0.15 の document-reviewer 未実施は v0.16 で再レビューした(v0.15 は履歴)。K12 と P28 の確定待ちは、K12 を確定、P28 を突合削除で消滅として解消。PD 4.7 の確認ポーリングと P34/P36 の照合は未実施(P34、P36 は案のまま)。

## 完了チェックリスト
- [x] プランが作業記録に残り、ユーザーの承認を得ている(0022、承認は本記録)
- [x] すべての作業に作業記録がある(0022〜0032)
- [x] レビューとタスクレビューが済んでいる(0028、0031、本記録。ただし最終修正後の再レビューは未実施と記録)
- [x] 未対応事項を最新の作業記録に書いている(本記録)
