# 0018 P7: 手動スモーク(実 OpenSearch・実 Crawler・実 Indexer)

日付: 2026-11-24

## 実施内容

プラン 4.1 の手順で、メインエージェントが手動スモークを実施した。変更操作を伴う(プラン承認で許可済み)。対象は専用の compose プロジェクト `loreley-admin-smoke` と、その一時データ(一時ディレクトリの文書、登録したテスト用データソース)だけ。開発用スタック・`loreley-it`・他プロジェクトのコンテナ/イメージには触れていない。

### 事前確認

- 9200・8000・8001・8080 は未使用(`lsof` と `docker ps --filter publish=` で確認)。9200 を使うプロジェクトなし
- `loreley-admin-smoke` のコンテナ・ボリュームの残りなし。別プロジェクトの停止中コンテナ `opensearch-opensearch-1`(2 週間前に終了)があったが触れていない
- Docker 20.10.13 / Docker Compose v2.3.3

### 環境

- 文書ディレクトリ(`mktemp` 相当、scratchpad 配下): `hello.md`・`sub/guide.md`・`notes.md`(通常)、`big.md`(約 90 KB。`MAX_RAW_BYTES` 64 KiB を超える)、`data.xyz`(対象外拡張子)
- スタック起動: `docker compose -p loreley-admin-smoke -f deploy/compose/compose.yaml -f tests/integration/crawler/compose.test.yaml up -d --build opensearch opensearch-init indexer crawler`(OpenSearch 9200・Indexer 8000・Crawler 8001。すべて healthy、`opensearch-init` は正常終了)
- api: `uv run python -m loreley_api.main`(`OPENSEARCH_URL`・`CRAWLER_URL`・`INDEXER_URL`・`CRON_TIMEZONE=Asia/Tokyo`・`WEB_DIST_DIR`(`index.html` のみ置いた一時ディレクトリ)・`OPENAPI_ENABLED=true`)

## 確認結果

| EP・観点 | 結果 |
| --- | --- |
| `/healthz` | 200 `{"status":"ok"}` |
| EP-14 | `cron_timezone=Asia/Tokyo`・`dashboards_url=null` |
| EP-13 | crawler・indexer・opensearch・api・web が normal、任意の 3 つ(opensearch-dashboards・embedding・llm)は `not_configured`。固定の順 8 件 |
| EP-12 | 6 索引(`loreley-*` の 4 索引を含む)・`truncated=false`・`total_indices=6` |
| EP-01(空 → 登録後 → クロール後 → 削除後) | 空は `{"items":[],"unavailable":{}}`。クロール後は `last_crawl`・`last_completed_at`・`document_count=4`。削除後は空に戻る。最上位 `unavailable` は常に `{}` |
| EP-02 | 登録後 `lock.state=none`・`last_crawl=null`。クロール後は `last_crawl`・`index.document_count=4`。削除後は 404 `source_config_not_found` |
| EP-03 | 不正な設定(未知の項目)→ 400 `config_invalid`(`field=connector_config`・`detail`「未知の項目がある」・`crawler_message`。B 2.5 の例外の形)/ ttl 両方指定+範囲外 → 400 `invalid_request`(`ttl_days` の `exclusive`・`ratio_threshold_percent` の `range`)/ 正しい内容 → 201(`ttl_seconds=604800`・`ttl_days=7`)/ 重複 → 409 `source_already_exists`(`details.status=active`) |
| EP-04 | 200(`ratio_threshold_percent` 20→25 が反映)/ 存在しない → 404 `source_config_not_found` |
| EP-06 | 202(`job_id` 発行)/ **直後の 2 回目 → 409 `lock_held`**(`details.options_applied=false`・`requested`・`existing_job`・`lock_state=held_crawl`)/ `{"rewrite_mode":true}` → 202、実行結果で `rewrite_mode=true`・`updated_count=4`(Crawler へ正しく届く)/ 存在しない → 404 / `{"force_delete":"true"}` → 400 `type`(Crawler に送られない)/ GET → 405 |
| EP-09 | `status`・`stalled=false`・`total` を確認。`unavailable={}` |
| EP-10 | `registration`(`enumerated_count=5`・`created_count=4`・`oversize_count=1`・`error_count=1`・`phase=final`)・`deletion`(`summary.status=deleted`・`confirmation=confirmed`・`current_state=available`・`fetched_at`・`settings`)・`latest_for_source=true`・`rerunnable=false`(`not_failed`) |
| EP-11 | oversize(`big.md`。`size=null`は B 6.1 の「分かる場合だけ。なければ null」どおり)・extract_failed(`data.xyz`)・skipped/summary_pending(0 件)。`tab_counts`・`document_count=4` が整合。不正な `tab`・`sort` → 400 に両方の違反を同時に返す |
| EP-07 | 終端ジョブ → 409 `job_already_finished`(`details.status=succeeded`)/ 存在しない → 404 `job_not_found` / `%2E%2E`・`a%3Fb%23c`・生の `.`・`..`(`--path-as-is`)→ いずれも 404 `job_not_found`(**AAPI-U-12 を実機で確認**)/ 制御文字 → 400 `format` / `%2F` → 404 `not_found`(Starlette の仕様差。既知) |
| EP-08 | ロックなし → 200 `released=false`(B に 404 の規定はなく、存在しない `source_id` も同じ。Crawler の仕様どおり) |
| EP-05 | 202(`force_delete=null`・`rewrite_mode=null`。B 3.5)→ ジョブは succeeded、EP-01 から消え、EP-02 は 404 |
| EP-10 の `.` を含む ID | `source_id=a.b` は 404 `source_config_not_found`(ハンドラまで届く。**AAA-U-4 を実機で確認**) |

