# Loreley API

`api` コンポーネント。現在は **Admin API**(管理画面向け。ベースパス `/api/admin/v1`)を提供する。Search API・MCP Server は未実装で、同じ土台に載せる予定。設計は `docs/v0.x/system-design/api/` を正とする(`api-base-design-v0.1.md` が共通の設計、`admin/` が Admin API の仕様書・アーキテクチャ・モジュール構成)。本書は起動・設定・安全上の注意・テストの要点をまとめる。

実装と設計書(特に `admin/admin-api-module-structure-v0.1.md`)に細部の差がある場合は、差分と設計書の追従改訂の申し送りが `agent_tasks/20261123_implement_admin_api/` の作業記録にある。追従改訂が済むまでは実装を正とする。

## 1. 概要

- **提供するもの**: Admin API の 14 エンドポイント(3 章)と、ヘルスチェック `GET /healthz`
- **Admin API の性格**: 画面向けの窓口。OpenSearch は**読み取りだけ**で、書き込み・操作(データソースの登録・更新・削除ジョブ・クロール起動・取消・ロック解放)はすべて Crawler の HTTP API を経由する。Indexer には `GET /healthz` だけを呼ぶ
- **構成**: `main`(設定・ログ設定・組み立て・起動)、`config`(環境変数)、`server`(外側のアプリ。機能を載せる口)、`health`(ヘルスチェック)、`admin`(Admin API)、`infrastructure`(OpenSearch・Crawler・死活確認の各クライアント)、`common`(エラー形式・アクセスログ・ログ設定など)
- **共通の挙動**: エラーは `{"error": {"code", "message", "retryable"}}`(任意で `details`)の JSON、未定義のパスは 404 `not_found`、未定義のメソッドは 405 `method_not_allowed`。アクセスログは自前(メソッド・ルートのテンプレート・ステータス・所要時間)で、`/healthz` は DEBUG。エラー応答・ログには入力値・認証情報・原本のパスを出さない。対話型ドキュメント(`/docs`・`/redoc`)と CORS はない
- **MVP の前提**: 単一ホスト・単一プロセス・**認証なし**
- **このタスクの範囲外**: Web UI(`/admin/`)の静的配信、compose への `api` サービスの追加、Dockerfile の Node ビルドステージ(別タスク。設計書の申し送り HO-34〜37)。`LORELEY_API_WEB_DIST_DIR` は現在、EP-13 の `web` の死活確認(`index.html` が読めるか)だけに使う

## 2. 公開範囲と安全性(必ず読むこと)

**この `api` には認証・認可がない。信頼できるネットワークにだけ公開する。**

- **既定は localhost のみ**。待ち受けの既定は `127.0.0.1` で、Docker で動かすときもホストへの publish は `127.0.0.1` に限る(4 章)。社内ネットワークへ公開すると、到達できる**全員**が次の操作を実行できる
  - データソース削除ジョブの起動(EP-05。そのデータソースの全文書・記録・設定が消え、取り消せない)
  - `force_delete=true` でのクロール起動(EP-06。削除の割合ルール・最小件数ルールを無視して削除する)
  - クロールの取消(EP-07)、ロック解放(EP-08)
  - データソース設定の登録・更新(EP-03・EP-04)
- API に確認や二重送信の防止はない(誤操作の防止は Admin View の確認ダイアログに委ねている)
- **`connector_config.root` には、Crawler のコンテナから見える任意のパスを指定できる**。Admin API は値を検証せず Crawler に中継する。読めるのは、Crawler に `:ro` でマウントしたディレクトリだけ
- **ブラウザ経由の書き込み要求への保護(`Origin` 検査・CSRF 対策)はない**。悪意あるウェブページが、利用者のブラウザから localhost の `api` へ要求を送る攻撃を防げない。
  - 本文なしの POST(EP-05・EP-06・EP-07)は、`Origin` の有無・値を問わず処理される(テストで確認済み)。ブラウザの単純なリクエストで届くため、他のウェブサイトのページからも呼べる。EP-06 の `force_delete=true` は JSON の本文が要るので、この経路では指定できない
  - EP-03 は `Content-Type: application/json` が要り(それ以外は 400)、EP-04(PUT)・EP-08(DELETE)は CORS を許可していないため、通常のブラウザからは届かない。ただし **DNS rebinding なら、EP-08 を含む全 EP(読み取りを含む)が対象**になる
  - このリスクは設計上、受け入れた未対応のリスクとして扱っている(軽い緩和は足していない)。認証を導入するときに保護を再検討する
