# 0017 P8a: `api`(Admin API 6エンドポイント)・`GET /healthz`・`config.py` の完成

日付: 2026-11-14 / 実施: code-implementer / 記録・再検証: メインエージェント
フェーズ開始時点の HEAD: `061dc7b196f67a689e0d834eb676ce356d6cdb34`(`apps/crawler/` は未コミット)。P8 は 8a・8b に分けた。P7+P8 のレビューは 8b 完了後にまとめて実施(0002 §6)。

## 0. メインの依頼文の訂正(重要)

メインの 8a への依頼文は「メンテナンス中の設定更新は409(CAPI-P-4・7・9、案どおり)」と書いたが、**設計書(crawler-api v0.3 の CAPI-P-17)は「メンテナンスフラグを確認するのは起動系(4.1・4.6)だけ。取り消し・ロック解放・設定の登録・更新では確認しない」としており、依頼文のほうが誤り**だった。実装担当は設計書どおり実装した(設定の更新・取り消し・ロック解放はメンテナンスフラグの影響を受けない。受付の409は `jobs` の結果のまま)。テストで固定済み。訂正の必要はない(実装が正)。

## 1. 検証結果(メインが再実行、`apps/crawler`)

```
$ uv run pytest -q           -> 3153 passed, 3 skipped in 25.63s(P7 後 2769 → +384(報告は +429。tests 追加分の差は数え方))
$ uv run ruff check          -> All checks passed!
$ uv run ruff format --check -> 264 files already formatted
$ uv lock --check            -> Resolved 39 packages
```

`git status` は `apps/crawler/` のみ。実装担当は3回連続成功を確認。`test_job_start.py` を5回連続で実行して成功(スレッドを使う1件(同時2リクエスト)に `Barrier` と join のタイムアウト5秒、スリープなし)。変異確認(scratchpad の別コピー、35件)は34件検出、1件生存は等価変異(`describe_settings_errors` の `include_input=False` を True に変えても、出力に使うのが `loc` と `type` だけで出力が変わらない。実質の漏れ防止は、元の例外を連鎖させないことと、センチネルのテストで確認)。

## 2. 実装内容(`apps/crawler/src/loreley_crawler/`)

- `api/`(新規): `__init__.py`(`create_app`・`ApiDependencies`)、`app.py`(FastAPI の組み立て。docs/openapi は公開しない)、`dependencies.py`(`ApiDependencies`: `job_admission`・`job_cancellation`・`lock_release`・`source_store`・`connector_registry`・`retrier`)、`routes.py`(6エンドポイントと `/healthz`。ハンドラは同期 `def`)、`request_parsing.py`(JSON の厳密な検証 `required`・`read_only`・`unknown_field`・型、パス検証 `source_id`・`job_id`、Connector の検証呼び出し)、`responses.py`(結果型→HTTP の写像。`match` で全バリアントを列挙し、未対応は `TypeError`(500))、`errors.py`(共通エラー形式、例外ハンドラ、pydantic の検証エラーを位置と型だけに変換)、`middleware.py`(アクセスログはルートのテンプレートのみ、想定外の例外を500にして再送出しない)
- `config.py`(変更): 既存の純粋関数はそのまま。追加: `Settings`(pydantic-settings)・`CrawlerConfig`・`load_config`・`build_config`・`ConfigError`・`check_heartbeat_timing`・`TimingViolation`・`warn_about_unchecked_indexer_limits`・`describe_settings_errors`
- `sources/__init__.py`: `ConnectorRegistry`・`ConnectorError`・`ErrorCategory` を再公開(R4 で `api` は `connectors` を import できないため。§3-1)。`sources/records.py`: `MalformedSourceRecord` に `connector_type: str | None = None` を追加(§3-2)。`jobs/__init__.py`: `HeartbeatSettings` を再公開
- tests: `tests/api/`(`support.py`・`conftest.py`・`test_job_start.py`・`test_cancel.py`・`test_lock_release.py`・`test_source_register.py`・`test_source_update.py`・`test_request_validation.py`・`test_errors.py`・`test_result_mapping.py`・`test_healthz.py`・`test_logging.py`)、`tests/test_config_loading.py`。`tests/architecture/dependency_rules.py` は `config` 行のコメントのみ修正(許可表の中身は無変更)、`test_dependency_rules.py` の自己テストを修正(`config` が各モジュールを import するようになり、`common` に違反ファイルを足すと循環にもなる。循環検査は `common` の違反ファイルを除いた木で行う)

## 3. 判断・設計上の理由

