# 0002 作業プラン: Admin API の Integration Test 作成

日付: 2026-11-25
状態: ユーザー承認待ち(承認前は実装しない)
作成: planner(`STATUS: PLAN_READY`)。メインエージェントが保存。

## 1. 目的とゴール

Admin API・Crawler・Indexer・OpenSearch を compose で起動し、実際の Admin API(`127.0.0.1:8080`)を HTTP で呼ぶ IT を作って成功させる。単体テストで足りる内容は重複させず、実 Crawler への中継、実 OpenSearch へのクエリ、実プロセスの停止と復旧を中心に検証する。

受け入れ基準:
- A1: `scripts/run-api-integration-test.sh` 1 本で、起動 → 待機 → pytest → 後始末まで実行できる
- A2: 6 章のシナリオ(AIT-01〜AIT-92)がクリーンな状態から 2 回続けて全件成功する
- A3: 終了時に `loreley-it` のコンテナ・ボリューム・ネットワークと `tests/integration/api/data/` が消え、他プロジェクトのコンテナ・イメージに変化がない(`--keep` のときは残す)
- A4: 既存の単体テストに退行がない(`apps/api` は常に実行。変更したアプリはその単体テストと ruff も)。`compose.yaml` を変えるので、既存の Crawler・Indexer IT も各 1 回再実行して成功する
- A5: 実行方法・結果・未検証事項を `tests/integration/api/README.md` と `docs/v0.x/test-results/admin-api-integration.md` に記録する

## 2. 確定事項・前提

### 2.1 確定事項(0001)
- 検証範囲: 主要ユースケース 5 群 + 実機限定の申し送り(EP-07 実行中取消、EP-08 実ロック解放、`lock_held`/`lock_in_use` 409、実行中の `lock_state`、`force_delete=true`、AAA-U-1、AAA-U-2)
- 未検証として記録: AAA-U-7、AAA-U-10、10,000 件窓、一部シャード障害、複数ノード `cat.*`・`relocating`、`ClientDisconnect`、BAPI-U-2(入れ子マウント・`root_path`)、`stalled=true`・`lease_expired`、AAPI-U-7
- api の compose: `deploy/compose/compose.yaml` に `api` を追加(HO-34・35 解消、api-base-design-v0.1 8章)。HO-43・44 は 1 つの共通変数から Crawler・api の両方へ。Web 成果物(HO-36・37)はスコープ外。テスト差分は `tests/integration/api/compose.test.yaml`
- 障害系: pytest から `docker compose -p loreley-it stop/start`。許可リスト・`finally` で復旧・期限付き healthy 待ち・`test_90_*` に集約。対象は crawler・indexer・opensearch
- `OPENAPI_ENABLED` は既定(無効)のまま。EP-13 の `web` は `index.html` のみのディレクトリを mount して `normal` にする

### 2.2 本プランで決めた事項
- **Crawler ポーリング間隔 `LORELEY_CRAWLER_POLLING_INTERVAL_SECONDS=10`**(Crawler IT は 2)。根拠: Crawler は終了通知直後に Indexer の状態を 1 回読み(まだ `running`)、その後間隔分待つ(`apps/crawler/src/loreley_crawler/crawl/status_polling.py:92-108`)。ロックを持つ時間はほぼこの間隔(約 10 秒)で、HTTP 数回の操作(1 秒未満)より十分長く、クロール 1 回は約 10〜12 秒。
  - 補完: Indexer `LORELEY_INDEXER_DELETION_POLL_INTERVAL_SECONDS=5`(既定 2)。終了通知から Crawler の最初の確認までに Indexer の削除が終わってしまう競合の確率を下げる。文書数での補完はしない
  - その他: `POLLING_TIMEOUT_SECONDS=120`、`RUNNER_SCAN_INTERVAL_SECONDS=1`、Crawler healthcheck `interval: 3s`・`start_period: 180s`、原本上限 64 KiB(`MAX_RAW_BYTES` を Indexer・Crawler・Crawler の検査値の 3 か所で同値)。いずれも Crawler IT と同じ
