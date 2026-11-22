# 0014 フェーズ6の完了: uv 経由の既定起動と 2 回連続成功

日付: 2026-11-13(前回までは 2026-11-12)
実施者: メインエージェント

## uv の導入の経緯

- `brew install uv`(ユーザー承認済み)は、Rust・LLVM をソースからビルドして約 8 時間かかり、**uv が入らないまま失敗して終了した**(llvm 23.1.5_1 と rust 1.99.1 だけが入った。失敗の詳細は、出力を `tail -5` で切っていたため残っていない。`uv` のビルドログも無かった)。当初ユーザーは「brew待ってみよう」と回答していた。
- 失敗の後、再度ユーザーに方針を確認したところ、**ユーザー自身が uv を導入した**(`~/.local/bin/uv`、uv 0.13.8。Dockerfile の固定版 0.13.7 とは異なるが、ホストでの結合テストの実行用であり Indexer のビルドには影響しない)。メインエージェントは brew 以外の方法で uv を入れていない。
- 待機用に置いたバックグラウンドコマンド(`pgrep -f 'brew.rb install uv'` を条件にしたループ)は、自分自身のコマンド文字列に一致して終わらない作りだったので、メインエージェントが停止した。

## 実施内容

1. `tests/integration` で `uv lock` を実行し、`tests/integration/uv.lock` を生成した(15 パッケージ。httpx 0.28.1、pytest 9.2.0、ruff 0.17.5。CPython 3.13.4)。`.gitignore` の対象外(コミットする)。
2. スクリプト `scripts/run-indexer-integration-test.sh` を、**既定の起動(uv 経由。`LORELEY_IT_PYTEST_CMD` 未指定)で 2 回連続で実行**した。
3. 結果記録(`docs/v0.x/test-results/indexer-integration.md`)の状態・3 章・4.2・4.4・6 章と、`tests/integration/README.md` の冒頭・前提・ファイル構成の uv の記述を更新した。

## 結果

| 回 | 結果 | 所要時間 | 備考 |
| --- | --- | --- | --- |
| 最初の試行 | 終了コード 1、3 秒 | — | **Docker デーモンが停止していた**(Docker Desktop のプロセスはあるが `docker info` が panic。夜間のスリープ等と思われる)。スクリプトの事前確認が「Docker デーモンに接続できません。Docker Desktop などを起動してから再実行してください。」と案内して中止した。スタックは作られず残骸なし。メインエージェントは Docker Desktop を操作せず、デーモンが応答するまで待った(50 秒後に復帰) |
| ④ | **40 passed in 13.40s**、終了コード 0 | スクリプト全体 70 秒 | ログ `tests/integration/results/pytest-20261113-034228.log`。pytest の rootdir は `tests/integration`、configfile は `pyproject.toml`、Python 3.13.4、pytest 9.2.0。`Installed 13 packages`(`.venv` は `tests/integration/.venv`、gitignore 済み) |
| ⑤ | **40 passed in 13.13s**、終了コード 0 | スクリプト全体 61 秒 | ログ `pytest-20261113-034340.log` |

- どちらも終了後に `loreley-it` のコンテナ・ボリューム・ネットワークの残りはなかった。無関係な既存コンテナ `opensearch-opensearch-1`(3 日前から Exited)には触れていない。
- ④⑤ のテスト・スクリプト・compose は、前日の ③(33.64s、一時 venv)と同じ内容(その間の変更は `uv.lock` の追加と文書のみ)。④⑤ の所要時間が ③ より短いのは、ビルドと OpenSearch のイメージのキャッシュ、Docker の状態によると思われる(原因は調べていない)。
- これにより、**0000 の完了条件「composeを利用したテストが成功」を、既定の起動(uv 経由)で 2 回連続して満たした**。

## 確認できたこと・できていないこと

- 確認済み: uv 経由の既定起動、`uv.lock` による固定、pytest の rootdir・設定ファイルの読み込み、Docker デーモン停止時の事前確認の案内。
- 未確認(結果記録 5・6 章のとおり): Linux ホスト・他の OS・他の compose / OpenSearch のバージョン、`uv run` がロックを自動生成するか(事前に `uv lock` を実行したため)、init が非 0 で終了する経路などの実機での再現、shellcheck、U-31 の未実施項目。

## 未対応事項・次にやること

- **タスクレビュー(task-reviewer)** を実施し、指摘に対応する。その後、完了チェックリストを確認して最終報告する。
- 最終報告でユーザーに提示する事項: (1) `loreley-deletions` 索引喪失時の 503(設計書 K66 との差の可能性)、(2) U-8(url・path の `doc_values`)、(3) `up --wait` が使えず自前ポーリングにした(確定要件 0001 Q3 からの変更)、(4) 結合テストで未実施の項目(`skipped_by_ratio`、`validation_failed`、409 競合、`_reindex`、要約など)、(5) 変更が未コミットであること(コミットは指示がないため行っていない)。
