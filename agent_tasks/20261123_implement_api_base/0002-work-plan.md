# 0002 作業プラン: API 基盤(apps/api)の実装

日付: 2026-11-23
状態: **ユーザー承認待ち**(planner 作成。2.2〜2.4 の推奨案は承認をもって確定)

## 1. 目的とゴール

`apps/api` に、将来の admin・search・mcp を「機能モジュール」として足せる共通の土台を作る。ヘルスチェックはその最初の機能モジュールとして実装し、基盤の口に組み込む。

### 受け入れ基準
- [ ] `cd apps/api && uv run pytest`、`uv run ruff check`、`uv run ruff format --check`、`uv lock --check` がすべて通る
- [ ] `uv run python -m loreley_api.main` で起動し、`GET /healthz` が 200 `{"status":"ok"}` を返す
- [ ] 未知のパスは A 5.2 形式の JSON 404 `not_found`、未定義メソッドは 405 `method_not_allowed`
- [ ] ヘルスチェックは独立した機能パッケージ `loreley_api/health` にある。`server` は `health` を import しない(`tests/architecture` で機械検査)
- [ ] ダミーのサブアプリを基盤の口(マウント)に載せたテストが通る(統一エラー形式、アクセスログが1回だけ、`no-store`、500 変換して再送出しない)
- [ ] `docker build -t loreley-api apps/api` が成功し、コンテナの HEALTHCHECK が `healthy` になる
- [ ] `apps/api/README.md` に起動方法・環境変数・テスト実行が書かれている
- [ ] 設計書(A〜D)は変更していない。設計書との差を作業記録に申し送っている

## 2. 確定事項・前提

### 2.1 0001 の確定事項(引き継ぎ)
- 基盤の範囲: main/config、server(`create_app` と機能パッケージを載せる口)、common(統一エラー形式・アクセスログ・`no-store`・ログ設定)、`tests/architecture`
- 設定は `HOST`/`PORT`/`LOG_LEVEL` の3つだけ
- 含めない: admin、infrastructure、OpenSearch/Crawler 関連設定、`/admin/` 静的配信、OpenAPI の公開と書き出し、`BlockingRunner`、本文上限(1 MiB)
- ヘルスチェックは独立した機能モジュールとして実装(Q2)
- Dockerfile は Indexer の流儀(固定ベースイメージ・マルチステージ・非root・HEALTHCHECK)。Node ステージなし。README は最小限。compose・CI・scripts は変更しない(Q3)
- 技術スタック: Python `>=3.12,<3.13`、`fastapi>=0.143.2,<1`、`uvicorn>=0.32,<1`(単一プロセス)、`pydantic>=2.9,<3`、`pydantic-settings>=2.6,<3`、dev は `httpx2>=2.16,<3`・`pytest>=8.3`・`ruff>=0.8`、uv / hatchling。ruff・pytest の設定は Indexer と同じ(line-length 100、select E/F/I/UP/B/SIM/RUF、`pythonpath=["src","."]`)
- 設定クラスは `BaseSettings(env_prefix="LORELEY_API_", extra="ignore", frozen=True)`。既定 `HOST=127.0.0.1`、`PORT=8080`(1〜65535)、`LOG_LEVEL=INFO`(DEBUG/INFO/WARNING/ERROR。小文字も可)。不正値は起動時に失敗し、値はログに出さない
- 外側アプリは `docs_url`・`redoc_url`・`openapi_url` を `None`、`redirect_slashes` 無効。CORS なし
- uvicorn は `log_config=None`、`access_log=False`、ワーカー数指定なし。`lifespan` は Indexer と同じ方式(`lifespan="off"` にしない)
- 起動時に外部へ接続しない

### 2.2 ユーザーの意図と設計書の差の扱い(推奨案)
設計書 D 4.2 は `/healthz` を `server/health.py` に置く(D R3・R9 もこれを前提)。ユーザーの意図は「ヘルスチェックを独立した機能モジュールとして実装」。設計書は変えず、次で吸収する。