### 3-1. R4 と `ConnectorError`
`api` は `connectors` を import できない(R4)が、`validate_connector_config` は `ConnectorError` を送出し `create_app` は `ConnectorRegistry` を受ける。許可表は変えず、`sources/__init__.py` が再公開し `api` はそこから import する。

### 3-2. 更新(PUT)の `connector_config` 検証と `MalformedSourceRecord` の拡張
crawler-api 4.4.1 は更新でも `validate_config` を求める。`connector_type` は登録後に変わらず、保存済みの値が要る。`api` が `SourceStore.fetch` を1回読み(`ApiDependencies.retrier` でリトライ)、保存済みの `connector_type` で検証してから `update()` を呼ぶ。設定がない・`connector_type` が読めない場合は検証せず、`update()` の結果(404・409・500)に任せる(404・409 の判断は `sources` に残り `api` では行わない)。形式不正だが `status` が読める記録を更新で修復する P4 の挙動を残すため、`MalformedSourceRecord` に `connector_type`(Connector の種別名であり設定の値ではない)を足した。**設計書にない(要確認)**: 更新で `api` が `sources.fetch` を1回余分に呼ぶ点(crawler-api 4.4 に追記の要否)

### 3-3. その他
- `ApiDependencies` に `Clock` を入れなかった(`api` は時計を使わない。日時の書式化は `common.timestamps.format_instant`)
- JSON: 本文は `json.loads` で読み手書きで検証(`reason` の語彙が pydantic の検証エラーと対応しないため)。`NaN`・`Infinity`・`1e999` は `ratio_threshold` では `type`、`connector_config` 内では `connector_config: type`。`connector_config` 内の孤立サロゲートは `connector_config: format`。未知の項目名は `format_display_text`(切り詰め100文字・制御文字エスケープ)を通して応答に載せる。本文が JSON でない場合は `invalid_request`(`details` なし)、オブジェクトでない場合は `details.errors=[{field:"body",reason:"type"}]`(`"body"` は設計書にない案)。複数の違反は、必須・読み取り専用・未知(本文の順)、値の違反(項目の定義順)の順に全部返す。`config_invalid` の `message` は Connector の説明文を `format_display_text(max_chars=512)` を通して返す(設計書は「そのまま」)。クロール起動以外の POST/DELETE は本文を読まない。受け付ける本文の大きさの上限は設けていない(設計書に規定なし)
- エラー応答: 503=`StoreUnavailableError`(`retryable=true`)、500=`StoreUnexpectedResponseError`・想定外の例外・`connector_internal_error`(`message` は固定文)。ログは例外のクラス名・固定の理由名・最内フレームの `ファイル:行 関数名` だけ(トレースバックは出さない)。未定義のパス・メソッドは `not_found`・`method_not_allowed`・`http_error`(Indexer と同形式)。`ValueError` は400にしない(バグを隠さないため500)
- `/healthz`: `{"status":"ok"}`。`jobs`・`sources` を呼ばない。「回復完了前は応答しない」は、アプリを回復の後に作る構造で実現し、`api` に受付可否のフラグや ready ミドルウェアを持たせていない(8b)。6 API + `/healthz` 以外のルートがないことを OpenAPI のパス定義で確認するテスト
- 案の局所化: メンテナンス中の設定更新は409にしない(§0)、`source_id` の文字種は `sources/validation.py` の定数1か所、`/healthz` のパス・形式は `routes.py` の1関数

### 3-4. `config.py` の設計
- `Settings` の環境変数名は、フィールド名の大文字に `LORELEY_CRAWLER_` を付けたもの。既定値は各モジュールの設定 dataclass のクラス属性を参照(二重管理せず architecture 11章の仮値と自動で一致)。項目を足して環境変数を足し忘れたらテストが失敗(`test_every_module_setting_field_has_an_environment_variable`)
- `load_config()` は `ValidationError` を、環境変数名と `type` だけの `ConfigError` にする(値・秘密を含まない。元の例外は連鎖させず `__context__`・`__cause__` は None)。各 dataclass の `ValueError` は固定文の `ConfigError("invalid <section> settings: ...")`
- 整合性検査: `check_size_limits`(P1)、`check_heartbeat_timing`(新規。ハートビートの停止の待ち ≥ 専用クライアントのタイムアウトの2倍。ちょうど2倍は許可)、索引名の相違(sources と jobs が同じなら起動失敗。設計書にない追加検査だが記録 ID の衝突で黙って壊れるのを防ぐ最小の安全策)。違反は全部まとめて `startup consistency check failed: ...`(項目名・数値のみ)。関係式(再試行間隔<更新間隔<リース)は `HeartbeatSettings` の構築時検査が `ConfigError`
- 新規の仮値: HTTP 待ち受けの既定 `127.0.0.1:8001`(Indexer の8000とホスト上で衝突しない)、ジッタ割合 0.2(設計書は「ジッタあり」のみ)、`log_level` 既定 INFO
- CM-U-9 仮置き(a): Indexer の上限は `LORELEY_CRAWLER_INDEXER_<名前>`(`MAX_RAW_BYTES` など6つ。Crawler 自身の `LORELEY_CRAWLER_MAX_RAW_BYTES`(原本1件の上限)と取り違えないよう `INDEXER_` を挟んだ)。未設定の項目は検査を省略し `CrawlerConfig.unchecked_indexer_limits` に名前を入れる。警告は `warn_about_unchecked_indexer_limits(config)` が出す(ログ設定の後に呼ぶ)

