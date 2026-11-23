# 0004 P1: 共通部品と admin の骨格

日付: 2026-11-24

## 実施内容

`code-implementer` が P1 を実装。メインエージェントが検証を再実行して確認した。

## 検証(メインエージェントが再実行、`apps/api`)

- `uv run pytest`: 751 passed(P0 基準 310)
- `uv run ruff check`: All checks passed
- `uv run ruff format --check`: 83 files already formatted
- `uv lock --check`: OK
- 実装担当による実機確認: `.invalid` の URL で `python -m loreley_api.main` 起動 → `/healthz` 200、`/api/admin/v1/nope` は JSON 404 + `cache-control: no-store`、Ctrl-C で正常停止

## 変更ファイル(`apps/api/` 配下)

- 依存: `pyproject.toml`、`uv.lock`(anyio 4.16.0、opensearch-py 3.2.0、urllib3 2.8.0。crawler と同版)
- common 新規: `clock.py`・`timestamps.py`・`results.py`・`concurrency.py`・`urls.py`・`probe_outcome.py`・`http/body.py`。変更: `logging_setup.py`
- `config.py`(C 7.2/7.3 の全変数・検証、`ApiConfig`・`load_config()`)、`main.py`(`SubAppMount("/api/admin/v1")`、外側 lifespan で close)
- infrastructure(設定型のみ): `opensearch/config.py`・`crawler_client/config.py`・`probes/config.py`
- admin: `app.py`・`dependencies.py`・`settings.py`・`base/{codes,errors,constants}.py`・`failures/{reasons,unavailable}.py`・`routers/{__init__,request_input}.py`
- tests: `fakes/{clock,inline_runner,behavior}.py`、`api_config.py`、`conftest.py`、`common/`・`admin/` の新規テスト、`test_config.py` 書き換え、`test_main.py`・`architecture/*` 更新

## 判断・設計上の理由(実装時に決めた事項)

- **AAM-U-1(anyio 4.16.0)**: `run` は `abandon_on_cancel=False`(キャンセル後もスレッド終了まで戻らない)、`run_all` は `abandon_on_cancel=True`(期限超過を放棄して戻る)。放棄時にトークンは返る。枠待ちの呼び出しは `Abandoned` になり開始しない。テストで固定
- **AAM-U-8**: `run_all(category, calls, deadline_seconds) -> list[T | Abandoned]`。結果は入力と同順、例外は他が終わってから最初の例外をそのまま送出(ExceptionGroup にしない)。区分上限は既定 opensearch 16 / crawler 4 / probe 8、未知の区分は `ValueError`
- **AAM-P-28**: `uvicorn.run` に `timeout_graceful_shutdown`・`lifespan` を渡さない(テストで固定)
- **AAM-U-3**: `exclusive`・`config_invalid` は `Reason` enum に持たせ、`FieldViolation` で明示付与。`handlers.reason_of` の対応表は未変更
- **`ClientDisconnect`**: 本文読み取り中に切断すると ERROR ログ + 500 のアクセスログになることを確認。挙動は変更せず、ログ水準を下げるかは P5 以降で判断
- **URL の検証**: `CRAWLER_URL`・`INDEXER_URL` はパス(空か `/` のみ)に加えクエリも拒否。`scheme://netloc` で保持し `CrawlerClientConfig.base_url` と `AdminSettings` の両方に入れる
- **空文字の扱い**: 未設定扱いは C に明記のある `*_HEALTH_URL`・`DASHBOARDS_URL`・`CRON_TIMEZONE` のみ
- **Depends 検査(AAM-U-9)**: `Depends`/`Security` の引数を関数定義に名前で結び付けて検査。同期 `def`・ラムダは違反。限界(クラス渡し・別名登録・同名別関数)はファイル冒頭に明記
- **R5**: `EXTERNAL_LIBRARY_OWNERS` を接頭辞(最長一致)キーにし、ファイル単位の所有者を許容。`urllib3.exceptions` は `crawler_client`・`probes`・`opensearch/{failure,health_probe}.py` に許可。`anyio` は `common/concurrency.py` のみ
- **P7 へ送り**: `create_admin_app` は `openapi_url=None` 固定。`OPENAPI_ENABLED` の公開配線は P7

## 満たした C 11章の観点

13(設定: 完全)/ 14(並行性: concurrency 部分。server の「Crawler 遅延でも他が応答」は P7)/ 8(import 部分のみ。AST の R8 は P2 以降)/ 11(CORS: R10 の対象に admin 追加)/ 12(部分)/ 15(部分。`OPENAPI_ENABLED=true` は P7)

## 設計書との食い違い(申し送り。設計書は未変更)

1. **D 4.3 `create_admin_router(deps)`**: D 6章の許可表と矛盾(deps の型が `admin/dependencies.py` にあり、`admin.routers` が import すると admin → routers → admin の循環)。実装は `create_admin_router()` を引数なしとし、EP 追加時にサービスを個別に渡す。`create_admin_app(deps)` の `deps` は P1 では未使用
2. **D 4.7 `AdminApiError(code, status, retryable, details)`**: 実装は `AdminApiError(code, status_code, *, retryable=False, details=None)`。`message` は code ごとの固定文を内部表から引く。P1 の生成関数は `invalid_request`・`unavailable`・`source_config_not_found`・`job_not_found` のみ。Crawler 連携の code は該当 EP で追加
3. **D 3章 `probes/config.py`・`AdminSettings`**: 設計書に中身の記述なし。`HttpProbeConfig` は確認 1 件のタイムアウトのみ。`AdminSettings` は C 7.2 の Admin 固有項目 + EP-13 用 `crawler_url`・`indexer_url`・`probe_timeout_seconds`
4. **D 4.1 `AdminDependencies` の組み立て関数**: P1 では `main` が直接生成。サービスが増えた時点で関数化

## 未対応事項・次にやること

- README は未更新(P7)。必須環境変数が増えたため、現状の Docker 起動例は `OPENSEARCH_URL`・`CRAWLER_URL`・`INDEXER_URL` なしでは起動失敗(P7 で更新)
- `tzdata` は `opensearch-py` → `python-dateutil` 経由の間接依存でロック入り。直接依存化は任意(P7 で判断)
- R7 拡張(`derivation` が pydantic・時計・乱数・環境変数を import しない検査)は P3 で追加
- `InlineRunner`・`FixedClock`・`FakeBehavior` は P3 以降で使用
- 次: P2(`infrastructure/opensearch` の読み取り層)