- OpenAPI の定義も同じ公開範囲に載るので、実行時の公開は既定で無効にしている(5 章)

## 3. 提供する API

ベースパスは `/api/admin/v1`。仕様(リクエスト・レスポンス・エラー)は `docs/v0.x/system-design/api/admin/admin-api-v0.1.md`(1.1 が一覧)を参照。

| EP | メソッドとパス | 用途 |
| --- | --- | --- |
| EP-01 | `GET /sources` | データソース一覧 |
| EP-02 | `GET /sources/{source_id}` | データソース詳細 |
| EP-03 | `POST /sources` | データソース登録 |
| EP-04 | `PUT /sources/{source_id}` | データソース更新(全置換) |
| EP-05 | `POST /sources/{source_id}/delete-jobs` | データソース削除ジョブの起動・再実行 |
| EP-06 | `POST /sources/{source_id}/crawl-jobs` | クロールの手動起動 |
| EP-07 | `POST /jobs/{job_id}/cancel` | ジョブの取消 |
| EP-08 | `DELETE /sources/{source_id}/lock` | ロック解放 |
| EP-09 | `GET /jobs` | ジョブ一覧 |
| EP-10 | `GET /jobs/{job_id}` | ジョブ詳細 |
| EP-11 | `GET /sources/{source_id}/documents` | 文書の確認(タブごと) |
| EP-12 | `GET /opensearch/cluster` | OpenSearch のクラスタ状態 |
| EP-13 | `GET /dashboard` | コンポーネントの死活 |
| EP-14 | `GET /meta` | cron のタイムゾーン・Dashboards の URL |

ベースパスの外には、`GET /healthz`(`{"status":"ok"}`)がある。何にも接続せず、アプリケーションが受け付けを始めていれば 200 を返す(コンテナの `HEALTHCHECK` 用)。

## 4. 起動方法

必須の環境変数が 3 つある(5 章: `OPENSEARCH_URL`・`CRAWLER_URL`・`INDEXER_URL`)。欠けていると、起動に失敗する。**起動時に OpenSearch・Crawler・Indexer へは接続しない**ので、これらが落ちていても `api` は起動する(接続できない状態は、各 EP の応答と EP-13 に出る)。

### ローカル