## 4. 設計書との食い違い・不明点

1. crawler-api 4.4(更新)は、`connector_config` の検証に使う `connector_type` を `api` がどう得るかを書いていない → §3-2 の方式で実装
2. module 4.1 / R4: `ConnectorRegistry`・`ConnectorError` を `sources` の再公開経由にした
3. 本文が JSON でない場合の `details`、`"body"` という項目名、`config_invalid` の `message` の安全網(512文字)は設計書にない詳細
4. JSON の扱い(§3-3)を決めた
5. 起動時の受付可否は「アプリを回復後に作る」構造に任せ `api` に状態を持たせていない。**8b で起動順テストを置く**

## 5. 環境変数一覧(README 用。接頭辞 `LORELEY_CRAWLER_` 省略。必須は3つ)

| 名前 | 既定値 | 意味 |
| --- | --- | --- |
| `OWNER` | 必須 | Crawler の安定した ID(256バイト以内・制御文字なし)。未設定は起動失敗 |
| `OPENSEARCH_URL` | 必須 | Store 層の OpenSearch の URL(認証情報の埋め込み不可) |
| `INDEXER_URL` | 必須 | Indexer の URL(パス・クエリなし) |
| `HTTP_HOST` / `HTTP_PORT` | `127.0.0.1` / `8001` | 待ち受け。コンテナでは 0.0.0.0 |
| `LOG_LEVEL` | `INFO` | `DEBUG`・`INFO`・`WARNING`・`ERROR`(小文字可) |
| `OPENSEARCH_USERNAME` / `OPENSEARCH_PASSWORD` | 未設定 | 認証(両方必須または両方なし)。パスワードは `SecretStr` |
| `OPENSEARCH_VERIFY_CERTS` | `true` | TLS 証明書の検証 |
| `OPENSEARCH_CA_CERTS_PATH` | 未設定 | CA 証明書のパス |
| `OS_STORE_REQUEST_TIMEOUT_SECONDS` | `30.0` | Store 層の通常のタイムアウト |
| `OS_HEARTBEAT_REQUEST_TIMEOUT_SECONDS` | `10.0` | ハートビート専用クライアントのタイムアウト |
| `SOURCES_INDEX_NAME` / `JOBS_INDEX_NAME` | `loreley-sources` / `loreley-jobs` | 索引名。2つは別の名前。jobs は Indexer の `LORELEY_INDEXER_JOBS_INDEX_NAME` と同じ値にする |
| `SCAN_PAGE_SIZE` / `SCAN_PIT_KEEP_ALIVE_SECONDS` / `SCAN_REQUEST_TIMEOUT_SECONDS` / `BULK_DELETE_BATCH_SIZE` | `1000` / `60` / `60.0` / `1000` | 全件走査・バルク削除 |
| `INDEXER_CONNECT_TIMEOUT_SECONDS` | `10.0` | Indexer への接続のタイムアウト |
| `INDEXER_START_TIMEOUT_SECONDS` / `INDEXER_FINISH_TIMEOUT_SECONDS` / `INDEXER_STATUS_TIMEOUT_SECONDS` | `30.0` | 開始通知・終了通知・Status |
| `INDEXER_LAST_SEEN_TIMEOUT_SECONDS` | `60.0` | `last-seen` |
| `INDEXER_REGISTER_BATCH_TIMEOUT_SECONDS` | `300.0` | バッチ登録 |
| `INDEXER_DISCARD_DELETIONS_TIMEOUT_SECONDS` | `600.0` | ソース削除1 |
| `INDEXER_DELETE_DOCUMENTS_TIMEOUT_SECONDS` | `4200.0` | ソース削除2 |
| `INDEXER_DELETE_DELETION_RECORDS_TIMEOUT_SECONDS` | `60.0` | ソース削除3 |
| `INDEXER_MAX_RAW_BYTES` / `INDEXER_MAX_BATCH_DOCUMENTS` / `INDEXER_MAX_BATCH_BYTES` / `INDEXER_MAX_REQUEST_BODY_BYTES` / `INDEXER_MAX_LAST_SEEN_IDS` / `INDEXER_SKIP_OVERSIZE_ID_LIMIT` | 未設定(警告して検査省略) | Indexer の上限(`LORELEY_INDEXER_` を除いた名前に対応)。compose で Indexer と同じ値を渡す。超過は起動失敗 |
| `RETRY_MAX_ATTEMPTS` / `RETRY_INITIAL_BACKOFF_SECONDS` / `RETRY_BACKOFF_MULTIPLIER` / `RETRY_MAX_BACKOFF_SECONDS` / `RETRY_JITTER_RATIO` | `3` / `1.0` / `2.0` / `30.0` / `0.2` | リトライ。ジッタ0.2は仮値 |
| `RUNNER_SCAN_INTERVAL_SECONDS` | `5.0` | Job Runner の走査間隔 |
| `ADMITTING_LOCK_GRACE_SECONDS` | `60.0` | 受付途中とみなすロックの長さ |
| `HEARTBEAT_LEASE_SECONDS` / `HEARTBEAT_INTERVAL_SECONDS` / `HEARTBEAT_RETRY_INTERVAL_SECONDS` / `HEARTBEAT_STOP_TIMEOUT_SECONDS` | `300` / `100` / `10` / `30`(秒) | 再試行間隔<更新間隔<リース。停止の待ち ≥ `OS_HEARTBEAT_REQUEST_TIMEOUT_SECONDS` の2倍 |
| `SCHEDULER_CHECK_INTERVAL_SECONDS` | `30.0` | Scheduler の判定周期 |
| `CHUNK_SIZE` / `LAST_SEEN_MAX_IDS` / `BATCH_MAX_DOCUMENTS` / `BATCH_MAX_RAW_BYTES` | `500` / `500` / `20` / `33554432` | チャンク・`last-seen`・バッチ。後ろ3つは Indexer 上限の検査対象 |
| `CONSECUTIVE_SKIP_LIMIT` / `INVALID_ID_EXAMPLE_LIMIT` | `20` / `20` | 連続スキップの打ち切り・識別子エラーの例の件数 |
| `FINISH_ID_LIST_WARNING_THRESHOLD` | `8000` | 終了通知の ID 一覧の警告閾値。Indexer 上限の検査対象 |
| `POLLING_INTERVAL_SECONDS` / `POLLING_TIMEOUT_SECONDS` / `POLLING_MAX_CONSECUTIVE_FAILURES` | `5.0` / `1800.0` / `3` | 削除結果のポーリング |
| `WARNINGS_MAX_ENTRIES` / `PREVIOUS_CRAWL_LOOKUP_JOBS` | `20` / `10` | `warnings` の件数上限・過去ジョブの件数 |
| `MAX_RAW_BYTES` | `20971520` | Crawler 自身の原本1件の上限(Indexer の上限とは別。`INDEXER_MAX_RAW_BYTES` と取り違えない) |
| `MAX_ENUMERATED_DOCUMENTS` / `DISPLAY_MAX_CHARS` | `500000` / `200` | 列挙の上限・表示の長さ |
| `FS_MAX_PATTERNS` / `FS_MAX_PATTERN_BYTES` / `FS_READ_CHUNK_BYTES` / `FS_MESSAGE_PATH_MAX_CHARS` | `100` / `1024` / `1048576` / `200` | FS Connector |

