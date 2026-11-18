# 0012 R3 指摘の反映と再レビュー

日付: 2026-11-16
文書反映: document-writer / 再レビュー: document-reviewer(R3 と同じ)/ 最終の 2 件の修正: メインエージェント

## 実施した作業の概要

0011 の R3 指摘(Important 3、Suggestion 9、Nitpick)を 4 文書(`crawler-integration.md`、`tests/integration/crawler/README.md`、`deploy/compose/README.md`、`apps/crawler/README.md`)に反映し、同じ `document-reviewer` で再レビューした。再レビューで、反映時に入った事実誤り(Important 2 件)と Suggestion 1 件が見つかり、メインエージェントが直した。

## 再レビューの結果

- 前回の Important 3 件(I1 9 章の矛盾 / I2 6 章の網羅性 / I3 Fess の推定表現)は**解消**。Suggestion 9 件の反映も事実と一致(5 章 8 の `20261113_upgrade_opensearch` による 2.19.7→3.9.0、5 章 10 の `loreley-sources` の strict 決定、CFS-U-4 の「未実施」への変更と旧記述(「macOS・CPython 3.13.4 では確認」。出典が見つからなかった)の削除、途中ログの対応づけ(推定と明記)、手動手順 37.94s の追記)。内部用語は新規・更新部分から除かれていた。前回確認できなかった設計書の見出し(api 4.4.2、indexer-architecture 9.6・9.14)の存在も確認できた。
- 反映時に新たに入った誤り:
  1. **Important**: CIT-01 の備考が「`loreley-jobs` の上記以外の項目(`schedule_cron` など)」と書いていた。`schedule_cron` は `loreley-sources` の項目で `jobs.json` に存在しない(アサートもしている)。→「`trigger`・`last_job_id`・`started_at` などの date 項目、索引しない object 項目」に修正
  2. **Important**: 「Indexer の IT-15・IT-41・IT-42」が所有していない `lock` の拒否(`lock_not_owned`)を確認していると書いていたが、実コードでは IT-15(`test_10_registration.py`)と IT-41(`test_40_source_deletion.py`)だけ。→「IT-15・IT-41。ソース削除 3(IT-42)の不所有ロック拒否は Indexer の IT にもない」に修正(4.3 と 6 章の 2 か所)
  3. **Suggestion**: 「プラン」が恒久文書に定義なしで残っていた。→ 5 章 2 の初出で「当初のシナリオ案(`agent_tasks/20261116_create_it_for_crawler/0002-work-plan.md`。以下「当初案」)」と定義し、「当初案」に統一。「作業記録に実行の記載がなく」は「実行の経緯を示す記録がなく」に
- 対応しない: `indexer-integration.md` の既存記述に残る内部用語(既存の履歴記録の書式を踏襲した範囲。対応不要)

## メインエージェントによる修正後の確認

- `jobs.json` に `schedule_cron` は 0 件、`test_01_startup.py` は `loreley-sources` の keyword として `schedule_cron` をアサートしている(grep)。
- `lock_not_owned` を含む Indexer の IT は `test_10_registration.py`(IT-15)と `test_40_source_deletion.py`(IT-41)のみ(grep)。
- `crawler-integration.md`・`tests/integration/crawler/README.md` に、R1・R2・R3・実装担当・メイン・code-reviewer・code-implementer・document-writer は残っていない(grep)。
- 修正は事実誤りの訂正と語の置換に限られ、レビュアーが他の項目を確認済みのため、2 回目の再レビューは行わなかった(修正点は上記 grep で確認)。

## 未対応事項

- 結果記録 3 章の実施時点のコミット SHA は、コミット後に追記が必要(結果記録の 6 章に負債として記載済み)
- `deploy/compose/README.md` の「約 855MiB は OpenSearch 2.19.7 での測定」の付記は、R3 が `indexer-integration.md` 3 章で確認済み(アイドル時メモリは 2.19.7 の記録にのみある)

## 次にやること

1. タスクレビュー(`task-reviewer`)→ 指摘対応
2. 最終報告
