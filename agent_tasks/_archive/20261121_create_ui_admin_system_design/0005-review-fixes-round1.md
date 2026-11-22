# 0005 レビュー(1回目)と指摘対応

- 日付: 2026-11-21
- レビュー: `document-reviewer`(対象 `docs/v0.x/system-design/ui-admin/ui-admin-functions-v0.1.md`、比較基準 SHA `171a828`。他文書の変更なしを確認済み)
- 修正: `document-writer`(成果物1文書のみ変更)
- 総評: Critical なし、Important 4件、Suggestion 多数、Nitpick 数件。

## 指摘と対応

| 重要度 | 指摘 | 対応 |
| --- | --- | --- |
| Important | AF-P-6 の理由が「再インデックス」と混同(`rewrite_mode` は全件再書き込みのクロール指定) | 反映。理由を「PD §4.6 に項目なし・要件0000にもない」に直し、再インデックス(SD §2.5、AF-21)とは別物と明記。5章に注記(機能IDは付けず) |
| Important | AF-14 の要約暫定方針の確度が「案」(実物は IA K64 確定) | 反映。確定と記載、failed 遷移条件・再実行手段は未決(IA U-9、PD §9.2 #13、AF-U-4)。要約有効化で Indexer が起動しない現状も追記 |
| Important | 設定の反映時点(実行待ちジョブには反映される) | 反映(crawler-api §4.4.1・§2.2、CA-P-51) |
| Important | 強制削除の確認操作を断定 | 反映。データソース削除(UC-5)のみ確認操作を置く。強制削除は PD §9.2 #10 未決(AF-U-7) |
| Suggestion | 承認済みの案の範囲(CA-P-1〜55 承認、56〜76 実装で決めた内容、77 未承認)、8.2 の依拠 AF 表 | 採用 |
| Suggestion | 「矛盾なし」と本文の不整合の書き分け | 採用 |
| Suggestion | 6.2 の引用元(契約外は crawler-api §1・§4.7 / indexer-api §1。SD §7.3 は稼働確認方法を §12.5 に委ねる) | 採用 |
| Suggestion | AF-U-7 に ttl・min_delete_count の入力検証を追加 | 採用 |
| Suggestion | AF-19 は AF-6・8・10 の表示の一部と明記、6.3 に AF-19・AF-P-7 を追加 | 採用 |
| Suggestion | AF-1・AF-7 に source_id 重複・孤児ロック等の周辺ケースを追記 | **不採用**(既存設計の内部詳細で、再掲しない方針。MVP は簡潔に) |
| Nitpick | 出典の確度の書き分け(CAPI-P-8/P-13/P-30、CAPI-K-9/P-19/IA K67)、「利用者への表示方法」の語 | 採用 |
| Nitpick | 「取消/取り消し」の表記統一 | **不採用**(軽微) |

## 変更ファイル

- `docs/v0.x/system-design/ui-admin/ui-admin-functions-v0.1.md`

## 未対応事項(完了報告時にユーザーへ確認)

- ユーザー未確認の前提: AF-P-5(インデックス件数はデータソース単位)、AF-P-6(`rewrite_mode` は Admin View で扱わない。画面指定は将来拡張の候補)、AF-P-7(ジョブ記録の警告表示)、AF-U-8(再実行時の `force_delete` 引き継ぎ)
- 文書が PD 追従改訂の対象を3点に拡げた(OpenSearch 最小ビュー/Admin API の検索インデックス・OpenSearch 読み取り範囲/ダッシュボード)。要件確認時は OpenSearch 最小ビューのみだった
- AF-4 は「実行待ち」も取消対象に含めるが、ユーザー回答 Q2 は「実行中ジョブの取消」
- 0001 の「`force_delete` / `rewrite_mode` 指定時は通知」と AF-P-6 の軽い食い違い(0001 は書き換えない。文書は「強制削除などの指定」と記載)
- `CLAUDE.md` の参照先に `docs/v0.x/system-design/ui-admin/` を追記するか(ユーザー判断)
- `apps/` と Indexer の実装は未確認(設計書のため対象外)

## 次にやること

- Important 修正の再レビュー(document-reviewer)→ 作業記録・STATUS 更新 → task-reviewer