- **シナリオ ID `AIT-nn`**。ファイル番号帯と対応。ID はテスト関数名に含めず、ファイル冒頭 docstring に書く(既存 IT と同じ)
- **compose 変数名**: 新設 `API_HOST_PORT`(8080)、`API_LOG_LEVEL`(INFO)、`LORELEY_DELETIONS_INDEX_NAME`(loreley-deletions)、`LORELEY_SEARCH_INDEX_ALIAS`(loreley-documents)、`LORELEY_CRON_TIMEZONE`(UTC)、`LORELEY_ADMITTING_LOCK_GRACE_SECONDS`(60)。流用: `LORELEY_JOBS_INDEX_NAME`、`LORELEY_SOURCES_INDEX_NAME`。
  - 既定値の根拠: Crawler の `timezone` 既定 UTC(`apps/crawler/src/loreley_crawler/config.py:312`)、猶予既定 60(`jobs/settings.py:29`)、Indexer 既定(`infrastructure/opensearch/connection.py:11-12`)、init 既定(`infra/opensearch/init-indices.sh:18-22`)
  - `LORELEY_CRON_TIMEZONE` 既定を UTC にすると api の EP-14 は `null` でなく `UTC` を返す(Crawler の実際の既定と一致。HO-43 の趣旨)

### 2.3 前提(既存 IT にならう)
- プロジェクト名 `loreley-it`。ポート 9200・8000・8001・8080 固定、127.0.0.1 のみ。既存 IT と同時実行不可。他プロジェクトのコンテナは止めない・消さない(9200 を Fess 等が使っていれば中止し相手を表示)
- スクリプトは `scripts/run-crawler-integration-test.sh` を複製して直す(共通ライブラリ化しない)。起動前に残骸(コンテナ・ボリューム・空でない `data/`・使用中ポート)があれば何も消さず中止。`up -d` 後は自前ポーリング(`--wait` 不使用)。終了時 `down -v --remove-orphans` と `data/` 削除。`--keep`、`LORELEY_IT_WAIT_TIMEOUT_SECS`(既定 300)、終了コード体系は既存と同じ
- `tests/integration/api/compose.test.yaml` は単独で重ねる(Crawler 用は重ねず、必要値は複製)
- テストデータ: `tests/integration/api/data/<source_id>/`(`.gitignore` の `tests/integration/*/data/` で除外済み)。内容は実行時生成。`source_id` は `it-` 始まりでテストごとに一意。削除確認テスト以外はデータを消さない
- 依存は `tests/integration/api/pyproject.toml`(pytest・httpx、dev に ruff)+ `uv.lock`。`document_id` は独立実装でアプリのコードを import しない
- 待ちは間隔と上限を明示した `poll_until`。超過時は最後の状態を付けて失敗。判定は Admin API 応答、必要なら OpenSearch 直接読みで裏付け
- 実機が設計と違ったらテストを実機に合わせず発見事項として記録。アプリ不具合は最小修正+単体テスト+作業記録。設計変更が要る修正は止めてユーザー確認
- **前提作りのための OpenSearch への直接書き込みは 2 か所のみ**(既存 IT `force_last_seen_at` が前例):
  - AIT-51: 孤児ロック(終端ジョブの `job_id`、2 時間前の `acquired_at`)
  - AIT-41: スキップ記録 2 件(実在文書の `document_id` 1 件、存在しない ID 1 件)
  - 形式は crawler-architecture 3.3・5.1、`infra/opensearch/schema/jobs.json` に合わせる
- 設計書は変更しない。HO-34・35・40・41・43・44 の状態更新(api-base-design 9.2)は申し送りに記録。`apps/api/Dockerfile` には触れない

## 3. 影響範囲

