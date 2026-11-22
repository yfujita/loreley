# 0001 要件確認の結果

作成日: 2026-11-16
工程: 要件確認(requirements-clarifier を2回呼び出し、`STATUS: REQUIREMENTS_READY`)

## 実施した作業の概要

- 要件定義(0000)と、先行タスク `20261112_create_compose_and_indexer_test`、Crawler の README・設計書(arch v0.4)、既存の compose・スキーマ・Indexer 結合テスト資材を突き合わせ、不明点を洗い出した。
- ユーザーに Q1〜Q3 を確認し、すべて推奨案で回答を得た(下記)。
- 0000 は書き換えていない。

## ユーザーの回答(確定)

| 質問 | 回答 |
|---|---|
| Q1 テスト範囲 | 主要フロー + 件数照合 + ソース削除(推奨案) |
| Q2 compose の置き場 | `deploy/compose/compose.yaml` に `crawler` を追加(推奨案) |
| Q3 テスト文書 | ホスト作業ディレクトリを `:ro` バインドマウント(推奨案) |

## 確定した要件

### 目的・スコープ

- 実装済みの Crawler(`apps/crawler`、FileSystem Connector のみ)を compose で起動し、実 OpenSearch・実 Indexer(別コンテナ、HTTP 直接通信、mock にしない)に対する結合テストを作り、実行して成功させる。
- 0000 の対象範囲 `apps/cawler` は `apps/crawler` の誤記として扱う。
- 対象範囲は `apps/crawler`、`infra`、`deploy`、`tests` に加え、`scripts/`、`docs/v0.x/test-results/`、`apps/crawler/README.md` の 8・9 章(実績に合わせた最小限の更新)とする。
- 設計書の改版は本タスクでは行わない。

### テスト範囲(Q1)

1. Crawler が healthy になる
2. `POST /sources` で設定を登録する
3. `POST /sources/{id}/crawl-jobs` でクロールを起動する
4. FileSystem Connector が txt/md/html/pdf と対象外ファイルを含むディレクトリを列挙・取得する
5. 索引された文書と `loreley-jobs` のジョブ記録を OpenSearch で直接確認する
6. 実 Indexer との件数照合(`enumerated_count` = Indexer の `n_seen + e_missing`、`validation_failed` にならない、バッチ応答の `document_id` 一致)
7. 2回目のクロールで、消えたファイルが TTL 削除される
8. ソース削除ジョブ(`POST .../delete-jobs`、順 0〜6)が通る
9. スキップ(またはCrawler側の原本サイズ超過)を1件確認する
10. 実行中のロックの実体が `loreley-jobs` に存在し、終了後に解放される
11. メンテナンスフラグが立っていると、クロール起動が 409 `maintenance_enabled` になる

対象外: 10,001件超の全件走査、実 NFS/SMB、Web Connector、並行時の `create` の原子性、運用系(起動時回復、`docker stop` の所要時間、ロック解放 API、取り消し API)。

### compose(Q2)

- `deploy/compose/compose.yaml` に `crawler` サービスを追加する。テスト用の上書きは `tests/integration/crawler/compose.test.yaml`。
- `scripts/run-indexer-integration-test.sh` は起動サービスを `opensearch opensearch-init indexer` に明示し、crawler が巻き込まれないようにする。
- `scripts/run-crawler-integration-test.sh` を新設する。
- `crawler` サービス: 公開は `127.0.0.1:8001` のみ / `stop_grace_period` 30秒以上 / healthcheck の start_period を十分長く / `LORELEY_CRAWLER_INDEXER_*` の上限値を Indexer の実際の値と同じにする / `JOBS_INDEX_NAME` を Indexer・`opensearch-init`・Crawler で同値にする / OpenSearch と Indexer(healthy)への `depends_on`。

### テスト文書(Q3)

- `tests/integration/crawler/data/`(gitignore)を Crawler に `:ro` でバインドマウントする。
- 固定サンプルは `tests/integration/crawler/samples/`。テストが `source_id` ごとのサブディレクトリ(`root` = `/data/documents/<source_id>`)にコピー・削除する。ファイルは uid 10001 が読める `a+rX` にする。
- 読めないファイルのシナリオがホスト権限で不安定な場合は、削除またはサイズ超過で代替する。

