# 0007 フェーズ 5: 実行スクリプト

日付: 2026-11-16
実装: code-implementer / 検証: メインエージェントが再実行

## 実施した作業の概要

`scripts/run-crawler-integration-test.sh` を新設した(`run-indexer-integration-test.sh` を写して調整。実行権限 755)。起動 → 待機 → pytest → 後始末を 1 本で行う。

## 変更したファイル

- 新規: `scripts/run-crawler-integration-test.sh`
- 他は変更なし。`scripts/run-indexer-integration-test.sh` の差分はフェーズ 2 の `up` のサービス明示 1 点のみ(今回は触っていない)。`.gitignore` は既存の `tests/integration/*/results/`・`tests/integration/*/data/` で足りる(`git check-ignore` で確認)。

## Indexer 用との差分(判断理由)

- 固定値: ポートに 8001 を追加、待機対象に `crawler:healthy` を追加、`up` は `opensearch opensearch-init indexer crawler` を明示、compose ファイルは `tests/integration/crawler/compose.test.yaml`、pytest は crawler 用。
- `LORELEY_IT_PYTEST_CMD` の逃げ道は持ち込まず、uv の事前確認は無条件(uv は導入済みのため)。
- `CRAWLER_DOCUMENTS_DIR` に `tests/integration/crawler/data` の絶対パスを export。起動前に `mkdir -p`、`cleanup` で `compose down` の後に `rm -rf "${documents_dir:?}"`(`:ro` の mount 元を使用中に消さないため)。
- 事前確認: ポート確認を `check_ports_are_free` に分け、占有していたら相手を表示する(止めない)。`loreley-it` の残骸検出 `check_no_leftover_stack`(ラベルで検出し、`down` コマンドを案内して終了コード 1)を追加。
- `--keep` は Indexer 用と同様に維持(プランにない小さな拡張。`--keep` のとき `data/` も残す)。
- それ以外(終了コード体系、`probe_service`、`trap`、`wait_for_stack`、`results/` のログ保存)は Indexer 用のまま。

## 検証結果

| 経路 | 実施者 | 結果 |
| --- | --- | --- |
| `bash -n` | 実装担当 | OK。`shellcheck` は未導入のため**未実施** |
| 成功経路 | 実装担当 | 13 passed(47.72s)、終了コード 0、`ps -a` 空、`data/` なし |
| 成功経路 | **メイン** | **13 passed(38.09s)、終了コード 0**、`ps -a` 空、`data/` なし |
| `LORELEY_IT_WAIT_TIMEOUT_SECS=1` | 実装担当 | 終了コード 10、`ps -a` とログ末尾を出力して `down`、後始末済み |
| `LORELEY_IT_WAIT_TIMEOUT_SECS=1` | **メイン** | **終了コード 10**、`ps -a` 空、`data/` なし |
| ポート占有(8001 を一時的に塞ぐ) | 実装担当 | 終了コード 1、占有者を lsof で表示、スタックは起動せず。塞いだ http.server は自分で停止し、8001 が空いたことを確認 |

## 未対応事項・不確実点

- `shellcheck` 未導入のため未実施。
- 残骸検出 `check_no_leftover_stack` の失敗経路と、コンテナがポートを占有している場合の `describe_port_owner`(docker ps 部分)は実機で動かしていない(成功経路で空振りしないことのみ確認)。R2 のレビュー対象にする。
- 同時実行はできない(プロジェクト名・ポートが同じ。スクリプト冒頭に記載済み)。

## 次にやること

1. R2(`code-reviewer` + `test-reviewer` を並列)
2. フェーズ 6(R2 の指摘対応後の最終コードで、クリーンな状態から一括スクリプトを 2 回連続、Indexer IT 回帰、文書)
