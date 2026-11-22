# 0005 フェーズ2: compose の作成

日付: 2026-11-12
実装: code-implementer / OpenSearch バージョン調査: web-researcher / 確認・記録: メインエージェント

## 実施内容

0002 のフェーズ 2 に従い `deploy/compose/` を新規作成した。OpenSearch のバージョンは `web-researcher` で調査して決めた。

## 変更ファイル(すべて新規)

- `deploy/compose/compose.yaml`: サービス `opensearch`、`opensearch-init`、`indexer` と名前付きボリューム `opensearch-data`
- `deploy/compose/.env.example`: `OPENSEARCH_VERSION`、`OPENSEARCH_HEAP_SIZE`、`OPENSEARCH_HOST_PORT`、`INDEXER_HOST_PORT`、`INDEXER_LOG_LEVEL`(秘密値なし)
- `deploy/compose/README.md`: 雛形(フェーズ 7 で完成させる)

## 判断・設計上の理由

- **OpenSearch は `opensearchproject/opensearch:2.19.7` で固定**(`.env` の `OPENSEARCH_VERSION` で変更可)。
  - 2.19 系は maintenance 系列(4.0 GA まで)で、opensearch-py 3.2.0 の CI が検証対象とする系列(2.18.0 / 2.19.5 / 3.6.0)。
  - 調査では、Indexer が使う API(`delete_by_query`、`search_after`、painless update、`if_seq_no`、エイリアス経由の操作、`dynamic: strict`)に 2.x と 3.x の破壊的変更は見つからなかった。ただし 3.1〜3.8 のリリースノートは個別に読んでおらず、「ない」とは断定できない。
  - 代替は 3.9.0(opensearch-py の CI の 3.x は 3.6.0 で、3.9.0 は未検証)。
  - 設計書(indexer-architecture v0.10 U-31)は「実装時に使用する OpenSearch のバージョンで確認する」とし、版を指定していない。
  - ホストは linux/amd64 で `docker pull` 済み。イメージダイジェスト `sha256:3bfa1ec74d56928c2e018033d45c460ce2c0ea65a5cedd577de3102326c31b89`(実バージョン 2.19.7、build_hash `6dd9a042`)。
- ヒープは `.env` に `OPENSEARCH_HEAP_SIZE=512m` だけを変数にし、compose 側で `-Xms`/`-Xmx` に組み立てる(空白入りの値のパース差を避ける)。
- `ulimits` は `nofile` 65536 のみ。`memlock` は `bootstrap.memory_lock` を使わないので設定しない。
- healthcheck は `wait_for_status=yellow`(単一ノードでは green を待つと healthy にならないことがあるため)。
- `version:`・`name:` は書かない(古い compose 向け)。プロジェクト名は `-p` で指定する。
- 公開ポートは `127.0.0.1` のみ(9600 は publish しない)。Indexer は認証なし、OpenSearch はセキュリティ無効のため。

## 検証結果

- 実施した: `docker compose -f deploy/compose/compose.yaml config`(`.env` 無しで終了コード 0、`--env-file .env.example`、`-p loreley-it` も 0)。環境変数による上書き(ヒープ、ホストポート)が反映されることを確認。公開ポートは opensearch が `127.0.0.1:9200`、indexer が `127.0.0.1:8000` のみ。
- 実機の起動確認は 0006(フェーズ 3)。
- フェーズ 3 の結果を受け、`compose.yaml` ヘッダと `README.md` の `up --wait` の記述を、メインエージェントが修正した(0006 参照)。

## 未対応事項・次にやること

- README の「フェーズ 3 で確認後に追記」の残り(`vm.max_map_count`(Linux)、マッピング変更時の手順、トラブルシュートの実事象)はフェーズ 7 で完成させる。
- 次: レビュー R1(`code-reviewer`)。