| パス | 変更 | 内容 |
| --- | --- | --- |
| `deploy/compose/compose.yaml` | 変更 | `api` 追加。`opensearch-init`・`indexer`・`crawler` に共通変数追加。冒頭コメント更新 |
| `deploy/compose/.env.example` | 変更 | `API_HOST_PORT`・`API_LOG_LEVEL`・新共通変数 4 つ |
| `deploy/compose/README.md` | 変更 | 構成表に `api`、変数、公開範囲の注意(認証なし・127.0.0.1 限定・HO-40・41)、`web` が `abnormal` に見える注記(HO-36 未対応)、起動直後の見え方(HO-45)、IT 同時実行不可 |
| `scripts/run-api-integration-test.sh` | 新規 | 一括実行 |
| `scripts/run-crawler-/run-indexer-integration-test.sh` | 小変更 | 新索引名変数 2 つも既定値で固定。コメントに api IT を追加 |
| `tests/integration/crawler/README.md`・`indexer/README.md` | 小変更 | 「api の IT と同時実行不可」注記 |
| `tests/integration/api/` | 新規 | `pyproject.toml`・`uv.lock`・`compose.test.yaml`・`conftest.py`・`support.py`・`test_01`〜`test_90`・`fixtures/web/index.html`・`README.md` |
| `docs/v0.x/test-results/admin-api-integration.md` | 新規 | 結果記録 |
| `apps/api`・`apps/crawler`・`apps/indexer`・`infra` | 必要時のみ | IT で見つかった不具合の修正 |

## 4. 構成の詳細

### 4.1 `compose.yaml` の `api`
- build `../../apps/api`、環境変数: `LORELEY_API_OPENSEARCH_URL=http://opensearch:9200`、`..._CRAWLER_URL=http://crawler:8001`、`..._INDEXER_URL=http://indexer:8000`、`..._LOG_LEVEL=${API_LOG_LEVEL:-INFO}`、`..._SOURCES_INDEX_NAME`、`..._JOBS_INDEX_NAME`、`..._DELETIONS_INDEX_NAME`、`..._SEARCH_INDEX_NAME=${LORELEY_SEARCH_INDEX_ALIAS:-loreley-documents}`(エイリアス。init の実体名は渡さない)、`..._CRON_TIMEZONE=${LORELEY_CRON_TIMEZONE:-UTC}`、`..._ADMITTING_LOCK_GRACE_SECONDS=${LORELEY_ADMITTING_LOCK_GRACE_SECONDS:-60}`
- ports `127.0.0.1:${API_HOST_PORT:-8080}:8080`、`depends_on: opensearch(healthy), opensearch-init(completed)`(crawler・indexer は待たない)、`restart: unless-stopped`、healthcheck はイメージの `/healthz`、検索対象 mount なし
- `opensearch-init` に `DELETIONS_INDEX_NAME`・`SEARCH_INDEX_ALIAS`、`indexer` に `LORELEY_INDEXER_DELETIONS_INDEX_NAME`・`..._SEARCH_INDEX_NAME`、`crawler` に `LORELEY_CRAWLER_TIMEZONE`・`..._ADMITTING_LOCK_GRACE_SECONDS` を同じ変数から追加。`OPENAPI_ENABLED` は書かない

### 4.2 `tests/integration/api/compose.test.yaml`
- indexer: `MAX_RAW_BYTES` 65536、`DELETION_POLL_INTERVAL_SECONDS` 5
- crawler: `127.0.0.1:${CRAWLER_HOST_PORT:-8001}:8001` を publish(診断用。テストは Crawler API を直接呼ばない)、`MAX_RAW_BYTES`・`INDEXER_MAX_RAW_BYTES` 65536、2.2 のポーリング値、healthcheck `interval: 3s`・`start_period: 180s`
- api: `../../tests/integration/api/fixtures/web:/app/web:ro` を mount(相対パスは最初の compose ファイルのディレクトリ基準。P2 で EP-13 `web=normal` で実効を確認)、healthcheck `interval: 3s`

### 4.3 スクリプト
- 既存との違い: ポート確認 4 つ(`*_HOST_PORT` 4 つ export)、索引名 4 つを既定値で export、`LORELEY_CRON_TIMEZONE=Asia/Tokyo` を export(共通変数が api に届くことを AIT-01 で確認)、`CRAWLER_DOCUMENTS_DIR=tests/integration/api/data`(絶対パス)、起動は `opensearch opensearch-init indexer crawler api`、`LORELEY_IT_ALLOW_COMPOSE_CONTROL=1` を export、pytest 既定引数 `-v -rP`、結果は `tests/integration/api/results/`