Python 3.12 と [uv](https://docs.astral.sh/uv/) を使う。

```sh
cd apps/api
uv sync
LORELEY_API_OPENSEARCH_URL=http://localhost:9200 \
LORELEY_API_CRAWLER_URL=http://localhost:8001 \
LORELEY_API_INDEXER_URL=http://localhost:8000 \
  uv run python -m loreley_api.main
curl -s http://127.0.0.1:8080/healthz   # {"status":"ok"}
```

`python -m loreley_api.main` は単一プロセスで uvicorn を起動する(`--workers`・`--reload` は使わない)。既定の待ち受けは `127.0.0.1:8080`。Ctrl-C(SIGINT)・SIGTERM で停止する。

### Docker

ビルドコンテキストは `apps/api`。

```sh
docker build -t loreley-api apps/api
docker run --restart unless-stopped \
  --network <OpenSearch・Crawler・Indexer と共通のネットワーク> \
  -p 127.0.0.1:8080:8080 \
  -e LORELEY_API_OPENSEARCH_URL=http://opensearch:9200 \
  -e LORELEY_API_CRAWLER_URL=http://crawler:8001 \
  -e LORELEY_API_INDEXER_URL=http://indexer:8000 \
  loreley-api
```

- **認証がないので、公開範囲を広げない**(2 章)。上の例は、ポートをホストのループバック(`127.0.0.1`)にだけ publish している。`0.0.0.0` への publish(`-p 8080:8080`)はしない
- `--network` は、`http://opensearch:9200` のような名前を解決するために、各コンテナと同じネットワークを指定する。URL のホスト名は、実際のコンテナ名・サービス名に合わせる
- OpenSearch の認証・TLS、任意の死活確認先、`CRON_TIMEZONE` など、その他の設定は 5 章の環境変数で渡す。接続先・認証情報などは、イメージに焼き込まず実行時に環境変数で渡す(Docker の secrets や `_FILE` 形式は読めない)。環境変数は `docker inspect` で見えるので、その権限を絞る
- イメージは Python 3.12(slim。ベースイメージはタグとダイジェストで固定。運用は `Dockerfile` の冒頭のコメント)で、依存は `uv.lock` から入れる(dev 依存は含まない)。**非 root(uid 10001)** で動く
- コンテナでは `LORELEY_API_HOST=0.0.0.0` が設定済み(既定の `127.0.0.1` では外から届かない)。`LORELEY_API_PORT` を変えたら、公開するポートも合わせる
- `HEALTHCHECK` は `GET /healthz`(間隔 15 秒、タイムアウト 5 秒、起動猶予 10 秒、再試行 3 回)。ホストは `127.0.0.1` 固定。`LORELEY_API_HOST` を特定の IP や IPv6 に変えるなら、`HEALTHCHECK` も合わせる
- 現在のイメージには Web UI のビルド成果物(`/app/web`)が入っていない。そのため EP-13 の `web` は異常と表示される(Node ビルドステージの追加は別タスク)

## 5. 環境変数

接頭辞は `LORELEY_API_`(下の表では省略)。実装は `src/loreley_api/config.py`、設計は `docs/v0.x/system-design/api/admin/admin-api-architecture-v0.1.md` の 7.2・7.3。空文字を渡した「任意」の URL・文字列は、未設定として扱う。

**必須**

| 変数 | 説明 |
| --- | --- |
| `OPENSEARCH_URL` | OpenSearch の接続先(`http`・`https`) |
| `CRAWLER_URL` | Crawler の接続先。**`http` だけ**。パス・クエリを持たない(`http://crawler:8001` の形。末尾の `/` は取り除く) |
| `INDEXER_URL` | Indexer の接続先(`/healthz` の確認だけに使う)。`CRAWLER_URL` と同じ形で、`http` だけ |

**待ち受けとログ**

| 変数 | 既定値 | 説明 |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | 待ち受けるアドレス。コンテナのイメージでは `0.0.0.0` |
| `PORT` | `8080` | 待ち受けるポート(1〜65535) |
| `LOG_LEVEL` | `INFO` | ログ水準(`DEBUG`・`INFO`・`WARNING`・`ERROR`。小文字も可) |

**OpenSearch**

| 変数 | 既定値 | 説明 |
| --- | --- | --- |
| `OPENSEARCH_USERNAME`・`OPENSEARCH_PASSWORD` | なし | Basic 認証(セキュリティ有効時)。**両方指定するか、両方省略する**。パスワードはログ・エラーに出さない |
| `OPENSEARCH_VERIFY_CERTS` | `true` | 証明書の検証 |
| `OPENSEARCH_CA_CERTS_PATH` | なし | CA 証明書のパス |
| `OPENSEARCH_REQUEST_TIMEOUT_SECONDS` | `10` | 1 リクエストのタイムアウト(0 より大きく 120 以下) |
| `OPENSEARCH_MAX_RETRIES` | `2` | 読み取りの再試行回数(0〜5) |
| `SOURCES_INDEX_NAME` | `loreley-sources` | データソース設定の索引 |
| `JOBS_INDEX_NAME` | `loreley-jobs` | ジョブ・ロックなどの索引 |
| `DELETIONS_INDEX_NAME` | `loreley-deletions` | 削除記録の索引 |
| `SEARCH_INDEX_NAME` | `loreley-documents` | 検索インデックスの**エイリアス**(Indexer の `LORELEY_INDEXER_SEARCH_INDEX_NAME` と同じ値。索引の実体名ではない) |

4 つの索引名は、非空で互いに異なること。Crawler・Indexer の設定と同じ値にする。

**Crawler・死活確認**

| 変数 | 既定値 | 説明 |
| --- | --- | --- |
| `CRAWLER_CONNECT_TIMEOUT_SECONDS` | `3` | Crawler への接続のタイムアウト(0 より大きく 60 以下) |
| `CRAWLER_RESPONSE_TIMEOUT_SECONDS` | `60` | Crawler の応答のタイムアウト(0 より大きく 600 以下) |
| `HEALTH_PROBE_TIMEOUT_SECONDS` | `3` | 死活確認 1 件のタイムアウト(0 より大きく 30 以下)。EP-13 全体の期限はこの値 + 1 秒 |
| `DASHBOARDS_HEALTH_URL`・`EMBEDDING_HEALTH_URL`・`LLM_HEALTH_URL` | なし | 任意のコンポーネントの確認先(完全な URL。`http`・`https`)。未設定なら EP-13 で `not_configured` になる。クエリに秘密を入れない |

**Admin API 固有**

| 変数 | 既定値 | 説明 |
| --- | --- | --- |
| `DASHBOARDS_URL` | なし | ブラウザから到達できる OpenSearch Dashboards の URL(`http`・`https`)。EP-14 で返し、画面がリンクにする。未設定なら `null` |
| `CRON_TIMEZONE` | なし | cron のタイムゾーン(IANA 名。例 `Asia/Tokyo`)。EP-14 で返す。Crawler の `LORELEY_CRAWLER_TIMEZONE` と同じ値を渡す。未設定なら `null` |
| `ADMITTING_LOCK_GRACE_SECONDS` | `60` | ロック取得直後の猶予(0 より大きく 3600 以下)。Crawler の `LORELEY_CRAWLER_ADMITTING_LOCK_GRACE_SECONDS` と同じ値を渡す |
| `OPENAPI_ENABLED` | `false` | OpenAPI JSON の実行時公開(6 章) |
| `WEB_DIST_DIR` | `/app/web` | Web UI のビルド成果物のディレクトリ。EP-13 が直下の `index.html` を確認する。存在は起動時に検査しない |

**URL の検証**: scheme は `http`・`https`(`CRAWLER_URL`・`INDEXER_URL` は `http` だけ)、ホストあり、ユーザー情報(`user:pass@`)なし。認証情報は専用の変数で渡す。

**設定が不正なとき**: 起動に失敗して終了コード 1 で終わる。標準エラー出力には、**値を含まず**、項目名と検証の種別だけを出す(例: `loreley_api.config.ConfigError: invalid settings: port: int_parsing; opensearch_url: missing`)。ログは標準エラー出力に出る。

## 6. OpenAPI

- 実行時の公開は、既定で**無効**(`LORELEY_API_OPENAPI_ENABLED=false`)。無効のとき、`GET /api/admin/v1/openapi.json` は JSON の 404 を返す。`true` にすると、このパスで OpenAPI JSON を返す
- `/docs`・`/redoc`(対話型ドキュメント)は、設定にかかわらず常に無効
- フロントエンドの型生成などのために、**アプリを起動せず、外部に接続せずに**ファイルへ書き出せる。

  ```sh
  cd apps/api
  uv run python -m loreley_api.admin.openapi_export <出力パス>
  ```

  書き出した JSON はリポジトリにコミットしない(置き場は、フロントエンドのタスクで決める)

## 7. 開発・テスト

```sh
cd apps/api
uv sync                      # dev 依存(pytest、ruff、httpx2)を含めて入れる
uv run pytest
uv run ruff check
uv run ruff format --check
uv lock --check              # uv.lock が pyproject.toml と一致していること
```

`tests/architecture` は、モジュール間の依存(許可表)と、HTTP の規約(CORS なし・ルートは `async def`・`FastAPI(...)` の既定値)、読み取り専用の規則(OpenSearch へは読み取りだけ・死活確認は GET だけ)を AST で検査する。機能パッケージを足すときは、`tests/architecture/dependency_rules.py` の `FEATURE_PACKAGES` に追加する。
