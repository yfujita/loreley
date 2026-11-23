# 0004 P4・P5 実装との突き合わせ・旧構成の残存確認

作成: 2026-11-23(メインエージェント。改訂を担当していないので、書いた本人の確認にならない)

## P4 実装との突き合わせ

D・A の記述を、`apps/api/src`・`apps/api/tests` と照合した。**全項目が一致**。不一致で D・A を直した箇所はなし。承認済みの案の内容を変える必要が出た項目もなし。

| 記述(D の節) | 実装の根拠 | 結果 |
| --- | --- | --- |
| `create_app(*, routers=(), mounts=(), debug_access_log_paths=(), lifespan=None)`・`SubAppMount(prefix, app)`(frozen)(4.2・4.12) | `server/app.py` の `SubAppMount`・`create_app` | 一致 |
| 外側 `FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False, lifespan=…)`(4.2) | `server/app.py` | 一致 |
| サブアプリに `redirect_slashes=False` を強制、`install_common_http(mount.app, log_access=False)`、最後に外側へ設置(4.2) | `server/app.py` の `for mount in mounts` | 一致 |
| `install_common_http(app, *, debug_access_log_paths=(), log_access=True)`(4.11) | `common/http/__init__.py` | 一致 |
| テンプレート = `root_path` から `app_root_path` を除いた部分 + `route.path`。`app_root_path` なしは `route.path`。`methods` を持たない route・route なしは `-`(4.2) | `common/http/middleware.py` の `_route_template` | 一致 |
| `no-store` は `/api/` の応答のみ。判定は `get_route_path(scope)` で処理の前(4.2・4.11) | `middleware.py` の `dispatch`・`NO_STORE_PATH_PREFIX` | 一致 |
| 500 変換と再送出しない・保証の範囲(4.11・4.12(c)) | `middleware.py` の docstring・`_respond` | 一致 |
| `ApiError(status_code, code, message, *, retryable=False, details=None)`、`error_response(..., headers=None)`(4.11) | `common/http/errors.py` | 一致 |
| `HEALTH_PATH="/healthz"`、`create_health_router()`、`async def healthz`(4.2) | `health/router.py` | 一致 |
| `build_app()` = `create_app(routers=[create_health_router()], debug_access_log_paths={HEALTH_PATH})`、`main()` の手順、`uvicorn.run(log_config=None, access_log=False)`(4.1・4.12(a)) | `main.py` | 一致 |
| `Settings`(`HOST` 既定 127.0.0.1・`PORT` 既定 8080 で 1〜65535・`LOG_LEVEL` 既定 INFO・小文字可)、`load_settings`・`ConfigError`・`describe_settings_errors`(4.1) | `config.py` | 一致 |
| `FEATURE_PACKAGES={"health"}`、許可表(`main`→`config`・`server`・機能、`server`・`config`・`common`・`health`→なし)、`EXTERNAL_LIBRARY_OWNERS` の 7 ライブラリが空(6章・4.12) | `tests/architecture/dependency_rules.py` | 一致 |
| `FastAPI(...)` に `docs_url=None`・`redoc_url=None`・`redirect_slashes=False` と `openapi_url`(値不問)を要求(R10) | `tests/architecture/test_http_rules.py` | 一致 |
| ログ AST 検査の対象メソッド `debug`・`info`・`warning`・`warn`・`error`・`critical`・`fatal`・`exception`・`log`、禁止 `extra`・`stack_info`・`exc_info`(R11・4.12(a)) | `tests/common/test_logging_calls.py` | 一致 |
| tests の構成(`architecture/`・`common/`(`http/`・`test_logging_*`)・`health/`・`server/`(`test_app`・`test_mounts`・`dummy_features`)・`test_config`・`test_main`・`log_records.py`)(4.12(a)・7.1) | `tests/` の一覧 | 一致 |
| `src` の構成(`common/logging_setup.py`・`common/http/{errors,handlers,middleware}.py`・`config.py`・`health/`・`main.py`・`server/`)、`Dockerfile`・`README.md`・`pyproject.toml`・`uv.lock`(3章・4.12(a)) | `apps/api/` の一覧 | 一致 |
| FastAPI 0.165.0・Starlette 1.10.0 | writer が `uv.lock` で確認(0003) | writer の確認。`test_mounts.py` が固定 |

未検証(書いた記述どおり「テストで固定していない」「未検証」と明記されている): `FastAPI(root_path=…)` をサブアプリに設定したときの挙動、入れ子マウント、`ClientDisconnect`。

## P5 grep(対象 `docs/v0.x/system-design/api/`。ベースラインは 0002)

| パターン | 結果 |
| --- | --- |
| `server/health`(D) | 9 行目の改訂履歴のみ(許可) |
| `create_app(settings`(D) | 0 件 |
| `admin_app`(D) | 新方式の記述のみ(`SubAppMount(..., admin_app)`、`create_admin_app` の戻り値の説明) |
| `server --> adminEntry` | 0 件 |
| `load_config`・`ApiConfig`(D) | 205・207・391・913 行。すべて「admin 実装時」と明記 |
| `HO-1〜HO-50` | D・C は 0 件。B は 8 行目の改訂履歴の過去の記述のみ。A は 8 行目(改訂履歴)・253 行(HO-51 の説明)・383 行(更新した旨の記述)のみ。いずれも経緯の記録として残す |
| 「本タスクでは作らない」(D) | 0 件 |
| `apps/api/` は存在しない(D) | 0 件(8.1 の「2026-11-22 の設計時」の記述に変更済み) |
| `server` のマウント(D) | 916・1006 行。「`server` のマウントから `main` の組み立てに改めた」という変更の経緯の記述のみ |
| `server` が import / `server` の設定(D) | 913 行 AAM-P-14。「`server` の設定 dataclass は作らない」という現状の記述のみ |
| `AAM-U-2` | D 880 行(確認していないこと。確定済みに触れる)・922(AAM-P-23)・935(確定に移した)、A 357(HO-48。確定)・360・370・373(HO-51) |
| `BAPI-U-2` | A 10.4 は OpenAPI の `servers`・`paths` に絞った。D の参照は 880・935 行付近で、絞った内容と整合(document-reviewer の観点に入れる) |
| HO-51 の状態(A 360 行) | 「対応済み」 |
| `git diff --stat c0b6e40 -- apps/` | 空(`apps/` に変更なし) |

## 変更したファイル

- なし(確認のみ)

## 未対応事項・次にやること

- document-reviewer によるレビュー(対象 A・B・C・D、比較基準 `c0b6e40`)
- task-reviewer(レビュー対応の後)
- 範囲外: E・F の「HO-1〜HO-50」、HO-39 の状態、BAPI-U-2 の OpenAPI の `servers`・`paths`、`apps/api/README.md` 冒頭の古くなった注記