### 4.4 `support.py`
- `AdminApi`(14 EP + `/healthz`。応答は検査せず返す)、`OpenSearchProbe`(読みは Crawler IT から複製、書きは 2.3 の 2 種のみ)、`SourceDirectory`、`compute_document_id`、`poll_until`、`expect_json`/`expect_error`、待ちヘルパ(ジョブ終端・`running` 観測・ロック解放・アイドル)
- `ComposeControl`(障害系専用): 引数リストで `docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/api/compose.test.yaml stop|start <service>`(shell 不使用、`subprocess` タイムアウト付き)。プロジェクト名・compose ファイルは定数。許可リスト `{crawler, indexer, opensearch}` 以外は例外。操作前に `ps -q` で実在確認。`LORELEY_IT_ALLOW_COMPOSE_CONTROL=1` がなければ障害系を skip。`wait_healthy` は `docker inspect` を期限付きポーリング
- 定数(仮): ジョブ完了待ち 90 秒、`running` 観測 30 秒、ロック解放 30 秒、アイドル待ち 120 秒、サービス復旧 300 秒。ポーリング間隔 0.5 秒(ロックは 0.2 秒)

### 4.5 `conftest.py`
- session autouse: OpenSearch・Indexer・Crawler・api の疎通確認(失敗は `pytest.exit(returncode=2)`)、`data/` の存在、メンテナンスフラグ残りなし
- function autouse: 各テスト前後でアイドル(実行中・待ちジョブ 0)を期限付きで待つ(Job Runner は直列で、前テストのジョブが後の窓を乱さないため)
- フィクスチャ: `source_id`(一意)、`SourceDirectory`、`registered_source`

## 5. 単体テストとの重複回避

IT で検証しない(`apps/api/tests` で確認済み): 入力検証の全パターン、ページ上限(`page × items_per_page > 10000`)、ID エンコード(0018 実機確認済み)、`config_invalid` 分解の境界、Crawler 写像表の全行、タイムアウト・再試行、`ClientDisconnect`、OpenAPI 宣言、ログ語彙、`unavailable` 理由コードの選び分け、`lock_state` 7 値の全分岐。

IT で検証するのは実物にしかない点: 実 Crawler・Connector が返す形の写し、実 OpenSearch クエリ(集計・`top_hits`・`mget`・`msearch`・`ids`・並べ替え・`from`/`size`)の応答を OpenSearch 直接読みで独立計算した期待値と照合、実プロセスの停止と復旧。正常系の `unavailable` は `{}` のみ確認。

## 6. シナリオ一覧

各テストの docstring に【何を確認するか】【前提と手順】【期待する結果と根拠(B = admin-api-v0.1 の章)】【単体テストでは確認できず実機で確認する点】を書く。

