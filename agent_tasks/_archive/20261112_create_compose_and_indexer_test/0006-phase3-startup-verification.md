# 0006 フェーズ3: 起動確認

日付: 2026-11-12
実施者: メインエージェント(`-p loreley-it`、`deploy/compose/compose.yaml`)
環境: Docker 20.10.13(Docker Desktop、メモリ 3.843GiB・CPU 2)、compose v2.3.3、x86_64

## 結果の要約

起動、初期化(init)、Indexer の実 OpenSearch への接続は成功した。**`docker compose up --wait` は compose v2.3.3 では使えない**ことが分かり、プランから逸脱する(下記)。

## 確認結果

| # | 手順 | 結果 |
| --- | --- | --- |
| 1 | `up -d --build --wait` | 3 コンテナとも起動し、opensearch・indexer は healthy、opensearch-init は Exited(0) になった。**しかしコマンドが戻らなかった**(約 10 分でも終了せず、手動で中断)。下記参照 |
| 2 | `_cluster/health` | green、ノード 1、プライマリシャード 7、未割り当て 0 |
| 3 | インデックスとマッピング | `loreley-documents-000001`、`loreley-deletions`、`loreley-jobs` が green/open(shards 1、replicas 0)。エイリアス `loreley-documents → loreley-documents-000001`。`dynamic`: documents=`strict`、deletions=`strict`、jobs=`false` |
| 4 | `GET 127.0.0.1:8000/healthz` | 200 `{"status":"ok"}` |
| 5 | Indexer の起動ログ | `unfinished deletion results were failed after the restart: count=0` → `the indexer is ready` → `Uvicorn running on http://0.0.0.0:8000`。**Indexer が実 OpenSearch に接続し、起動時の整理(`loreley-deletions` の読み取り)まで完了した**(README 10 章で未確認だった点) |
| 6 | 再度 `up`(init の冪等性) | init ログは `skip: index already exists`、`skip: alias already exists` となり `done`(終了コード 0)。`--wait` なしの `up -d` は 3 秒で戻った |
| 7 | `stop indexer` | 1 秒で停止、終了コード 0、OOMKilled=false。ログに `Shutting down` → `Application shutdown complete.`(30 秒の猶予内) |
| 8 | `down -v --remove-orphans` | コンテナ・ボリューム・ネットワークとも `loreley-it` のものは残っていない |

補足(実測):
- OpenSearch: `2.19.7`(distribution opensearch、build_hash `6dd9a042`、JDK 21.0.12.1)、ヒープ最大 `536870912` B(512MiB)、`nofile` 65536、メモリ使用 約 855MiB(OpenSearch)・約 56MiB(Indexer)、CPU ほぼアイドル。
- イメージ: `loreley-it_indexer:latest` 189MB。ビルドは成功(ベースイメージ取得を含む)。
- init はスキーマを受理した(`strict_dynamic_mapping_exception` なし。ただし Indexer の書き込みでの受理は結合テストで確認する)。

## 発見事項: compose v2.3.3 の `up --wait` が戻らない

- 事象: `up -d --wait` は、全サービスが `Healthy` / `Exited(0)` になったログを出した後も、プロセスが終了しない。2 回再現した(1 回目は新規起動、2 回目は起動済みのスタックへの再実行。2 回目のログも `Healthy` / `Exited` で止まった)。
- 推定原因: 終了済みの one-shot サービス(`opensearch-init`)を `--wait` が待ち続ける。原因の特定まではしていない(compose の既知の不具合の可能性があるが、未確認)。
- 切り分け: `--wait` を付けない `up -d` は 3 秒で戻る(再現済み)。
- なお `perl -e 'alarm 90; exec ...'` で時間制限をかけると docker CLI だけが止まり、compose プラグインのプロセスが残る。この方法は使えない(手動で kill した)。
- 影響と対応:
  - 0001 Q3 の `up --wait` からの逸脱になる。0002 の想定(リスク表「`up --wait` が one-shot の init で失敗する場合は自前の待機に切り替え、理由を記録・報告」)に該当する。
  - フェーズ 5 の実行スクリプトは `up -d --build` のあとに、`docker compose ps` / `docker inspect` で opensearch・indexer の health と init の終了コード(0)を **自前でポーリングし、上限時間を持つ**形にする。`--wait-timeout` も v2.3.3 に無い。
  - `compose.yaml` ヘッダと `deploy/compose/README.md` の `up --wait` の記述を修正した。

## 環境の整備

- `uv` は未インストール。`brew install uv` を実行中だが、Homebrew が依存の `python@3.15` をソースからビルドしていて時間がかかっている(開始から約 20 分以上)。フェーズ 4 の実行環境に必要。完了しない場合は代替(`pip` で uv を入れる等)をユーザーに確認する。

## 未対応事項・次にやること

- レビュー R1(`code-reviewer`、省略不可): `infra/opensearch/**`、`deploy/compose/**`。観点は 0002 の 6 章のとおり。加えて「`--wait` を使わない理由と compose の記述の整合」「init の `curl` の接続エラー処理」。
- R1 の指摘対応後、フェーズ 4(結合テスト資材)へ。`uv` が使えることが前提。
- `apps/indexer` は変更していない(不具合なし)。
