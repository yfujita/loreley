# 0001 要件確認

日付: 2026-11-23

## 実施内容

`requirements-clarifier` で要件定義(0000)と設計書(api-base-design-v0.1、admin-api-module-structure-v0.1、admin-api-architecture-v0.1)、既存実装(apps/indexer、apps/crawler)を突き合わせ、不明点3件をユーザーに確認した。

## ユーザー回答(確定)

| # | 質問 | 回答 |
| --- | --- | --- |
| Q1 | 基盤の範囲 | **共通の土台一式**。main/config、server(`create_app`・機能パッケージをマウントする口)、common(統一エラー形式・アクセスログ・`no-store`・ログ設定)、`tests/architecture`(層と依存規則のAST検査)。設定は `HOST`/`PORT`/`LOG_LEVEL` のみ。含めない: admin、infrastructure、OpenSearch/Crawler 関連設定、`/admin/` 静的配信、OpenAPI 公開・書き出し、`BlockingRunner`、本文上限 |
| Q2 | 「追加しやすい」ことの検証 | (選択肢外の回答)**ヘルスチェックが独立したモジュールとして実装できているか**を観点にする。つまりヘルスチェックを、将来の admin・search と同じ「機能モジュール」の形で実装し、基盤の口に組み込む |
| Q3 | Dockerfile・README | **両方作る**。Dockerfile は Indexer の流儀(固定ベースイメージ・マルチステージ・非root・HEALTHCHECK)で、Node ステージは含めない。README は起動方法・環境変数・テスト実行の最小限。compose・CI・scripts は変更しない |

## 確定した要件(設計書・要件から自明なもの。clarifier報告より)

- 対象は `apps/api` のみ。パッケージ `loreley_api`(`src/loreley_api/`)。
- 技術スタックは Crawler・Indexer に揃える: Python `>=3.12,<3.13`、FastAPI `>=0.143.2`、uvicorn(単一プロセス)、pydantic `>=2.9,<3`、pydantic-settings `>=2.6,<3`、uv/hatchling/pytest/ruff、dev依存 `httpx2`・`pytest`・`ruff`。
- 設定は `BaseSettings`(`env_prefix="LORELEY_API_"`)。`HOST=127.0.0.1`(コンテナでは `0.0.0.0`)、`PORT=8080`、`LOG_LEVEL=INFO`。不正値は起動時に失敗し、値はログに出さない。
- `GET /healthz` は何も呼ばず 200 `{"status":"ok"}`。アクセスログでは DEBUG。
- 外側アプリは `docs_url`・`redoc_url`・`openapi_url` を `None`、`redirect_slashes` 無効、CORS なし。
- エラー応答は A 5.2 形式。未定義パス 404 `not_found`、405 `method_not_allowed`、その他 `http_error`、想定外 500 `internal_error`。
- アクセスログはメソッド・ルートのテンプレート・ステータス・所要時間のみ。uvicorn は `log_config=None`・`access_log=False`。想定外例外は middleware が 500 に変換し再送出しない。
- 層構造: エントリ → server → 機能パッケージ → infrastructure → common。機能パッケージどうしは依存しない。
- 起動時に外部へ接続しない。停止は Indexer と同じ lifespan 方式。
- 設計書(A〜D)は変更しない。食い違いは作業記録に申し送る。
- 受け入れ基準: `uv run pytest` と `uv run ruff check` が通る。`python -m loreley_api.main` で起動し `GET /healthz` が 200。未知パスが JSON 404。`docker build` 成功、HEALTHCHECK が healthy。

## 未解決事項(プランで扱う)

- **Q2 の回答と設計書の差**: 設計書(A 2.1)は `/healthz` を server(外側アプリ)に置く形だが、ユーザーの意図は「ヘルスチェックを独立モジュールとして実装」。プランで、health を機能モジュール(例 `loreley_api/health`)として実装し、マウントの口(`create_app` が機能モジュールを受け取る)に組み込む構成を検討し、設計書との差があれば作業記録に申し送る。
- 422(`RequestValidationError`)変換の範囲(基盤では `invalid_request` と基本的な `reason` のみ、対応表の網羅は admin 実装時に回す案)。
- Dockerfile の `HEALTHCHECK` 値(起動時に外部接続しないため `--start-period` は短くする案)。

## 次にやること

planner で作業プラン(0002)を作成し、ユーザーの承認を得る。