| ID | ファイル | EP | 検証内容 |
| --- | --- | --- | --- |
| AIT-01 | test_01_startup | healthz・13・14・12 | (a) `/healthz` 200。(b) EP-13 は 8 件が固定順で crawler・indexer・opensearch・api・web が `normal`、他 3 つが `not_configured`。(c) EP-14 `cron_timezone=Asia/Tokyo`、`dashboards_url=null`。(d) EP-12 に `loreley-documents-000001`・`loreley-deletions`・`loreley-jobs`・`loreley-sources`、`truncated=false`。(e) openapi.json は 404 |
| AIT-10 | test_10_sources | 3・4・1・2 | (a) EP-03 201、`loreley-sources` 直読みで `ttl`(秒)・`ratio_threshold` に変換保存。(b) 同内容再送 200。(c) 内容違いは 409 `source_already_exists`。(d) EP-02 `lock.state=none`・`last_crawl=null`・`document_count=0`。(e) EP-04 200 で保存値・`updated_at` 更新。(f) EP-01 に `source_id` 昇順で現れる |
| AIT-11 | test_10_sources | 3・4 | 実 Connector の違反(相対 `root`、未知項目)が 400 `config_invalid`。`field`・`reason`・`detail`(Connector 固定文と一致)・`crawler_message` 非空。保存されない |
| AIT-12 | test_10_sources | 2・4・5・6・8・11 | 未登録ソース: EP-04・05・06 は 404 `source_config_not_found`、EP-02・11 は 404、EP-08 は 200 `released=false` |
| AIT-20 | test_20_crawl | 6・10・2・9・5・8・1 | 起動 202 → `running` 観測。実行中: EP-02 `held_crawl`、EP-09 `active` に当該ジョブ(`stalled=false`・`cancellable=true`)、EP-06 再送 409 `lock_held`、EP-05 409 `lock_held`、EP-08 409 `lock_in_use`。終了後: EP-10 `succeeded`・`registration` 件数・`phase=final`・`deletion.confirmation=confirmed`・`latest_for_source=true`・`rerunnable=false`、EP-02 `lock.state=none`・`last_crawl`・`document_count`、EP-01 の行。OpenSearch のジョブ記録と突き合わせ |
| AIT-21 | test_20_crawl | 6・10・1 | `force_delete=true` の中継。ttl 1 秒のソース: クロール A(4 件)→ 2 件削除 → 通常クロール B は割合ルールで削除が止まる → `force_delete=true` のクロール C で `deletion.summary.forced=true`・`deleted_count=2`・EP-01 `document_count=2`。`rewrite_mode=true` も C で中継。割合ルールの正確な条件は indexer-architecture 9 章で確認 |
| AIT-30 | test_30_queries | 1 | ソース 3 つ(2 回・1 回・0 回クロール)+ それまでの全ソースの全行について、`last_crawl`・`last_completed_at`・`document_count` を OpenSearch 直読みの独立計算と照合。`source_id` 昇順。AAA-U-1(`terms` の `size`、`top_hits`) |
| AIT-31 | test_30_queries | 9・10 | `source_id` 絞り込みの `total`、`sort=queued_at`/`-queued_at` の順序逆転、`status=succeeded` 絞り込み、範囲外 `page=2` は `items=[]`、`window_limit=10000`、`latest_for_source`(古い方は false) |
| AIT-32 | test_30_queries | 12 | `indices`・`shards`・`nodes`・`cluster` を `_cat/*`・`_cluster/health` 直読みと照合。`total_indices = len(indices)` |
| AIT-40 | test_40_documents | 11・10・1 | 通常 md 3・壊れ PDF 26(`extract_failed`)・70,000 バイト 2(`oversize`)を 1 回クロール。(a) `tab_counts={skipped:0, extract_failed:26, oversize:2, summary_pending:0}`、`document_count=29`(EP-01 と一致)。(b) `extract_failed` の 1 ページ目 25 件・2 ページ目 1 件、和集合が独立計算の 26 件と一致、重複なし。(c) 既定 `-last_seen_at` と昇順、同時刻は `document_id` 昇順、`items_per_page=50` で 26 件。(d) `oversize` 項目。(e) EP-10 `oversize_count=2`・`error_count` |
| AIT-41 | test_40_documents | 11 | 直接書き込みでスキップ記録 2 件。`skipped` タブで `existence` が `existing`・`new`、`tab_counts.skipped=2`、AAA-U-2(`ids` クエリ)。※AAPI-U-7(Crawler が書いた記録の照合)は未検証のまま |
| AIT-50 | test_50_cancel_and_lock | 6・7・9・10・2 | X のクロール起動 → `finish_notice.send_started_at`(直読み)待ち。その間に Y を起動して実行待ち。(a) EP-09 `active` に X(running)・Y(queued)、EP-02 の Y は `held_crawl`・`status=queued`。(b) EP-07 で Y 取消 200 `cancelled`、Y ロック `none`。(c) EP-07 で X 取消 202 `running` → EP-10 `cancelled`・`cancel_after_finish_notice=true`・`warnings` に `polling_aborted`・ロック `none`。(d) X 再取消 409 `job_already_finished` |
| AIT-51 | test_50_cancel_and_lock | 2・6・8 | 孤児ロックを直接書く(`acquired_at` 2 時間前)。(a) EP-02 `orphan`。(b) EP-06 409 `lock_held`(`lock_state=orphan`)。(c) EP-08 200 `released=true`・`failed_job_id=null`、ロック文書が消える。(d) 再送 `released=false`。(e) EP-06 202 → `succeeded` |
| AIT-60 | test_60_source_deletion | 5・7・6・1・2・10・11・8 | 別ソース Z のクロール実行中に文書ありソース S の EP-05 → 202(`source_delete`、`queued`)。(a) EP-02 S は `held_delete`、EP-06 S は 409 `lock_held`(`existing_job.job_type=source_delete`)、EP-07 で削除ジョブ取消は 409 `job_not_cancellable`。(b) 完了後: EP-10 `succeeded`、EP-02・11 の S は 404、EP-01 に S なし、OpenSearch に S の文書・記録なし、Z は残る、EP-08 S は `released=false` |
| AIT-90 | test_90_component_failures | 全 | crawler stop: EP-13 crawler `abnormal`(`reason` は `connection_refused` or `name_not_resolved`。値を記録)、他 `normal`。EP-03〜08 は 503 `crawler_unreachable`(`retryable=true`)、EP-01・02・09・10・11・12・14 は 200。start・healthy 後、EP-13 `normal`、EP-06 202 → `succeeded` |
| AIT-91 | test_90_component_failures | 13・06・05・10・01・02・04・03・11 | indexer stop: EP-13 indexer `abnormal`、crawler・opensearch `normal`、読み取り EP は 200。(a) 停止中のクロールは終端まで期限付きで待ち状態と `failure_reason` を記録(断定しない)、`failed` なら `rerunnable=true`。(b) 停止中のソース削除は `failed` で終わるはず(`deleting` 順 0 → Indexer 失敗)。EP-01・02 `status=deleting`・`delete_job`、EP-04・06 409 `source_deleting`、同内容 EP-03 409 `source_already_exists`(`deleting`)、EP-11 200。(c) 復旧後: EP-05 再実行 `succeeded` でソース消滅、(a) のソースは EP-06 再実行 `succeeded`、古いジョブは `rerun_blocked_reason=superseded` |
| AIT-92 | test_90_component_failures | 全 | opensearch stop: EP-01・02・09・10・11・12 は 503 `unavailable`(`retryable=true`)、EP-13 opensearch `abnormal`・api `normal`(crawler・indexer は記録)、EP-14・`/healthz` 200、EP-06 は 503 `crawler_unavailable` か `crawler_unreachable`(記録)。start 後、4 サービスの healthy を最大 300 秒待ち、EP-01 200・EP-13 全 `normal`・クロール `succeeded` |