## 6. 8b(`main.py`)への申し送り

- 起動順の先頭: (1) `config = load_config()`(`ConfigError` は捕捉せず異常終了)、(2) `configure_logging(level=config.log_level, secrets=config.log_secrets)`、(3) `warn_about_unchecked_indexer_limits(config)`、(4) OpenSearch 接続(Store 用・ハートビート専用の2クライアント。`config.opensearch` で `create_store_client`・`create_heartbeat_client`)、(5) `StartupRecovery.run()` → `JobRunner.start()` → `Scheduler.start()` → アプリ作成 → uvicorn
- `CrawlerConfig` の項目: `http_host`・`http_port`・`log_level`、`log_secrets`(repr 非表示)、`opensearch`(`OpenSearchConnectionConfig`)、`sources_index_name`・`jobs_index_name`、`repository`(`RepositorySettings`)、`indexer`(`IndexerClientConfig`)、`retry_policy`(`RetryPolicy`)、`jobs`(`JobsSettings`。`owner` と `heartbeat` を含む)、`scheduler`・`crawl`(`CrawlSettings`)・`documents`(`DocumentsSettings`)、`file_system`(`FileSystemSettings`。`create_connector_registry(fs_settings=config.file_system)` に渡す)、`unchecked_indexer_limits`
- `create_app(ApiDependencies(job_admission, job_cancellation, lock_release, source_store, connector_registry, retrier))`。`retrier` は確認点なしの `Retrier(config.retry_policy)`(受付・取り消し・解放・回復と共有してよい)。`JobAdmission` などは HTTP ハンドラのスレッドから呼ばれ、Scheduler も同じ `JobAdmission` を共有する(0016 §5)。uvicorn は `host=config.http_host`・`port=config.http_port`・`log_config=None`・`access_log=False`・workers=1(アクセスログは `api/middleware.py` が出す)
- **アプリは回復の完了後に作ること**。`/healthz` が回復前に応答しないことの起動順テストは 8b の範囲。R7 の「`main` が作る Repository は3つ」の検査、全体の依存ルール・全ログのセンチネル検査も 8b。`SourceStore` は `api` と `source_delete` で同じインスタンスを共有してよい。組み立ての詳細は 0011 §6・0013 §7・0014 §6・0016 §5