1. `/healthz` の URL・挙動・ログ水準は設計書どおり(A 2.2 / 6 / 5.5、BAPI-P-13)。変えるのはコードの置き場所だけ
2. `loreley_api/health/` を機能パッケージとして作る(admin・search と同じ層。`common` と `fastapi` だけに依存)。入口は `create_health_router() -> APIRouter` と `HEALTH_PATH = "/healthz"`
3. `server` は機能パッケージを import しない汎用の口だけを持つ
   - `create_app(*, routers=(), mounts=(), debug_access_log_paths=frozenset(), lifespan=None) -> FastAPI`
   - `routers`: 外側アプリに直接載せるルーター(`/healthz` のようなルート直下の機能)
   - `mounts`: `SubAppMount(prefix, app)` の列(admin のようなサブアプリ。BAPI-P-9)
   - 組み立ては `main` が行う
4. A 2.1 の「`/healthz` は外側アプリにある」は崩さない(health のルーターは外側アプリに `include_router`)
5. 作業記録に申し送る差分(設計書の追従改訂は別タスク):
   - D 3章・4.2: `server/health.py` を `health/` に変更。`server` の入口は `create_app(settings, admin_app)` ではなく汎用の `create_app(routers, mounts, …)`
   - D 6章 R3・許可表: `server` は機能パッケージを import しない(許可表より厳しい)。`main` に `health` を、機能パッケージの行に `health` を足した
   - D 6章 R9: ルート関数を `async def` にする対象が `server/health.py` から `health/` に移った
   - D 7.1: テストが `tests/server/` の health から `tests/health/` に移った
   - admin 実装時の注意: `main` で `SubAppMount("/api/admin/v1", create_admin_app(...))` を渡すだけ。マウントしたサブアプリの lifespan は Starlette では実行されないので、クライアントを閉じる処理は `create_app(lifespan=...)`(外側)に渡す。ロガー制限の対象(opensearch・urllib3 など)と外部ライブラリの所有者(D R5)はライブラリ導入時に足す

### 2.3 422 変換の範囲(推奨案)
- `RequestValidationError` を 400 `invalid_request`、`message="the request is invalid"`、`details.errors=[{field, reason}]` に変換。`input`・`ctx`・`msg` は使わない
- `field`: `loc` 先頭が `body`/`query`/`path`/`header`/`cookie` なら除く。残りをドット区切り、添字は `[n]`。何も残らなければ位置名を使う。各要素は A 5.2 の規則で整える(孤立サロゲート置換・制御文字エスケープ・100文字切り詰め)
- `reason` の最小表:

  | pydantic の type | reason |
  | --- | --- |
  | `missing` | `required` |
  | `extra_forbidden` | `unknown_field` |
  | `*_type`・`*_parsing` | `type` |
  | `greater_than(_equal)`・`less_than(_equal)`・`too_short`・`too_long`・`multiple_of` | `range` |
  | `literal_error`・`enum` | `unsupported` |
  | 上記以外 | `format` |

- `json_invalid` は 400 `invalid_request`、`details` なし(Crawler と同じ)
- 基盤に含めない: `exclusive`、Admin 固有の値(`config_invalid` 等)、本文上限、厳密 JSON のモデル設定(admin 実装時に足す)
- `details` は値がないとき省く

### 2.4 HEALTHCHECK の値(推奨案)
`--interval=15s --timeout=5s --start-period=10s --retries=3`。確認コマンドは Indexer と同形(標準ライブラリ urllib、プロキシ無効、ホスト `127.0.0.1` 固定、ポートは `LORELEY_API_PORT`(既定 8080)、`timeout=3`)。起動時に外部接続しないため `start-period` だけ短くする。

