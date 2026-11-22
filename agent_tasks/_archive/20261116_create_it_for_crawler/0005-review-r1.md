# 0005 レビュー R1(フェーズ 1・2)

日付: 2026-11-16
レビュアー: code-reviewer(実装担当 code-implementer とは別)
対象: `infra/opensearch/**`、`deploy/compose/compose.yaml`・`.env.example`、`tests/integration/crawler/compose.test.yaml`、`scripts/run-indexer-integration-test.sh`(比較基準: 基準コミット `6970478`、未コミット差分)

## 結果

**Critical / Important なし。次工程に進めてよい**(Suggestion 3 件)。

### 公開範囲の確認(省略不可)

- 結論: Crawler API は `127.0.0.1` のみに publish される。環境変数でも変えられない。
  - `crawler.ports` は `"127.0.0.1:${CRAWLER_HOST_PORT:-8001}:8001"` の 1 行のみ(`host_ip` は固定)。`compose.test.yaml` に `ports` はない。
  - `docker compose config` で、3 つの組み合わせすべてで 3 サービスの `host_ip` が 127.0.0.1。`CRAWLER_HOST_PORT=0.0.0.0:8001` や `8001:8001` は config がエラーで失敗(fail closed)。
  - `:ro` マウントは 1 本のみ(`read_only: true`)。未指定時の既定は `deploy/compose/documents`(空ディレクトリ)で、ホストの広い範囲が mount されることはない。

### 指摘なしの観点

上限 6 項目・索引名の同値定義(Indexer の既定値・Crawler の整合性検査と整合)、`depends_on`・healthcheck・`stop_grace_period`、`init-indices.sh` の冪等性、スキーマとコードの突き合わせ(`sources.json` は `build_body()` の 9 キーと一致、`jobs.json` の既存 4 項目の型は不変)、Indexer 用スクリプトの変更が最小、コメントの正確さ、スコープ。

## Suggestion と対応

| ID | 内容 | 対応 |
| --- | --- | --- |
| S1 | `CRAWLER_DOCUMENTS_DIR` 未指定だと `deploy/compose/documents` が自動作成され、gitignore されない。パスの打ち間違いでも失敗せず 0 件列挙になる | **フェーズ 6 の `deploy/compose/README.md` に注意書きとして書く**。`.gitignore` への追加や `create_host_path: false` への変更は要件外のため行わない(`.env.example` の既定のまま) |
| S2 | FS Connector の `root` はコンテナ内の任意の絶対パスを受け付ける。`:ro` が守るのはホスト側のファイルで、`/data/documents` 配下に制限されない(コードからの推測、未実行) | **フェーズ 6 の `deploy/compose/README.md` か結果記録の発見事項に一文書く**。本タスクでコードは変えない |
| S3 | 設計書 arch 10 章の記述(Crawler はホストに公開しない / 既定の compose は Indexer に上限の変数を渡していない)と食い違う | **フェーズ 6 の結果記録「発見事項」に載せる**(承認済みの前提どおり。設計書は改版しない) |

## 再レビュー

Critical / Important がないため再レビューは不要。S1〜S3 の反映はフェーズ 6 の文書(R3 でレビュー)で確認する。

## 未対応事項・次にやること

1. フェーズ 3(テスト資材)・フェーズ 4(テスト本体の実装・実行)を `code-implementer` に依頼する
2. フェーズ 6 の文書に S1〜S3 を反映する(0002 の 5 章フェーズ 6 の入力として扱う)
