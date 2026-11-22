# 0013 タスクレビューと完了

日付: 2026-11-16
レビュアー: task-reviewer(実装・文書の担当とは別)

## タスクレビューの結果

**Critical / Important なし。完了を報告してよい**(Suggestion 7 件、Nitpick 2 件)。

- 要件(スキーマ・Compose・テスト・テスト実施)と完了条件(Integration Test が成功する)は、実ログと文書で裏づけられた。`tests/integration/crawler/results/` の 5 ログはすべて末尾が 13 passed。最終の 2 回(44.54s・43.88s)は、最終コードの変更(16:46:53)より後の実行で、以降の変更は文書のみ。実行後の残骸なし。
- `apps/crawler` のコードは未変更(`apps/crawler/README.md` のみ)。作業記録は 0000〜0012 が連番で、STATUS.md は最新の作業記録と一致。
- 完了チェックリスト: 全項目 ○(承認の回答そのものは audit から独立には確認できないが、0003 に記録あり。レビュアーは「参考情報」とした)。
- 実装とレビューは別エージェントで、サブエージェントが `agent_tasks` 配下を書いた形跡はない(mtime による確認)。

## 指摘と対応

| 指摘 | 対応 |
| --- | --- |
| 失敗経路の実機確認が R2 反映前の版のまま | **対応**: 最終版のスクリプトで再実行した。`LORELEY_IT_WAIT_TIMEOUT_SECS=1` → **終了コード 10**、ポート 8001 を一時的に塞ぐ → **終了コード 1**(`lsof` の結果と「利用者自身の判断で止めてから再実行する」メッセージを確認、スタックは起動せず)。どちらも `ps -a` 空・`data/` なし。塞いだ `http.server` は自分で停止し、8001 は空き。結果記録 4.4 を更新した。シグナル・`--keep`・`check_no_leftover_stack` 失敗経路・コンテナ占有時の `describe_port_owner`・`compose down` 失敗時の分岐は引き続き未確認 |
| 4.2 の「初回に 1 件失敗」の時系列が不明、64 行の「失敗・不安定なテストはなかった」の対象が不明 | **対応**: 結果記録 4.2 を「テストの誤りを直す前に 1 件失敗した実行があった(ログは保存していない。実施者の報告による)」と書き分け、「この最終版の 2 回では」と対象を限定した(既存の作業記録 0006 は書き換えていない) |
| `pytest-20261116-164835.log`(48.11s)の経緯が作業記録にない | **対応しない**(結果記録に「経緯は未確認」と明記済み。実害なし) |
| 最終報告に含める事項(R1 S2 の `root` 制限なし、プランからの乖離、`apps/crawler/README.md` の 6・7 章の更新、`fess-opensearch` はコンテナが存在しない可能性) | **最終報告に含める**。`docker ps -a` に `fess-opensearch` は現れず、停止ではなく削除された可能性が高い(私は操作していない) |
| 「ユーザー判断待ち: なし」と未解決事項の判断項目の関係 | **対応**: STATUS.md の「ユーザー判断待ち」に判断が必要な項目を移した |
| 承認の独立確認(audit に `AskUserQuestion` が残らない)、サブエージェントの編集が audit で確認できない | 対応不要(参考情報) |
| 0002 冒頭が「承認待ち」のまま | 対応不要(既存の作業記録は書き換えない運用。承認は 0003 に記録) |

## 完了時点の状態

- 完了条件: クリーンな状態から一括スクリプトで 2 回連続 13 passed・終了コード 0(最終コード)。Indexer IT の回帰 40 passed。README の手動手順も実行確認済み(13 passed)。最終版のスクリプトの失敗経路 2 つも確認済み。
- 変更は未コミット(コミットの指示なし)。結果記録 3 章の実施時点のコミット SHA は、コミット後に追記する。
- 成果物: Compose(`deploy/compose/compose.yaml` に `crawler`、`.env.example`、`tests/integration/crawler/compose.test.yaml`)、スキーマ(`infra/opensearch/schema/sources.json` 新設、`jobs.json` 拡張、`init-indices.sh`)、テスト(`tests/integration/crawler/`、13 件)、実行スクリプト(`scripts/run-crawler-integration-test.sh`)、結果記録・手順書。修正した Crawler はなし。

## 最終報告に含める事項(ユーザー判断・認知)

1. `fess-opensearch`: ポート 9200 を使っていたため、ユーザーに確認して停止してもらった。その後の確認で、コンテナ自体が存在しない(`docker ps -a` に出ない)。必要なら再作成が要る可能性がある
2. Fess アプリが(索引名からの推定)テスト用 OpenSearch に heartbeat を書き込んだ。`loreley-*` には無影響。テストはポート 9200 固定で、Fess 稼働中は混入し得る
3. arch 10 章との差(Crawler をループバックに publish、Indexer に上限 6 項目を明示的に渡す)と、`loreley-sources` の `dynamic: strict` の決定(arch 3.1 は「実装時に決める」)を、設計書に反映するか
4. FileSystem Connector の `root` はコンテナ内の任意の絶対パスを受け付ける(`:ro` が守るのはホスト側のファイル。Crawler API は認証なしでループバックのみ公開)
5. 当初案からの乖離: CIT-10 は `config_invalid`(当初案の `invalid_request` は誤り)、追加テスト CIT-23、`conftest.py` のメンテナンスフラグ残り検出、スクリプトの `--keep`・残骸検出、`apps/crawler/README.md` の 6・7 章も更新
6. 未実施・未確認: 権限エラーの `skip` 記録・`partially_succeeded` ほか(結果記録 6 章)、スクリプトのシグナル・`--keep` ほか
7. 変更は未コミット

## 未対応事項

- 結果記録 3 章のコミット SHA の追記(コミット後)
- スクリプトの重複(Indexer 用・Crawler 用)は 3 つ目のモジュールのときに共通化する負債
- CI への組み込みは対象外