### 2.5 そのほかの前提
- **ApiError**: `common/http/errors.py` に `ApiError(status_code, code, message, retryable=False, details=None)` を置き、同形の応答に変換するハンドラを付ける(D 4.11 の部品)
- **HTTPException の写像**: 404 → `not_found`、405 → `method_not_allowed`、その他 → `http_error`(ステータスそのまま)。message は固定英語文。405 の `Allow` は残す
- **`no-store`**: パスが `/api/` で始まる応答だけ。`/healthz` とそれ以外には付けない(AAM-P-26)
- **アクセスログ**: ロガー `loreley_api.access`、形式 `METHOD テンプレート STATUS 所要ms`、未一致は `-`。`debug_access_log_paths` のテンプレートは DEBUG、他は INFO。想定外の例外は middleware で捕捉し、ERROR でクラス名と送出元(ファイル:行 関数名)だけを出し、500 `internal_error` を返して再送出しない
- **サブアプリへの設置(AAM-P-23)**: `server` がマウントするとき共通の例外ハンドラと middleware をサブアプリにも設置する。外側の middleware はマウントの担当パス(`prefix + "/"` で始まるもの)のアクセスログを出さず、サブアプリ側がマウント接頭辞を含む完全なテンプレートを出す。具体的な判定方法は P3 で確かめて決める(AAM-U-2)
- **ログ設定**: `configure_logging(level, stream=None)`。形式 `"%(asctime)s %(levelname)s %(name)s %(message)s"`、ルートのハンドラを置き換え、`uvicorn.access` を ERROR 以上に制限。秘密値マスクは入れない
- **設定エラー**: `load_settings()` が pydantic の `ValidationError` を「フィールド名: type」だけの `ConfigError` に置き換える(Indexer の `describe_settings_errors` と同じ。最大10件)。`except` の外で送出し連鎖させない。`main` は捕捉せず異常終了させる
- **`lifespan`**: `create_app` は任意の `lifespan` を受け取れる。基盤自身は閉じる資源がないので渡さない

## 3. 影響範囲

### 3.1 作成するファイル(すべて新規。既存ファイルの変更なし)

```text
apps/api/
├── .dockerignore
├── .gitignore
├── .python-version            # 3.12
├── Dockerfile
├── README.md
├── pyproject.toml
├── uv.lock
├── src/loreley_api/
│   ├── __init__.py
│   ├── main.py                # Composition Root
│   ├── config.py              # Settings・load_settings・ConfigError
│   ├── server/
│   │   ├── __init__.py        # create_app, SubAppMount
│   │   └── app.py
│   ├── health/                # 機能パッケージ
│   │   ├── __init__.py        # create_health_router, HEALTH_PATH
│   │   └── router.py          # GET /healthz(async def)
│   └── common/                # 葉
│       ├── __init__.py
│       ├── logging_setup.py
│       └── http/
│           ├── __init__.py    # install_common_http(app, *, debug_access_log_paths, skip_prefixes)
│           ├── errors.py
│           ├── handlers.py
│           └── middleware.py
└── tests/
    ├── __init__.py
    ├── log_records.py
    ├── architecture/{__init__,dependency_rules,test_dependency_rules,test_http_rules}.py
    ├── common/{__init__,test_logging_setup,test_logging_calls}.py
    ├── common/http/{__init__,test_errors,test_handlers,test_middleware}.py
    ├── health/{__init__,test_health}.py
    ├── server/{__init__,dummy_features,test_app,test_mounts}.py
    ├── test_config.py
    └── test_main.py
```

流儀の出典(変更しない): `apps/indexer/pyproject.toml`、`apps/indexer/Dockerfile`、`apps/indexer/.dockerignore`、`apps/indexer/src/loreley_indexer/main.py`(設定エラー表示・起動)、`api/middleware.py`、`common/log_setup.py`、`apps/crawler/src/loreley_crawler/api/errors.py`、`apps/indexer/tests/architecture/*`、`apps/indexer/tests/api/test_logging.py`

### 3.2 モジュールの責務と依存の向き