- EP-01〜14 のすべてを少なくとも 1 シナリオが実コンポーネント経由で呼ぶ
- 所要時間見込み: クロール約 17 回(1 回 10〜12 秒)+ 障害系復旧待ち + 起動(初回ビルド込み)で 1 回 10〜20 分(実測して記録)
- AIT-41・51 の直接書き込みは前提作りのみ。判定は Admin API と実 Crawler の応答

## 7. 実装フェーズ

実装は `code-implementer`(レビュアーと分離)。docker 実行は `scripts/run-api-integration-test.sh` と `docker compose -p loreley-it …` のみ許可、他プロジェクトのコンテナ・イメージ・ボリュームの操作は禁止(依頼文に明記。ローカル起動も禁止の場合は明記)。フェーズごとにメインエージェントが作業記録・STATUS.md 更新・コミット。ブランチ `feature/create-it-for-admin-api`、比較基準 `55dce2f`(開始時に再記録)。

- **P1 compose・設定・既存スクリプト**: 成果物は `compose.yaml`、`.env.example`、`deploy/compose/README.md`、既存 2 スクリプト、Crawler・Indexer IT README。検証: `docker compose -p loreley-it -f deploy/compose/compose.yaml config` で環境変数展開、`api` の ports が 127.0.0.1 限定、`bash -n`(あれば `shellcheck`)。受け入れ: HO-34・35・43・44 を満たす(検索エイリアスに実体名を渡さない)。既存 2 スクリプトの起動サービスは不変
- **P2 IT の土台とスクリプト**(P1 依存): `tests/integration/api/` の土台一式、`scripts/run-api-integration-test.sh`、`test_01_startup.py`。検証: ruff、`pytest --collect-only`、AIT-01 のみ実行して成功、事前確認の中止(空でない `data/` で何も消さず終了コード 1)、終了後に `loreley-it` の残りなし。受け入れ: EP-13 `web=normal`、`cron_timezone=Asia/Tokyo`
- **P3 正常系**(P2 依存): `test_10`〜`test_60`(AIT-10〜60)。ファイル単位で `--keep`・`-k` 反復。失敗時はテスト誤り/アプリ不具合/設計食い違いを切り分け、アプリ不具合は最小修正+単体テスト+記録、設計食い違いは発見事項記録(テストは設計に合わせたまま、通す必要があればユーザー判断)。受け入れ: 表の検証内容をすべてアサート、待ちは全て上限あり
- **P4 障害系**(P3 依存): `test_90`(AIT-90〜92)。検証: 全件成功、途中失敗させても `finally` で start・healthy 待ち・後始末まで終わることを 1 回確認(確認後に元に戻す)、`docker ps -a` 前後比較で他プロジェクトに変化なし。受け入れ: `ComposeControl` が許可リスト外サービス・別プロジェクトを操作できない
- **P5 最終確認と記録**(P4 依存、メインエージェント): クリーン状態から 2 回連続全件成功(A2)、後始末確認(A3)、`apps/api` 単体テスト・ruff(変更アプリも)、既存 Crawler・Indexer IT 各 1 回(A4)。成果物: `tests/integration/api/README.md`(目的・前提・実行方法・終了コード・環境変数・シナリオ一覧・設計上の注意)、`docs/v0.x/test-results/admin-api-integration.md`(環境・シナリオ別結果・0021 B 各項目の判定・発見事項・観測値・所要時間・未検証・再実行手順)