### スキーマ

- `infra/opensearch/schema/sources.json` を新設し `loreley-sources` を作る(`dynamic: strict`、項目・型は arch v0.4 の 3.1・3.2、`connector_config` は object で索引しない)。
- `jobs.json` は `dynamic: false` のまま、arch 3.1 のマッピング案の項目(`record_type`、`source_id`、`job_type`、`status`、`trigger`、各 date 項目など)を追加する。Indexer が読む4項目(`owner`・`job_id`・`lease_expires_at`・`enabled`)の型は変えない。Indexer の IT-01(`dynamic: false` の検証)を維持する。
- `init-indices.sh` に `loreley-sources` の作成と索引名の環境変数(例 `SOURCES_INDEX_NAME`)を追加し、冪等性を維持する。
- 毎回 `down -v` で新規作成するため、既存環境への put mapping は行わない。

### テスト方式・基準

- `tests/integration/crawler/` に専用 pyproject と `uv.lock` を置き、pytest をホストから実行する。compose プロジェクト名は `loreley-it`。`up --wait` は使わず自前ポーリング(compose v2.3.3 では戻らないため)。
- ジョブ状態は Crawler に取得 API がないため、OpenSearch の `loreley-jobs` / `loreley-deletions` / 検索インデックスを直接読む。
- 作法: 一意な `source_id`、検索系確認前の `_refresh`、sleep に頼らず間隔と上限を明示したポーリング、コメントで何をテストしているかを明示する。
- 完了条件(具体化):
  - 一括スクリプトがクリーンな状態から2回連続で全テスト成功(終了コード 0)
  - Indexer の結合テスト 40 件が、スキーマ・compose・スクリプトの変更後も成功(回帰確認)
  - Crawler を修正した場合は、Crawler の単体テスト・ruff も成功
- 結果記録は `docs/v0.x/test-results/crawler-integration.md`。未実施項目は「未実施」と明記する。
- 手順書は `tests/integration/crawler/README.md` と `deploy/compose/README.md` の更新で用意する。
- 失敗が見つかったとき: 軽微なものは Crawler(単体テストも併せて追加)かテストを修正する。設計に関わる食い違いは止めてユーザーに報告する。
- CI への組み込みは対象外。

## 前提として置いた事項(プラン承認時に再確認する)

- Crawler IT 用の上書きは Indexer 用とは別にする。Indexer 用の `MAX_RAW_BYTES=64KiB` は流用しない(Crawler 既定 20MiB が Indexer 上限を超え、整合性検査で起動失敗するため)。`POLLING_INTERVAL_SECONDS`・`RUNNER_SCAN_INTERVAL_SECONDS`・Indexer の `DELETION_POLL_INTERVAL_SECONDS` は小さくする。
- ユーザー回答中の「ロック解放」は「実行中のロックが存在し、ジョブ終了後に解放されること」と解釈した(ロック解放 API は対象外の運用系)。
- メモリ約3.8GiB で OpenSearch + Indexer + Crawler を同時起動する。逼迫した場合は症状と対処を記録する。

## プラン作成時に決める事項

- TTL 削除の時刻の作り方(小さい `ttl` + ポーリング、または OpenSearch へ直接書いて `last_seen_at` を過去にする前提作り)。割合ルール(`ratio_threshold`・`min_delete_count`)が削除を妨げない値にする
- 実行スクリプトの共通化か複製か
- Indexer の IT のサンプル文書の再利用か独自保持か(モジュール間 import は避け、複製が基本)
- スキップの具体的な再現方法(権限 `fetch_permission_denied` かサイズ超過か)
- 各シナリオの ID 割り当て、`compose.test.yaml` の具体値、ポーリング上限値
- レビューの割り当て(code-reviewer / test-reviewer / document-reviewer、タスクレビューの要否)

## 変更したファイル

- 本ファイルの新規作成、`STATUS.md` の更新のみ。

## 未対応事項・次にやること

1. planner でプランを作成し、`0002-work-plan.md` として保存してユーザーの承認を得る