| モジュール | 責務 | import してよい内部モジュール |
| --- | --- | --- |
| `main` | 設定読み込み、ログ設定、機能の生成、`create_app`、`uvicorn.run` | `config`、`server`、`health`、`common` |
| `config` | 環境変数の読み込みと検証。値を出さない `ConfigError` | `common` |
| `server` | 汎用の口(外側 FastAPI、ルーター取り込み、サブアプリのマウント、共通部品の設置) | `common` だけ(機能パッケージ不可) |
| `health` | `GET /healthz` のルーター | `common` だけ |
| `common` | 葉。エラー形式・ハンドラ・middleware・ログ設定 | なし |

- 機能パッケージどうしは依存しない(R2)
- 基盤は `opensearchpy`・`urllib3`・`requests`・`httpx`・`httpx2`・`aiohttp`・`anyio` を使わない(所有者は空。admin 導入時に D R5 どおり割り当てる)
- CORS の middleware はどこからも import しない

## 4. 実装フェーズ

各フェーズの終わりに `uv run pytest` と `uv run ruff check`/`ruff format --check` を通し、結果を作業記録に残す。実装開始時のコミット SHA を作業記録に記録しレビューの比較基準にする(プラン作成時点の HEAD は `6fb61a0`)。

### P1: 雛形・設定・ログ設定
- 成果物: `pyproject.toml`、`.python-version`、`.gitignore`、`uv.lock`、`__init__.py`、`config.py`、`common/__init__.py`、`common/logging_setup.py`、`tests/test_config.py`、`tests/common/test_logging_setup.py`
- テスト: 既定値、環境変数での上書き(`LOG_LEVEL` 小文字可)、不正 PORT(0・65536・非数字)と不正 `LOG_LEVEL` で `ConfigError`(メッセージに入力値のセンチネルなし、`__context__`/`__cause__` が None)、ログ設定(ハンドラ1つ・水準反映・`LOG_LEVEL=DEBUG` でも `uvicorn.access` は ERROR)
- 検証: `uv sync`、`uv run pytest`、`uv run ruff check`、`uv lock --check`
- 依存: なし

### P2: common/http(統一エラー形式・ハンドラ・middleware)
- 成果物: `common/http/{__init__,errors,handlers,middleware}.py`、`tests/common/http/*`、`tests/common/test_logging_calls.py`
- テスト(最小の FastAPI に `install_common_http` を設置):
  - エラー本文の形(`details=None` はキー省略)
  - 404 `not_found`、405 `method_not_allowed`(`Allow` あり)、その他 HTTPException(例 418)は `http_error`
  - `ApiError` が指定どおり返る
  - 422 変換(2.3 の表を表駆動): reason 各種、`field` の作り方、項目名の整形、`json_invalid` に `details` なし、入力値センチネルが本文に出ない
  - middleware: ログ形式とID非出力・未一致は `-`、`debug_access_log_paths` は DEBUG・他は INFO、`/api/` 配下(404含む)に `no-store`・他は付かない、想定外例外は 500 `internal_error` で `raise_server_exceptions=True` でも上がらない、ERROR ログはクラス名と origin だけ(`exc_info` なし、メッセージのセンチネルなし)
  - ソース全体の AST 検査: `extra`/`exc_info`/`stack_info`/`.exception` 不使用
- 依存: P1

### P3: health 機能パッケージと server(口)
- 成果物: `health/{__init__,router}.py`、`server/{__init__,app}.py`、`tests/health/test_health.py`、`tests/server/{dummy_features,test_app,test_mounts}.py`
- テスト:
  - health の独立性: 素の `FastAPI` に載せても 200。`create_app()` に渡さなければ `/healthz` は 404、渡すと 200。`no-store` なし・DEBUG ログ・`POST` は 405
  - 外側アプリ: `docs_url`/`redoc_url`/`openapi_url` が None(`/docs` 等は JSON 404)、`/healthz/` は 404(307 でない)、CORS ヘッダーなし、`lifespan` の開始・終了が動く
  - マウントの口(ダミーのサブアプリ2つ。例 `/api/dummy-a/v1`、`/api/dummy-b/v1`): 200 + `no-store`、アクセスログがちょうど1行でテンプレートが `{item_id}` を含む、配下の未知パスは同形の JSON 404 + `no-store`、405・`ApiError`・422→400・想定外例外→500(1回だけログ、再送出しない)がすべて A 5.2 形式、末尾なし・末尾スラッシュは 404、2つのマウントが干渉しない
  - AAM-U-2(テンプレートを1回だけ出す方法)は実際に確かめて決めた方式を作業記録に残す