### 障害系

- **Crawler 停止**(専用スタックのコンテナのみ): EP-04・05・06・08 がすべて 503 `crawler_unreachable`(`retryable=true`)。EP-13 は crawler が `abnormal`/`connection_refused`、indexer・opensearch は normal。EP-01・02・09・11・12 は影響を受けず 200。復旧後(`start`・healthy)、EP-06 が 202 に戻る
- **OpenSearch 停止**: EP-01・10・12 が 503 `unavailable`(`retryable=true`)。EP-13 は opensearch が `abnormal`/`connection_refused`(**AAPI-U-11: 接続拒否時の `ConnectionError.info` の分類が実機で期待どおり**)、crawler・indexer・api は normal。EP-14・`/healthz` は影響なし。EP-13 は 0.27 秒で応答。EP-06 は Crawler 自身が 503 `unavailable` を返し 503 `crawler_unavailable`。復旧後 EP-01 が 200 に戻る
- **手順上のミス(結果には影響なし)**: 最初の Crawler 停止は、シェル変数の展開に失敗して停止コマンドが実行されず、Crawler は動いたままだった(その間の出力は障害時の結果ではなく通常動作)。気づいたため関数(`dc()`)に直して障害系をやり直し、上記の結果を得た

### OpenAPI

- `OPENAPI_ENABLED=true` の実機の `/api/admin/v1/openapi.json`(200)は、`env -i`(環境変数なし)で `openapi_export` が書き出した JSON と**完全一致**(14 操作・12 パス)
- `/docs`・`/redoc`・外側の `/openapi.json`・`/api/admin/v1/docs`・`/api/admin/v1/redoc` は 404
- 既定(`OPENAPI_ENABLED` なし)の 404 は、単体テスト(`tests/server/test_admin_openapi.py`)で確認済み。スモークでは `true` の公開のみ実機確認

### ログ

- api のログ 99 行(INFO 91、WARNING 8)。アクセスログは**ルートのテンプレート表記**(例 `GET /api/admin/v1/jobs/{job_id} 503 3.7ms`)、ルート外は `GET - 404`
- `smoke`・`job-2026`・`connector_config`・`/data/documents`・`include_patterns`・`big.md`・`password`・`Traceback` はログに**出ていない**
- WARNING は固定語彙のみ: `crawler call failed: operation=start_crawl error_code=crawler_unreachable crawler_status=None crawler_code=None reason=connection_failed`(R-C で追加した失敗理由のログ)、`opensearch read failed: operation=sources.list_all target=store kind=unavailable error=ConnectionError status=n/a`

### Docker

