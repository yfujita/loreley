# 0004 実装 P1〜P3(雛形・設定・common/http・health・server)

日付: 2026-11-23
実施: code-implementer(メインエージェントが検証を再実行)
実装開始時のコミット SHA: `6fb61a0`(`apps/api/` は新規)

## 実施した作業

0002 + 0003 の P1(雛形・設定・ログ設定)、P2(common/http)、P3(health 機能パッケージと server の口)を実装した。

## 検証結果(メインエージェントが再実行)

`cd apps/api` で `uv run pytest`: **170 passed**。`uv run ruff check`: 通過。`uv run ruff format --check`: 29 files already formatted。`uv lock --check`: 通過(fastapi 0.165.0、starlette 1.10.0、httpx2 2.16.2。`fastapi>=0.143.2,<1` で解決。下限は下げていない)。

## 変更ファイル(すべて `apps/api/` の新規。`docs/`・`apps/crawler`・`apps/indexer` は変更なし)

- `.gitignore`、`.python-version`、`pyproject.toml`、`uv.lock`
- `src/loreley_api/`: `__init__.py`、`config.py`(Settings・ConfigError・load_settings)、`common/{__init__,logging_setup}.py`、`common/http/{__init__,errors,handlers,middleware}.py`、`health/{__init__,router}.py`、`server/{__init__,app}.py`
- `tests/`: `conftest.py`、`log_records.py`、`test_config.py`、`common/test_logging_setup.py`、`common/test_logging_calls.py`、`common/http/test_{errors,handlers,middleware}.py`、`health/test_health.py`、`server/{dummy_features,test_app,test_mounts}.py`(各 `__init__.py` を含む)

## 判断・設計上の理由

### AAM-U-2(マウント下でアクセスログを1回だけ出す方式)の確定
- 方式: **外側のアプリの middleware だけが、サブアプリの処理後にアクセスログを1回出す**。サブアプリには `install_common_http(..., log_access=False)` を設置し、例外の吸収と `no-store` だけを担当させる
- 0002 2.5 / D の想定(外側はマウント担当パスを除外し、サブアプリ側が接頭辞つきテンプレートを出す)とは**分担が逆**
- 根拠(スクラッチ実験): FastAPI 0.165 / Starlette 1.10 では、外側の middleware がサブアプリ処理後の同じ `scope` から `scope["route"].path` と `scope["root_path"]` を読める。テンプレートは `scope["root_path"].removeprefix(scope["app_root_path"]) + route.path` で組み立てる。サブアプリ内の 404 は `route` がなく `-`。サブアプリに middleware を置かないと、サブアプリ自身の ServerErrorMiddleware が text/plain の 500 にして再送出するため、サブアプリへの設置は必須
- 利点: `skip_prefixes` が不要、サブアプリへの接頭辞の受け渡しが不要、入れ子マウントでも `root_path` が積み上がる
- **注意(依存する実装挙動)**: 「同じ `scope` が共有・更新される」という Starlette の実装挙動に依存する。`tests/server/test_mounts.py` が固定している(変異テストで確認済み: サブアプリがログを出すと 12 件、サブアプリへの設置をやめると 15 件失敗)。Starlette 更新時はこのテストで検知する

### プランからの差分
- `install_common_http` の引数: `skip_prefixes` → `log_access: bool`(署名 `install_common_http(app, *, debug_access_log_paths=(), log_access=True)`)
- `create_app` が `mount.app.router.redirect_slashes = False` を設定する(サブアプリが既定 `redirect_slashes=True` でも A 5.1(末尾スラッシュは 404)を守るため。既定では 307 になることを確認しテストで固定)
- `ApiError(status_code, code, message, *, retryable=False, details=None)`: `retryable`・`details` はキーワード専用
- `error_response` に `headers` 引数を追加(405 の `Allow` を残すため)
- ログ AST 検査の対象メソッドは 0003 の列挙に `fatal` を加えた
- 422 の項目名整形(孤立サロゲート置換・制御文字エスケープ・100文字切り詰め)は Crawler の `display_text.py` に倣い `handlers.py` 内に小さく実装(`common/display_text` は作っていない)
- pydantic は孤立サロゲートを含むキーを `loc=("body",)`・type=`string_unicode`(reason は `format`)にするため、置換のエンドツーエンド確認は「`body` の `format`」まで。置換自体は単体テストで確認

### 0003 §3(lifespan)のテスト
親の lifespan の開始・終了が1回ずつ、親が開いたダミー資源をサブアプリのハンドラが使える(終了後は閉じる)、マウントしたサブアプリ自身の lifespan は実行されない、を `tests/server/test_mounts.py`・`test_app.py` に追加した。

## 未対応事項・次にやること

- P4(`main.py`・`tests/architecture`)、P5(Dockerfile・`.dockerignore`・README)、P6(設計書9章 HO-51 追記)が未着手
- **HO-51 への申し送り事項**(P6 で反映):
  - AAM-U-2 の確定方式(上記。D の「外側はサブアプリ担当パスを除く」とは逆の分担。`log_access=False` で設置)
  - `redirect_slashes` を `create_app` で強制する
  - 孤立サロゲートを含むキーは `body` の `format` になる
  - 0002 2.2 の5項目、サブアプリ lifespan、OpenAPI 生成(0003 §4)
- P4 の architecture 許可表: `server` は `fastapi`・`starlette`・`common.http` のみ import、`health` は `fastapi` のみ(実ソースで成立済み)。`starlette` の import を外部ライブラリの許可に含めること