- 依存: P2

### P4: main と tests/architecture
- 成果物: `main.py`、`tests/test_main.py`、`tests/architecture/*`
- main: `build_app()` = `create_app(routers=[create_health_router()], debug_access_log_paths={HEALTH_PATH})`。`main()` = `load_settings` → `configure_logging` → `build_app` → `uvicorn.run(app, host, port, log_config=None, access_log=False)`
- test_main: `build_app()` で `/healthz` 200・未知パス JSON 404、組み立て中に外部接続しない、子プロセスで `LORELEY_API_PORT=SENTINEL-PORT` を付けて起動し終了コード非0・stderr に `port` を含みセンチネルを含まない
- architecture: 許可表は 3.2 のとおり。`FEATURE_PACKAGES = {"health"}` から作り、自己テストで合成2つ目の機能(例 `dummy`)を足して R2 を確かめる。実ソース検査(違反なし・循環なし・未分類ファイルは違反・`config` に依存するのは `main` だけ)、合成ソースの自己テスト(正例・負例)、`test_http_rules`(CORS import なし、ルートデコレーター付き関数は `async def`、`FastAPI(...)` が `docs_url=None`・`redoc_url=None`・`redirect_slashes=False` を明示)
- 手動検証: `uv run python -m loreley_api.main` を起動し `curl -s 127.0.0.1:8080/healthz` が 200、`/nope` が JSON 404、アクセスログの出方、Ctrl-C 停止(8080 使用中なら `LORELEY_API_PORT` を変える)
- 依存: P3

### P5: Dockerfile・.dockerignore・README
- Dockerfile(Indexer に倣う): `PYTHON_IMAGE` は Indexer と同じタグ+ダイジェスト、builder で `uv==0.13.7`・`uv sync --locked --no-dev --no-install-project`・`compileall`、runtime は uid/gid 10001 の `api` ユーザー、`ENV PATH/PYTHONPATH=/app/src/PYTHONUNBUFFERED/PYTHONDONTWRITEBYTECODE/LORELEY_API_HOST=0.0.0.0`、`EXPOSE 8080`、2.4 の HEALTHCHECK、`CMD ["python","-m","loreley_api.main"]`。Node ステージ・`/app/web` なし
- README: 概要(基盤のみ・機能は `/healthz` だけ・設計書の参照先)、起動方法(ローカルと Docker。publish は `127.0.0.1` に限る。認証がないので公開範囲を広げない注意を1文)、環境変数表(HOST/PORT/LOG_LEVEL・設定エラーの出方)、テスト実行
- 検証(他プロジェクトのコンテナは止めない。衝突しにくいポート):
  1. `docker build -t loreley-api apps/api`
  2. `docker run -d --name loreley-api-check -p 127.0.0.1:18080:8080 loreley-api`
  3. 15〜30秒後に `docker inspect --format '{{.State.Health.Status}}' loreley-api-check` が `healthy`
  4. `curl -s 127.0.0.1:18080/healthz` が 200、`/nope` が JSON 404
  5. `docker exec loreley-api-check id -u` が `10001`。`docker run --rm --entrypoint python loreley-api -c "import pytest"` が失敗(dev 依存なし)
  6. `docker run --rm -e LORELEY_API_PORT=SENTINEL-PORT loreley-api` が非0終了で出力にセンチネルなし
  7. `docker stop` で速やかに停止。自分で作ったコンテナ・イメージだけを `docker rm` / `docker rmi`
- 依存: P4

## 5. レビューフェーズ