## 7. 未対応事項・提案

- 提案: ハートビート専用クライアントのタイムアウトが再試行間隔以内か(connection.py のコメント「再試行間隔とリース時間に収まる短さ」)の検査は、設計書に式がないため入れていない
- 提案: リクエスト本文の大きさの上限は、設計書に規定がないため設けていない(必要なら設計書の改版が先)
- 実機でしか確認できないもの: uvicorn 上での実際のスレッドプールの挙動、`/healthz` の `healthy` 化(P9・統合テストへ持ち越し)

## 8. 設計書の改版依頼リスト(提案。P8a 分)

1. crawler-api 4.4.3: 更新では、保存済みの `connector_type` で `validate_config` を行う(`api` が保存済み設定を1回読む)。設定がない・種別が読めない場合は検証せず、404・409・500 は `sources` の結果に任せる
2. module 4.1・R4: `api` が使う `ConnectorRegistry`・`ConnectorError` は `sources` の入口の再公開で、`api` は `connectors` を直接 import しない。`MalformedSourceRecord` に `connector_type` を持たせる
3. crawler-api 3.2・3.3: 本文が JSON でない場合は `details` なし、オブジェクトでない場合は `field="body"` の `type`/`NaN` 等の有限でない数値(`connector_config` 内を含む)は `type`、孤立サロゲートは `format`/未知の項目名は切り詰め・エスケープして返す
4. crawler-api 3.3: `config_invalid` の `message` は Connector の説明文を、切り詰めと制御文字のエスケープを通して返す
5. module 3章・architecture 10章: 環境変数名の規則(フィールド名の大文字+`LORELEY_CRAWLER_`)と一覧。Indexer の上限は `LORELEY_CRAWLER_INDEXER_<名前>`(CM-U-9 の仮置き(a))
6. architecture 11章: 次の仮値を採用値として追記: HTTP 待ち受け 127.0.0.1:8001、ジッタ割合 0.2、Store 層タイムアウト30秒・ハートビート専用10秒、停止の待ち30秒(≥ 専用タイムアウトの2倍)
7. architecture 10章・module 3章: 整合性検査に追記: ハートビートの停止の待ち ≥ 専用クライアントのタイムアウトの2倍/関係式(再試行間隔<更新間隔<リース)/`loreley-sources` と `loreley-jobs` の索引名が異なること
8. crawler-api 4.7: `/healthz` を含め、アクセスログは「メソッド・ルートのテンプレート・ステータス・所要時間」だけを出す。ヘルスチェックの間隔によってはログが増える点を注記

## 9. 次のアクション

8b(`main.py`・組み立て・起動順・停止順、R7 の「Repository 3つ」の検査、全体の依存ルール検査、全ログ・全エラー応答のセンチネル検査、起動順(`/healthz` が回復前に応答しないこと)のテスト)を `code-implementer` に依頼する。その後 P7+P8 を code-reviewer・test-reviewer で並列レビュー(重点: メンテナンスフラグの範囲(0016 §3)、起動順・停止順、ログ流出、`api` の更新時の `connector_type` の読み取り(§3-2))。