## 8. レビューフェーズ

P5 後に 3 つを並列実施。比較基準は実装開始 SHA から HEAD。文脈は 0000・0001・本プラン・各フェーズの作業記録。
- **code-reviewer(必須)**: `compose.yaml`・`.env.example`・各スクリプト・`compose.test.yaml`・`conftest.py`・`support.py`・アプリ修正差分。重点: api の公開範囲(127.0.0.1)、索引名と共通変数の配線、`stop/start` の許可リストとプロジェクト固定、`rm -rf`・`down -v` の安全性、subprocess タイムアウト
- **test-reviewer**: `test_*.py`・`support.py`・`conftest.py`。重点: 表とアサートの対応、単体テストとの重複、待ちの上限・不安定さ、テスト間独立性、直接書き込みの範囲、期待値が実機に合わせて曲げられていないか
- **document-reviewer**: 各 README の差分・`admin-api-integration.md`。重点: 事実と推測の書き分け、公開範囲の注意、手順の正確さ、未検証事項の網羅
- web-ui-reviewer は省略(Web UI の変更なし。`fixtures/web/index.html` はテスト用の空ファイル)

## 9. レビュー指摘への対応

Critical・Important は `code-implementer` が修正、必要なら IT 再実行(コード・テスト変更時は全件)、同じレビュアーで再レビュー。解消までレビューフェーズ未完了。Suggestion・Nitpick はメインエージェントが判断し作業記録に残す。対応ごとに作業記録と STATUS.md 更新。

## 10. タスクレビューフェーズ

複数フェーズ・データ削除・コンテナ操作を含むため実施。レビュー完了と全作業記録作成後に `task-reviewer`。Critical・Important は該当工程に差し戻し再レビュー。解消までタスク未完了。

## 11. テスト方針