P5 完了後、`code-reviewer` と `test-reviewer` を並列で実施。
- 対象: `apps/api/` 配下の全ファイル(3.1。`uv.lock` は差分確認対象外可)。新規ディレクトリなのでファイル一覧で渡す
- 比較基準: 実装開始時のコミット SHA
- 渡す文脈: 0000・0001・本プラン・各フェーズ作業記録、A(3〜7章)、D(3・4.1・4.2・4.11・6・7章)
- code-reviewer の観点: A 5.2/5.5/6 への適合、2.2 の差の吸収の妥当性、値の漏えい、想定外例外の再送出しなし、サブアプリへの設置(AAM-P-23)、要件外機能の混入、Dockerfile(非root・固定・HEALTHCHECK)と README の正確さ
- test-reviewer の観点: 受け入れ基準と 4章のテスト項目の網羅、統一エラー形式・アクセスログ・マウント口ダミー検証・health 独立性・tests/architecture 自己テストが空振りしないか
- `web-ui-reviewer`(Web UI 変更なし)、`document-reviewer`(設計書変更なし。README は code-reviewer が確認)は省略
- 指摘対応: Critical/Important は修正→検証やり直し→同じレビュアーで再レビュー。Suggestion/Nitpick は判断と理由を作業記録に残す。両レビューが「指摘なし」か「Critical/Important 解消済み」になるまで完了にしない

## 6. タスクレビューフェーズ

実装フェーズが5つで複数セッションにまたがる見込みであり、設計書との差(2.2)の吸収の妥当性確認が要るため、`task-reviewer` を実施。レビューフェーズ完了と作業記録作成後に実施。観点: 要件・0001・プランと実際の変更・作業記録の突き合わせ、設計書との差の申し送り漏れ、要件外の追加。Critical/Important は該当工程に差し戻し再レビュー。

## 7. テスト方針
- 単体テストとアプリ全体のテスト(`TestClient`(httpx2))。外部システムなし
- 統一エラー形式(外側・マウント配下の両方で 404/405/HTTPException/ApiError/422→400/500、センチネルで値非出力)
- アクセスログ(`caplog`。形式・水準・1リクエスト1行・テンプレート)
- マウント口のダミー検証(ダミーはテスト内のみ。プロダクトコードに置かない)
- health の独立性、`tests/architecture`(実ソース + 合成ソース自己テスト)
- 起動(子プロセスで設定エラー、手動で `/healthz`)、コンテナ(P5 の手順)

## 8. リスクと対策

| リスク | 対策 |
| --- | --- |
| `fastapi>=0.143.2` が解決できない・挙動が違う | P1 の `uv lock` で確認。解決できなければ止めてユーザーに報告。下限は勝手に下げない(BAPI-P-8) |
| マウント下でログ二重・テンプレート不取得・例外ハンドラ不発(AAM-U-2) | P3 のダミー検証で受け入れ条件を固定し方式を確定、作業記録に残し admin タスクへ申し送る |
| ServerErrorMiddleware が再送出し uvicorn がトレースバックを出す | 外側・サブアプリ両方の middleware で捕捉。`raise_server_exceptions=True` で確認 |
| 8080/18080 使用中・別プロジェクトのコンテナ稼働 | ポートを変える。他のコンテナは止めない |
| 設計書 D との差が admin 実装時に混乱を招く | 2.2 の5項目を申し送りに明記。追従改訂は別タスク |
| ロールバック | 変更は新規 `apps/api/` のみ。ディレクトリ削除で元に戻る |

## 9. 未解決事項
- AAM-U-2(マウント下でテンプレートを1回だけ出す具体方式): P3 で確かめて決め、作業記録に残す
- 設計書 D(3章・4.2・6章 R3・R9・許可表・7.1)への追従改訂: 本タスクでは行わず申し送る
- HO-40/HO-41(README の公開範囲・リスク注意書きの全文): admin 実装タスクで扱う。本 README には公開範囲を広げない注意を1文だけ入れる
