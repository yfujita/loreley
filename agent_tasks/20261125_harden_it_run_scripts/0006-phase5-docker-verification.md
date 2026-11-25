# 0006 Phase 5: Docker を使う検証と全件実行

日付: 2026-11-26 / 実施: メインエージェント(`caffeinate -i`、バックグラウンド実行。検証スクリプトと出力はスクラッチパッドの `p5/`)
対象コード: 0005 の修正後(`--keep` の案内文言を直した版)。コード差分の基準は `96a9b52`。コミットはしていない。
実行前の状態: `loreley-it` のコンテナ・ボリューム・`data/`・ロックなし。他プロジェクトのコンテナは `opensearch-opensearch-1`(Exited (143) 2 weeks ago)のみ。

## 結果の一覧(すべて期待どおり)

| # | 内容 | 結果 |
| --- | --- | --- |
| 5-1 | Crawler: `compose down` を失敗(偽の docker)+ `LORELEY_IT_{OPENSEARCH,INDEXER,CRAWLER,API}_URL=http://127.0.0.1:9999` + `-k test_01_startup` | `4 passed, 10 deselected`、終了コード **11**。「後始末に失敗しました」「コンテナが残っている可能性があるため、…/crawler/data は削除しませんでした」「テストは成功しましたが…終了コード 11」を表示。終了後: コンテナ 4・ボリューム 1・`data/` が**残り**、ロックは**解除済み**。URL を 9999 にしても成功(スクリプトが固定したため) |
| 5-2 (i) | Indexer: `compose down` を失敗 + URL 上書き + `-k test_01` | `4 passed, 36 deselected`、終了コード **11**。スタック(コンテナ 3・ボリューム 1)が残り、ロックは解除済み。URL の上書きは効かなかった |
| 5-2 (ii) | そのまま Indexer を実行 | 終了コード 1、「前回の loreley-it スタックのコンテナが残っています」(3 件を表示)。コンテナ ID 不変 |
| 5-2 (iii) | 本物の `down`(`-v` なし)の後に Indexer を実行 | 終了コード 1、「loreley-it のデータボリュームが残っています」。ボリューム不変(残っている) |
| 5-2 (iv) | `down -v --remove-orphans` で片付け | コンテナ・ボリュームなし |
| 5-3 | Crawler `--keep -k test_01_startup` | 終了コード 0。ロック**なし**、スタック(4 コンテナ・1 ボリューム)と `data/` が**残った**。片付ける前の再実行は「コンテナが残っています」で終了コード 1(中止)。表示された後始末コマンドをそのまま実行して、コンテナ・ボリューム・`data/` がすべて消えた |
| 5-3' | Indexer `--keep -k test_01` | 終了コード 0。ロックなし、スタック(3 コンテナ・1 ボリューム)が残り、表示された後始末コマンドで片付いた |
| 5-4 | TERM: Indexer の起動待機中(3 コンテナができた後)に、ロックの `owner` の PID へ送信 | 終了コード **143**。後始末(`down -v`)が実行され、コンテナ・ボリューム・ロックなし。(`caffeinate -i` 経由で起動したが、`owner` の PID は `caffeinate` の PID と同一だった) |
| 5-5 | 同時実行: 1 本目に Crawler の全件。「スタックの準備ができました」の後、2 本目として Indexer・Crawler・api を順に起動 | 3 本とも終了コード **1**(保持者 `script=run-crawler-integration-test` と PID を表示)。2 本目の前後で、コンテナ ID・ボリューム・各コンテナの `StartedAt` が**不変**。`docker events` は 5 行で、すべてヘルスチェックの `exec_*`(destroy・die・kill・stop・remove なし)。1 本目は終了コード 0 |
| 5-5 / 5-6 Crawler | 全件(5-5 の 1 本目) | **14 passed in 36.99s**、終了コード 0。ログ: `tests/integration/crawler/results/pytest-20261126-041916.log` |
| 5-6 Indexer | 全件 | **40 passed in 17.19s**、終了コード 0、93 秒。ログ: `tests/integration/indexer/results/pytest-20261126-042111.log` |
| 5-6 api | 全件 | **23 passed in 423.90s (0:07:03)**、終了コード 0、512 秒。ログ: `tests/integration/api/results/pytest-20261126-042255.log` |

- 3 本の全件実行のログに、`skipped`・`deselected`・`xfailed`・`warnings` の行は無い(0005 の 4 章の判定条件を満たす)。api の障害系(AIT-90〜92)も skip されずに通った(`LORELEY_IT_ALLOW_COMPOSE_CONTROL=1` が api のスクリプトから渡っている)
- 各実行の前後で、`loreley-it` のコンテナ・ボリューム・`data/`・ロックが残っていないことを確認した。他プロジェクトのコンテナ(`opensearch-opensearch-1`)とボリューム(`opensearch-data`、`opensearch_opensearch-data`)は一貫して変化なし
- 0005 の 5 章の事故で 1 度、Crawler の全件が先に走っている(`pytest-20261126-040531.log`、14 passed in 37.90s)。上の記録とは別の、追加の成功実績

## 静的検査

- `bash -n` と `/bin/bash`(3.2.57)の `bash -n`: 4 ファイル(`scripts/lib/it-common.sh`、`scripts/run-{api,crawler,indexer}-integration-test.sh`)すべて OK
- shellcheck: **未実施**(ホストに無い)

## 完了条件(0001)の照合

| 完了条件 | 状況 |
| --- | --- |
| 1. 3 本で URL 固定・事前確認の失敗処理・後始末失敗の終了コードの方針が同じ | 達成(0004 の Phase 3、0005 の 3 章、本記録の 5-1・5-2) |
| 2. 同時実行の拒否(後から起動した側が何も消さずに中止) | 達成(5-5。同じ IT・別の IT の両方、3 本とも。ID・ボリューム・`StartedAt` 不変、events に破壊的操作なし) |
| 3. 残ったロックの扱い、INT・TERM・`--keep` 後にロックが残らない、`--help`・引数エラーでロックを作らない | 達成(0004 の `kill -9`・INT・TERM・`--help`、0005 の 3-H、本記録の 5-3・5-4)。README への記載は Phase 6 |
| 4. 14/40/23 件が成功し、実行後に残骸なし | 達成(上の表) |
| 5. shellcheck、使えなければ未実施と明記 | `bash -n` のみ実施。shellcheck は未実施 |
| 6. README・結果文書の更新 | Phase 6〜7 で実施 |

## 未対応事項・次にやること

- Phase 6: README 3 つ・結果文書 3 つの更新(`document-writer`)。README に書くこと: 終了コード 11(ロック解除の失敗を含む)、接続先 URL の固定(Crawler・Indexer)、事前確認の中止条件(Indexer は追加分)、同時実行をロックで拒否すること、ロックの置き場所(`${TMPDIR:-/tmp}/loreley-it.lock`)と手動解除の手順、`--keep` でもロックは解除されること、`TMPDIR` が異なる環境とは排他されないこと、PID 不一致の手動解除を誤ると警告のみで終わること
- Phase 7: `document-reviewer`。Phase 8: `task-reviewer`