- IT 自体: 6 章の各シナリオ。期待値の根拠は設計書の章、可能なものは OpenSearch 直読みの独立計算と照合
- 安定性: クリーンから 2 回連続成功。窓依存テスト(AIT-20・50・60)は操作前に `running`(必要なら `send_started_at`)を観測。窓が閉じた場合は原因が分かるメッセージ
- 安全性: 他プロジェクトのコンテナ前後比較(P4)、事前確認による中止(P2)、障害系の後始末(P4)
- 退行: `apps/api` 単体テスト・ruff 常時、修正アプリも、既存 Crawler・Indexer IT 各 1 回(P5)
- 静的検査: `tests/integration/api` の ruff(check・format)、スクリプトは `bash -n`(あれば `shellcheck`)

## 12. リスクと対策

| リスク | 対策 |
| --- | --- |
| 実行中の窓(約 10 秒)の競合で Indexer の削除が先に終わりジョブがすぐ終わる | Indexer 走査間隔 5 秒、操作前に `running` 観測、失敗メッセージで判別、頻発なら間隔見直し(記録) |
| compose v2.3.3 で `stop`/`start` が想定と違う | 0018 で crawler・opensearch 単独停止は確認済み。P4 冒頭で `ps` 確認、違えば止めて相談 |
| api がコンテナ内のため EP-13 の `reason` が 0018 と違う(`name_not_resolved`) | どちらも `abnormal` として受け入れ値を記録 |
| OpenSearch 停止後の crawler・indexer 復旧が遅い(最大約 3 分) | 復旧待ち上限 300 秒、障害系は最後のファイルに集約 |
| 9200 を Fess などが使用 | 事前確認で中止し相手を表示。EP-12 照合は直接 `_cat` と比べるので外部索引が混ざっても壊れない |
| 実機で設計食い違い・アプリ不具合 | テストを実機に合わせない。不具合は最小修正+単体テスト+記録。設計変更要はユーザー判断 |
| `compose.yaml` 変更で既存 IT・開発起動が壊れる | P1 の `config` 確認、P5 で既存 IT 再実行、ロールバックは revert のみ |
| 実行時間が長い(10〜20 分) | 反復は `--keep`・`-k`、全件実行は各フェーズ末と P5 のみ |
| Docker メモリ不足(5 サービス) | README に約 4GB 以上を推奨と記載、診断出力で判別 |

ロールバック: 新規ファイルと追記のみ。フェーズ単位のコミットの revert で戻せる。

## 13. 未解決事項

- AIT-21 の割合ルールが削除を止める正確な条件は実装時に indexer-architecture 9 章で確認
- AIT-91 の停止中クロールの終わり方は観測して記録
- 2.1 の未検証に加え、EP-09 の複数ページ(26 件以上のジョブが必要)も未検証として記録。ページング実応答は EP-11(AIT-40)で確認
- 「EP-05 の `force_delete=true`」の解釈: EP-05 は本文を取らず `force_delete` は `null`(B 3.5)。`force_delete=true` は EP-06 で確認し、EP-05 はソース削除そのもの(AIT-60・91)
- 申し送り: api-base-design 9.2 の HO-34・35・40・41・43・44 の状態更新(設計書追従改訂タスクへ)

## 承認時にユーザー確認が必要な点(推奨案前提)

1. **前提作りのための OpenSearch 直接書き込み(AIT-51 孤児ロック、AIT-41 スキップ記録)**: 推奨は採用(既存 IT `force_last_seen_at` と同前例)。Crawler 自身に解放可能な実ロックを作らせる方法がなく(起動時回復が自分のロックを消す)、`fetch_permission_denied` は macOS bind mount で作れるか不明。判定は実 Crawler・Admin API の応答。代替: 直接書き込みをやめ EP-08 実解放と `ids` クエリを未検証として記録
2. **Crawler ポーリング間隔 10 秒・Indexer 削除走査間隔 5 秒**: 推奨は採用。代替: 短縮(例 6 秒・3 秒)すると実行時間は縮むが窓の競合による不安定さが増える
3. **共通変数既定 `LORELEY_CRON_TIMEZONE=UTC`**: 推奨は UTC(EP-14 は `null` でなく `UTC`、Crawler の実際の既定と一致)。代替: 既定を空にして EP-14 が `null` を返す現状を保つ
