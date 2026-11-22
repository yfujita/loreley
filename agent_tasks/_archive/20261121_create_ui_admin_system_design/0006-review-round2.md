# 0006 再レビュー(2回目)と指摘対応

- 日付: 2026-11-21
- レビュー: `document-reviewer`(対象 `docs/v0.x/system-design/ui-admin/ui-admin-functions-v0.1.md`。比較基準 SHA `171a828`、他文書の変更なしを確認済み)
- 結果: **Critical・Important なし**。1回目の Important 4件はすべて「解消」(実物の出典と照合済み)。Suggestion 3件、Nitpick 3件。
- 修正: メインエージェントが軽微な修正として直接反映(文書内の数行。Suggestion/Nitpick 計6件すべて採用)。

## 1回目 Important の判定

| 指摘 | 判定 |
| --- | --- |
| AF-P-6 の理由(再インデックスとの混同) | 解消 |
| AF-14 の確度(IA K64 確定) | 解消 |
| 設定の反映時点(実行待ちには反映) | 解消 |
| 強制削除の確認操作の断定 | 解消 |

## 2回目の指摘と対応

| 重要度 | 指摘 | 対応 |
| --- | --- | --- |
| Suggestion | AF-P-6 と 0001 の `rewrite_mode` 通知の食い違いが文書内で未説明(AF-6、AF-U-3(a) の「強制削除など」) | 採用。AF-6 に「`rewrite_mode` は AF-P-6 により通知の対象外(0001 の前提から範囲を狭めた)」を追記、AF-U-3(a) を「強制削除の指定」に修正 |
| Suggestion | 8.2 の依拠表の抜け(AF-8 に CA-P-10、AF-19 に CA-P-10、AF-3 に CA-P-13) | 採用 |
| Suggestion | `status=deleting` の更新不可の確度表記のずれ(AF-1、AF-16) | 採用。起動拒否は `CAPI-K-4`(確定)、設定更新の拒否は `CAPI-P-9`(承認済みの案)に書き分け |
| Nitpick | AF-10 の「案」→「承認済みの案」(CA-P-30) | 採用 |
| Nitpick | 0 章「項目はレベルまでで」の表現 | 採用 |
| Nitpick | AF-U-5(c) が本文に紐づいていない | 採用。3.4 に1行追記 |

## 変更ファイル

- `docs/v0.x/system-design/ui-admin/ui-admin-functions-v0.1.md`(文書内の数行)

## 確認できなかった点(レビュアー報告)

- PD §4.7 の長文の後半、SD §3.3 の本文、`apps/` と Indexer の実装(設計書のため対象外)

## 未対応事項(完了報告時にユーザーへ確認)

- 0005 の未対応事項と同じ(AF-P-5/6/7、AF-U-8、PD 追従改訂の範囲3点、AF-4 の「実行待ち」も取消対象、`CLAUDE.md` 参照先追記の要否)

## 次にやること

- `task-reviewer` でタスク全体を確認する
