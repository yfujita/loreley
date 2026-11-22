# 0004 フェーズ 1・2: スキーマと compose

日付: 2026-11-16
実装: code-implementer(静的検証まで)/ 実機検証: メインエージェント

## 実施した作業の概要

- フェーズ 1: `loreley-sources` の新設、`loreley-jobs` のマッピング拡張、`init-indices.sh` の更新。
- フェーズ 2: `crawler` サービスの追加、`opensearch-init`・`indexer` への変数追加、`.env.example`、テスト用上書き `tests/integration/crawler/compose.test.yaml`、`run-indexer-integration-test.sh` の起動サービス明示。

## 変更したファイル

- 新規: `infra/opensearch/schema/sources.json`、`tests/integration/crawler/compose.test.yaml`
- 変更: `infra/opensearch/schema/jobs.json`、`infra/opensearch/init-indices.sh`、`deploy/compose/compose.yaml`、`deploy/compose/.env.example`、`scripts/run-indexer-integration-test.sh`(`up` に `opensearch opensearch-init indexer` を明示した 1 点とコメント 3 行のみ)
- `apps/crawler`・`apps/indexer` のコードは変更していない。

## 実装担当の静的検証(Docker の起動を伴わない)

- 3 つの JSON が `json.tool` を通る。`sh -n`・`bash -n` が通る。
- `docker compose ... config` が 3 つの組み合わせ(ベースのみ / Crawler 用上書き / Indexer 用上書き)で成功。公開ポートは 3 つとも `127.0.0.1`、Crawler の mount は `read_only: true`、`JOBS_INDEX_NAME` は 3 者で一致、`SOURCES_INDEX_NAME` は 2 者で一致。Indexer 用上書きの値(`MAX_RAW_BYTES=65536` など)が優先される。
- Crawler の `load_config()` に `config` 出力の環境変数を渡し、整合性検査が通る(警告なし)。`MAX_RAW_BYTES=70000` では検査が失敗することも確認(検査が効いている)。

### 突き合わせ(実装担当の報告)

- `sources/records.py` の `build_body()` の 9 キー(`source_id`、`connector_type`、`connector_config`、`ttl`、`ratio_threshold`、`min_delete_count`、`schedule_cron`、`status`、`updated_at`)が `sources.json` に漏れなくあり、余分なキーはない。
- Crawler が `loreley-jobs`・`loreley-sources` の絞り込み・並べ替えに使う項目(`record_type`、`source_id`、`status`、`owner`、`job_type`、`document_id`、`queued_at`、`job_id`、`schedule_cron`)は全てマッピング済み。ロック文書の項目も全て定義済み。

## メインエージェントによる実機検証(フェーズ 2 の手動起動)

手順: `CRAWLER_DOCUMENTS_DIR=$PWD/tests/integration/crawler/data` で、`compose.yaml` + `tests/integration/crawler/compose.test.yaml` を `up -d --build`(`--wait` なし)。

| 確認項目 | 結果 |
| --- | --- |
| Crawler イメージのビルド・起動 | 成功。`startup recovery finished: failed_jobs=0 deleted_locks=0 kept_locks=0`、`owner=crawler-1` |
| healthy | `crawler`・`indexer`・`opensearch` が healthy、`opensearch-init` が Exited(0)。`GET /healthz` は 200 |
| healthcheck の `test` の継承 | **保持されている**(`docker inspect` で、イメージの `test` に `Interval=3s`・`StartPeriod=180s` が重なっている)。compose への明示は不要 |
| 起動ログの警告 | なし(「Indexer の上限が未設定」を含む警告 0 件) |
| 公開ポート | 9200・8000・8001 すべて `127.0.0.1` のみ |
| マッピング | `loreley-sources` は `dynamic: strict`(9 項目)、`loreley-jobs` は `dynamic: false`(既存 4 項目 + 拡張項目) |
| init の冪等性 | 再実行で全て `skip`(alias・3 索引) |
| `POST /sources` | 201。strict マッピングに受け入れられ、`loreley-sources` に保存された |
| 実クロール(スモーク) | `POST .../crawl-jobs` が 202 → 3 秒で `succeeded`(`enumerated_count=2`、`created_count=2`)。検索インデックスに 2 件 |
| 回帰: Indexer IT | `scripts/run-indexer-integration-test.sh` で **40 passed(23.41s)、終了コード 0**。`crawler` は起動せず(`ps -a` に出ない)、`deploy/compose/documents` も作られていない |

後始末: `down -v --remove-orphans` し、`tests/integration/crawler/data` を削除した。

## 発見事項・判断

1. **`connector_type` の値は `file_system`**(`filesystem` は 400 `unsupported`)。`apps/crawler/src/loreley_crawler/connectors/registry.py:19` の定数。テストの `connector_type` はこれを使う。
2. **別プロジェクト(Fess)のアプリがテスト用 OpenSearch に書き込んでいる**: 起動した OpenSearch に、`fess_config.coordinator`(`instanceId=127.0.0.1:93982`、type=heartbeat)の索引と文書があった。ホスト上の Fess が `127.0.0.1:9200` に接続し続けており、フェーズ 0 でユーザーが `fess-opensearch` を停止(または削除)したため、同じポートで起動した Loreley のテスト用 OpenSearch へ書き込んでいる。
   - 影響: `loreley-*` 索引には影響しない(Indexer IT 40 件・Crawler のスモークとも成功)。ただし Fess は Loreley のテスト環境に索引を作る。テスト終了時の `down -v` でそれらは消える(Fess 側のデータとしては意味を持たない)。
   - 私は Fess のプロセスにも `fess-opensearch` にも触れていない。ユーザーへの最終報告に含める。ポート固定のままだと、Fess 稼働中は同様の混入が起こり得る。
3. 実装担当が `.env.example` の `CRAWLER_DOCUMENTS_DIR=./documents` について、`deploy/compose/documents` を `.gitignore` に入れるかを確認事項として挙げた。要件外のため追加していない(フェーズ 6 の README に「テストではスクリプトが `tests/integration/crawler/data` を渡す」と書く)。
4. `x-max-raw-bytes` のアンカー定義が `config` 出力に残るが、害はない。

## 未対応事項・次にやること

1. R1(`code-reviewer`。公開範囲の確認は省略不可)を実施する
2. フェーズ 3(テスト資材)以降へ進む。`connector_type` は `file_system`
3. 最終報告でユーザーに Fess の件を伝える
