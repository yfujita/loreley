# 0009 フェーズ5: 実行スクリプト

日付: 2026-11-12
実装: code-implementer / 確認・記録: メインエージェント

## 実施内容

0002 のフェーズ 5 に従い、`scripts/run-indexer-integration-test.sh`(305 行、実行権限つき、日本語コメント、`bash -n` OK)を作成した。`tests/integration` の既存ファイルは変更していない(`STACK_HINT` は既にこのスクリプト名を参照)。

## 設計・判断の要点

- **起動と待機**: `up -d --build` のみ(`--wait` は使わない。0006 の発見)。その後 3 秒間隔で、opensearch・indexer が healthy、opensearch-init が Exited(0) になるまで自前でポーリングする。コンテナ ID は `compose ps -aq <service>`、判定は `docker inspect` の State.Status / ExitCode / Health.Status。早期失敗: init が非 0 終了、コンテナが exited / dead / restarting、unhealthy。上限は既定 300 秒(環境変数 `LORELEY_IT_WAIT_TIMEOUT_SECS`)。
- **終了コード**: pytest のコードをそのまま返す(`set +e` と `PIPESTATUS[0]` で `tee` 越しに取得。`-k` が 0 件一致で 5)。起動失敗 10、事前確認・引数エラー 1、INT 130、TERM 143。
- **後始末**: `trap cleanup EXIT` と INT/TERM の trap(`up` の直前に登録)。非 0 のとき `ps -a` と各サービスのログ末尾 100 行を出してから `down -v --remove-orphans`。`--keep` で残し、後始末コマンドを表示。
- **ポート確認**: bash の `/dev/tcp/127.0.0.1/<port>`(macOS・Linux 双方、`lsof`/`nc` 非依存)。
- **uv の差し替え**: 環境変数 `LORELEY_IT_PYTEST_CMD` で pytest 起動コマンド全体を置換できる(指定時は uv の事前確認を省略)。既定は `uv run --project tests/integration pytest tests/integration -v`。uv が入っていない環境で用意済みの venv を使うためだけの逃げ道。
- プランにない追加: 事前確認に `docker info`(デーモン接続)を追加(原因表示のため)。bash 3.2(macOS 標準)で動く書き方。ビルド済みイメージ・取得済みイメージは `down` で消さない。

## 検証結果(実装担当が実施)

| 項目 | 結果 |
| --- | --- |
| `bash -n` / `sh -n` | エラーなし。shellcheck は未導入のため**未実施** |
| 成功経路(`/tmp` から呼出し、クリーン状態) | 36 passed(22.93 秒)、終了コード 0、全体 2 分 11 秒(ビルドはキャッシュ済み)。終了後 `ps -a` 空、ボリューム・ネットワークも残らず。出力は `tests/integration/results/pytest-*.log` に保存 |
| 失敗経路 (a) テスト失敗(`-k IT-NOSUCH-999`) | pytest が 5 で、スクリプトも 5。`ps -a` とログ末尾を出力し、`down -v` で後始末(1 分 36 秒) |
| 失敗経路 (b1) 起動失敗(`OPENSEARCH_VERSION=0.0.0-nonexistent`) | イメージ取得失敗で 6 秒、終了コード 10、診断情報を出して `down` |
| 失敗経路 (b2) 待機の上限超過(`LORELEY_IT_WAIT_TIMEOUT_SECS=1`) | indexer が starting のまま上限超過で終了コード 10、`ps -a`・ログを出して後始末(1 分 49 秒) |
| ポート使用中(9200 を一時的に塞ぐ) | 原因と対処を出して終了コード 1(スタックには触れない)。解放を確認 |
| uv なし(`LORELEY_IT_PYTEST_CMD` 未指定) | uv が無いと案内して終了コード 1 |
| `--keep` | スタックが残り healthz 200。残したスタックへ手動 pytest(`-k "startup or document_id"`)で 9 passed。表示された `down -v` で撤去 |
| シグナル(`up` の最中に INT / TERM) | それぞれ 130 / 143、どちらも `down -v` まで実行 |
| 最終 | 全検証後 `loreley-it` のコンテナ・ボリューム・ネットワーク残りなし、9200・8000 の LISTEN なし。`opensearch-opensearch-1`(無関係)には触れていない(メインエージェントも `docker ps -a` と `docker volume ls` で確認) |

## 未確認・留意事項

- **uv 経由の既定の起動は未確認**(ホストに uv なし)。uv 導入後、フェーズ 6 でスクリプトを既定のまま通す。
- init が非 0 で終了する早期失敗の経路と、unhealthy / restarting の判定は、実機で再現できなかった(`up` 自体が先に失敗するため)。R2 のコードレビューで確認する。
- `-k IT-30` のように ID で絞ると 0 件になる(テスト関数名に IT-nn が含まれず、docstring のみ)。ファイル名やキーワード(`-k deletion`、`tests/integration/test_30_deletion.py`)で絞る旨をフェーズ 7 の README に書く。IT-nn で絞れるようにするマーカーの付与は要件外なので実装しない。
- 終了コード 1 が事前確認の失敗と pytest のテスト失敗で重なる(標準エラーで区別できる)。
- 実行のたびに `tests/integration/results/` にログが増える(gitignore 済み)。

## 次にやること

- R2: `code-reviewer`(スクリプトの `trap`・後始末・終了コード、早期失敗の判定、依存固定)と `test-reviewer`(シナリオの網羅、偽陽性、再現性、コメント)を並列で実施する。
- フェーズ 6(2 回連続の成功確認と結果記録)。uv が入っていなければ、ユーザーに代替を確認する。
