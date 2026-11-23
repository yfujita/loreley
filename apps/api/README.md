# Loreley API

Admin API・将来の Search API・MCP Server が載る、`api` コンポーネントの共通の土台。設計は `docs/v0.x/system-design/api/`(`api-base-design-v0.1.md` が共通の設計、`admin/` が Admin API の仕様書・アーキテクチャ・モジュール構成)を正とし、本書は起動・設定・テストの要点をまとめる。**ただし実装は `admin/admin-api-module-structure-v0.1.md`(D)と一部異なる**(ヘルスチェックを `health/` パッケージにしたこと、`server` の入口、アクセスログの分担など)。差分は `api-base-design-v0.1.md` 9.2 の HO-51 に書いてあり、D を追従改訂するまでは実装を正とする。

## 1. 概要

- **現在の範囲**: 基盤だけ。機能は `GET /healthz`(`{"status":"ok"}`)の 1 つで、Admin API・Search API・MCP Server は未実装
- **構成**: `main`(設定・ログ設定・組み立て・起動)、`config`(環境変数)、`server`(機能を載せる口。`create_app`)、`health`(ヘルスチェック。最初の機能パッケージ)、`common`(エラー形式・アクセスログ・ログ設定)
- **共通の挙動**: エラーは `{"error": {"code", "message", "retryable"}}`(任意で `details`)の JSON、未定義のパスは 404 `not_found`、未定義のメソッドは 405 `method_not_allowed`。アクセスログは自前(メソッド・ルートのテンプレート・ステータス・所要時間)で、`/healthz` は DEBUG。対話型ドキュメント(`/docs` など)と CORS はない
- **MVP の前提**: 単一ホスト・単一プロセス・**認証なし**

## 2. 起動方法

### ローカル

Python 3.12 と [uv](https://docs.astral.sh/uv/) を使う。

```sh
cd apps/api
uv sync
uv run python -m loreley_api.main
curl -s http://127.0.0.1:8080/healthz   # {"status":"ok"}
```

`python -m loreley_api.main` は単一プロセスで uvicorn を起動する(`--workers`・`--reload` は使わない)。既定の待ち受けは `127.0.0.1:8080`。Ctrl-C(SIGINT)・SIGTERM で停止する。

### Docker

ビルドコンテキストは `apps/api`。

```sh
docker build -t loreley-api apps/api
docker run --restart unless-stopped -p 127.0.0.1:8080:8080 loreley-api
```

- **認証がないので、公開範囲を広げない**。上の例は、ポートをホストのループバック(`127.0.0.1`)にだけ publish している。`0.0.0.0` への publish(`-p 8080:8080`)はしない
- イメージは Python 3.12(slim。ベースイメージはタグとダイジェストで固定。運用は `Dockerfile` の冒頭のコメント)で、依存は `uv.lock` から入れる(dev 依存は含まない)。**非 root(uid 10001)** で動く
- コンテナでは `LORELEY_API_HOST=0.0.0.0` が設定済み(既定の `127.0.0.1` では外から届かない)。`LORELEY_API_PORT` を変えたら、公開するポートも合わせる
- `HEALTHCHECK` は `GET /healthz`(間隔 15 秒、タイムアウト 5 秒、起動猶予 10 秒、再試行 3 回)。ホストは `127.0.0.1` 固定。`LORELEY_API_HOST` を特定の IP や IPv6 に変えるなら、`HEALTHCHECK` も合わせる

## 3. 環境変数

接頭辞は `LORELEY_API_`。

| 変数 | 既定値 | 説明 |
| --- | --- | --- |
| `LORELEY_API_HOST` | `127.0.0.1` | 待ち受けるアドレス。コンテナのイメージでは `0.0.0.0` |
| `LORELEY_API_PORT` | `8080` | 待ち受けるポート(1〜65535) |
| `LORELEY_API_LOG_LEVEL` | `INFO` | ログ水準(`DEBUG`・`INFO`・`WARNING`・`ERROR`。小文字も可) |

設定が不正だと、起動に失敗して終了コード 1 で終わる。標準エラー出力には、値を含まず、項目名と検証の種別だけを出す(例: `loreley_api.config.ConfigError: invalid settings: port: int_parsing`)。ログは標準エラー出力に出る。

## 4. テスト

```sh
cd apps/api
uv sync                      # dev 依存(pytest、ruff、httpx2)を含めて入れる
uv run pytest
uv run ruff check
uv run ruff format --check
uv lock --check              # uv.lock が pyproject.toml と一致していること
```

`tests/architecture` は、モジュール間の依存(許可表)と HTTP の規約(CORS なし・ルートは `async def`・`FastAPI(...)` の既定値)を AST で検査する。機能パッケージを足すときは、`tests/architecture/dependency_rules.py` の `FEATURE_PACKAGES` に追加する。
