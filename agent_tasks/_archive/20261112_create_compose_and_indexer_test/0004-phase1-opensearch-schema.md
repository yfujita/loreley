# 0004 フェーズ1: OpenSearch スキーマ定義

日付: 2026-11-12
実装: code-implementer / 確認・記録: メインエージェント

## 実施内容

0002 のフェーズ 1 に従い、OpenSearch のスキーマ定義と init スクリプトを新規作成した。

## 変更ファイル(すべて新規)

- `infra/opensearch/schema/search-index.json`: search-index v0.10 の 4.1 の JSON と同一(`dynamic: strict`、shards 1、replicas 0)
- `infra/opensearch/schema/deletions.json`: 0002 の 4.2 のとおり(30 項目、`dynamic: strict`)
- `infra/opensearch/schema/jobs.json`: 0002 の 4.3 のとおり(`dynamic: false`、`owner`・`job_id`・`lease_expires_at`・`enabled`)
- `infra/opensearch/init-indices.sh`: POSIX sh、冪等、コメントは日本語

## 判断・設計上の理由

- **エイリアスは JSON ではなく init スクリプトで付与する**。search-index の JSON を設計書 4.1 と同一に保つため、また公式イメージに `jq` が無く、実体名・エイリアス名を環境変数で変えられるようにするため。エイリアス作成は `HEAD /_alias/{名前}` で存在確認し、存在するときだけスキップする(再インデックス後にエイリアスが `-000002` を指している状態で `-000001` を再付与して複数インデックスを指す事故を避ける)。PUT とエイリアス付与は原子的でないが、再実行で補完される。
- 環境変数と既定値: `OPENSEARCH_URL=http://opensearch:9200`、`SCHEMA_DIR=/schema`、`SEARCH_INDEX_NAME=loreley-documents-000001`、`SEARCH_INDEX_ALIAS=loreley-documents`、`DELETIONS_INDEX_NAME=loreley-deletions`、`JOBS_INDEX_NAME=loreley-jobs`。
- 各インデックスは HEAD で存在確認(200 存在、404 不在、他は失敗)、なければ PUT し `"acknowledged":true` を確認。400 `resource_already_exists_exception` は競合した実行によるものとして成功扱い。失敗時は HTTP ステータスと応答本文を標準エラーに出して非 0 終了(接続失敗・スキーマファイル欠如も非 0)。
- HEAD は `curl --head`(`-X HEAD` は本文待ちでハングし得るため)。

## 突き合わせ結果

| 対象 | 抽出方法 | 書き込み側のみ | マッピング側のみ |
| --- | --- | --- | --- |
| deletions.json 30 項目 | AST で `records.py` の `to_body()` 全キー(`DeletionRecord` 9、`DeletionResultRecord` 28、和集合 30) | なし | なし |
| search-index.json 19 項目 | `search_document.py` の `build_source` と、`processor.py` の要約書き戻し(`summary`・`summary_status`・`summary_model`) | なし | なし |

- 書かない項目(`fetched_at`、`metadata`、`acl`、`extractor_version`)は定義にもない。
- `jobs.json` の 4 項目は `jobs.py` が読む項目と一致。

## 検証結果

- 実施した: `python3 -m json.tool`(3 JSON すべて OK、メインエージェントも再確認)、`sh -n`(OK、メインエージェントも再確認)、`dash -n` OK、スタブ HTTP サーバー(`python3 http.server`、scratchpad 内、リポジトリ外)での動作確認(初回: 4 つ作成して終了コード 0、2 回目: 全 skip で 0、HTTP 500 で 1、スキーマ欠如で 1、接続不能で 1)。
- **未実施**: shellcheck(未インストール)、実 OpenSearch でのスキーマ受理と公式イメージ内の `curl`/`sh` での動作(フェーズ 3 で確認)。

## 未対応事項・次にやること

- フェーズ 2 で compose を作る。`opensearch-init` は `infra/opensearch` を読み取り専用で mount し、`SCHEMA_DIR` をその mount 位置に合わせて渡す(例: `/init` に mount して `SCHEMA_DIR=/init/schema`、entrypoint は `["/bin/sh", "/init/init-indices.sh"]`)。
- OpenSearch のバージョン調査(`web-researcher`)の結果待ち。`uv` のインストール(`brew install uv`)は実行中で、フェーズ 4 までに完了していればよい。
- Compose v2.3.3 のため `--wait-timeout` が使えない(0003 参照)。
- レビュー R1 はフェーズ 3 完了後に実施する。