- `docker build -q -t loreley-api-smoke:test apps/api`: 成功(キャッシュで約 8 秒)
- 必須環境変数なしの `docker run`: 終了コード 1。`ConfigError: invalid settings: opensearch_url: missing; crawler_url: missing; indexer_url: missing`(項目名と種別だけ)
- `LORELEY_API_PORT=abc` と、ユーザー名・パスワードを含む URL: `port: int_parsing; opensearch_url: url_userinfo`。**パスワード・ユーザー名・URL の値は出力に出ない**
- 必須 3 変数を指定すると起動し(`0.0.0.0:8080`)、コンテナ内から `/healthz` が応答。プロセスは非 root(uid 10001)
- 起動失敗時は、`ConfigError` のトレースバックが標準エラーに出る(メッセージは項目名だけで、値は含まない)

### 後始末

- api 停止(SIGINT で正常終了)。`docker compose -p loreley-admin-smoke ... down -v --remove-orphans --rmi local` でコンテナ・ボリューム・ネットワークを削除。`--rmi local` で消えなかった自作イメージ(`loreley-admin-smoke_crawler`・`loreley-admin-smoke_indexer`)と `loreley-api-smoke:test` を削除。実行用の `docker run` コンテナも削除
- 他プロジェクトのコンテナ(`opensearch-opensearch-1`)・イメージ(`loreley-it_*`・`fess-opensearch`・`compose_indexer`)は無傷。ポートは解放済み。作業ツリーはクリーン

## 実機で確認できた実装時確認事項

- **AAPI-U-11**: 接続拒否時の `opensearch-py` の例外 → EP-13 の `abnormal`/`connection_refused`(確認済み)
- **AAPI-U-12**: EP-07 の `job_id`(`.`・`..`・`%2E`・`?`・`#`・空白)が全文字エンコードされて Crawler に届き 404 `job_not_found`(P5a の実機確認に続き、api 経由でも確認)
- **AAA-U-4**: `source_id` の `.`(`a.b`)がハンドラまで届く
- **AAA-U-1〜3(クエリの意味)**: 部分的に確認。R-3(`last_crawl`・`last_completed_at`)、R-9(`document_count`)、`tab_counts`、一覧の `total`、EP-10 の `latest_for_source` が実データで期待どおり。並べ替えの順序・`terms` の `size`・`top_hits` は、データが 1 ソース・数ジョブのため十分には確認できていない
- **クロール完了後の `deletion`**: `confirmation=confirmed`・`current_state=available`(クロールの削除結果の読み取り)が実データで取得できた

## 未確認(結合テストのタスクなどへ申し送り)

- **AAA-U-10**(期限後に残るスレッドの数と時間): 未実測
- **EP-07 で実行中のジョブを取り消す**、**EP-08 で実際にロックを解放する**、**EP-06 の `lock_in_use` の 409**、`stalled=true`、`lease_expired` などのロック状態: 実行中のジョブを意図的に作れず(クロールが約 3 秒で完了する)未確認。単体テスト(偽物・ローカル HTTP スタブ)では確認済み
- **EP-05・EP-06 の `force_delete=true`**: 未実行(削除の実機確認は `source_delete` のみ)
- **EP-12 の `relocating` の `node` 表記、複数ノード・複数シャードの `cat.*` の列**: 単一ノード・数索引のみで未確認
- **AAPI-U-7(`ids` クエリの `_id` と `document_id` の一致)**: `skipped` の行が 0 件で `existence` を実機で見られていない(`oversize`・`extract_failed` の行は `existence` を持たない仕様)
- **ページングの窓 10,000 の実データでの確認**、**OpenSearch の部分失敗(一部シャード障害)**: 未確認
- **`ClientDisconnect`(本文読み取り中の切断)**: 単体テストのみ

## 未対応事項・次にやること

- レビュー R-C(後半): 比較基準 `463a050`(R-C 前半の指摘対応)から HEAD(P7a・README・本スモークの記録を含む)まで。重点は OpenAPI の宣言(各 EP のステータスと B の突き合わせ)、`ClientDisconnect` の WARNING + 400 の判断、README の正確さ(HO-40・41、環境変数、起動例)、`servers` 固定の判断、tzdata
- その後 task-reviewer → PR
