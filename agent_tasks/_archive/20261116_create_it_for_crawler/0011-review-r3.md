# 0011 レビュー R3(フェーズ 6 の文書)と指摘への対応

日付: 2026-11-16
レビュアー: document-reviewer(文書の作成者 document-writer とは別)
対象: `docs/v0.x/test-results/crawler-integration.md`、`indexer-integration.md`(9 章追記)、`tests/integration/crawler/README.md`、`deploy/compose/README.md`、`apps/crawler/README.md`(基準コミット `6970478`、未コミット差分)

## 結果

**Critical なし、Important 3 件、Suggestion 9 件、Nitpick 5 件**。「軽微な修正で可」。

確認できたこと(指摘なし): 実測値(13 passed の 44.54s / 43.88s、Indexer 40 passed 37.69s、基準コミット、Docker 20.10.13・compose v2.3.3・uv 0.13.8・VM メモリ・CPython 3.13.4)が実ログ・作業記録と一致。未実施・未確認の項目は確認済みと書かれていない。手順書のコマンド・変数名・ポート・終了コード・テスト関数名・シナリオ ID(13 件)・相対リンクが実物と一致。発見事項(ループバック公開、上限の受け渡し、`config_invalid`、CIT-23)が書かれている。`indexer-integration.md` の既存の 1〜8 章は書き換えられていない。作成者の確認事項(`deploy/compose/README.md` の「OpenSearch 2.19.7 での測定」付記)は正しい(アイドル時メモリは 2.19.7 の記録にのみある)。

### Important

| # | 指摘 | 対応 |
| --- | --- | --- |
| I1 | `apps/crawler/README.md` 9 章の導入文が、直後の表と矛盾(「`auto_create_index` の判断を除いて完了」だが、表には「既存の環境への反映」未対応・「arch U-24」未決もある) | 反映する |
| I2 | 結果記録 6 章の「未実施」一覧が、4.3・README 8 章で未実施・未確認とした項目(非 ASCII 名の `document_id`、`non_unique_sort`、Status API の `waiting_for` 等、`lock` 拒否側、`enabled` の fail-closed、Indexer のメンテナンス停止経路、降順ソート、PIT 期限切れ・バルク部分失敗、arch 12 #39 など)を拾っていない | 反映する(6 章に足し、4.3 が項目別判定の正本であることを明記、tests README の案内も合わせる) |
| I3 | Fess がテスト用 OpenSearch に書き込んだ、という記述が事実として書かれているが、根拠は `fess_config.coordinator` 索引の存在だけで、プロセスの特定は未確認(推定) | 反映する(3 文書で「推定(プロセスの特定は未確認)」にそろえる) |

### Suggestion / Nitpick の対応

反映する: 内部作業用の用語(R1/R2・実装担当・code-reviewer・フェーズ N)の除去、README 8 章と結果記録 4.3 のラベル定義・語の統一(CFS-U-4 の項目にもラベル)、手順書(手動)の実行確認(0010 の 37.94s)を結果記録に追加、5 章 8 の「食い違いの調査は範囲外」を `20261113_upgrade_opensearch` による更新という事実に修正、4.2 の「干渉しなかった」の対象の明確化、CIT-01 の 3 件目の記述を実際のアサート範囲に限定、5 章に「`loreley-sources` の `dynamic` を strict に決めた」を追加、`apps/crawler/README.md` の更新漏れ(「compose は別タスク」「前提・スコープ外(別タスク)」)、tests README の「ID は…にだけある」の訂正と終了コード 4 の注記、4.2 に途中の実行ログの注記。

反映しない: `indexer-integration.md` の冒頭の更新日・関連(必須でない)、VM メモリの丸め表記(誤りではない)。

反映は document-writer が実施中。Important があるため、**同じ `document-reviewer` で再レビューする**。

## レビュアーが確認できなかったこと(Bash の一時的な失敗)

`crawler-api-v0.4.md` の 4.4.2 の見出しの有無、`indexer-architecture-v0.10.md` の 9.6・9.14 の見出しの有無、IT-41・IT-42 の内容と結果記録 4.3 の ID の 1 対 1 対応。再レビューで改めて確認を依頼する。

## 次にやること

1. 反映結果を確認し、`document-reviewer` で再レビュー
2. タスクレビュー(`task-reviewer`)
3. 最終報告
