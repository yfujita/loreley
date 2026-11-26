# 20261126_add_web_container_nginx

## 背景・目的

Admin View の静的コンテンツは、`api` ではなく `web` コンテナ(Nginx)が配信し、`/api/` も Nginx が `api` にプロキシする(フロント設計 v0.2。ユーザー指示)。そのための `web` コンテナと compose の追加、`api` 側の `web` 判定の置き換え、結合テストの追従を行う。

## 要件

### 現状(As-Is)

- `web` コンテナはなく、`apps/web` もない(フロントエンドは未実装)
- compose の `api` は `127.0.0.1:${API_HOST_PORT:-8080}:8080` でホストに公開されている
- `api` の EP-13(ダッシュボード)は、`web` の状態を `LORELEY_API_WEB_DIST_DIR/index.html` が読めるかで判定している。`web` が別コンテナになると、全環境で `web` が常に異常に見える
- 結合テスト(`tests/integration/api/`)は `api` を `127.0.0.1:8080` で直接呼び、`/app/web` に `index.html` を mount して `web` を normal にしている

### あるべき姿(To-Be)

- `web` コンテナ(Nginx)が `/admin/` の SPA を配信し、`/api/` を `api` へプロキシする。ホストに公開するのは `web` だけ(`127.0.0.1` のみ)で、`api` はホストに公開しない
- `api` の EP-13 の `web` 判定が、`web` への HTTP 確認になっている。`api` に静的配信の前提(`LORELEY_API_WEB_DIST_DIR`・`web_dist.py`)が残っていない
- 結合テストが、新しい公開範囲・判定方式で通る

### 具体的にやること

- `apps/web/Dockerfile`(Node 24 でビルド → Nginx。ベースはタグ+ダイジェスト固定、`npm ci`、`dist/` を `/usr/share/nginx/html/admin` へ)と `apps/web/nginx/default.conf`(設計 E 3.3 の方針)を作る
- compose に `web` サービスを追加する(`build: ../../apps/web`、`127.0.0.1:${WEB_HOST_PORT}` に publish、`depends_on: api`(`service_healthy`))。`api` の `ports` を外す。`compose.yaml` 冒頭の「公開範囲」の注意書きと、`deploy/compose/README.md`・`apps/api/README.md` を更新する(HO-40・41 の注意書きを `web` に適用。運用の確認方法 `docker compose ps`・`logs web api` も書く)
- `api` の EP-13 の `web` 判定を `HttpHealthCheck` による HTTP 確認に置き換える(`ComponentId`・`reason` の OpenAPI は変えない)。`web_dist.py`・`LORELEY_API_WEB_DIST_DIR`・配線・コメント・関連テストを撤去または更新する
- 結合テストを追従する: `compose.test.yaml` が `api` を `127.0.0.1:8080` に publish し、`/app/web` の mount と fixtures を不要にして `web` の扱いを新しい判定に合わせる
- Nginx の実装時確認(HO-58): `proxy_read_timeout` などの数値、`%2F`・`%2E` を含む `job_id` が Nginx 越しで保持されること、`web` のヘルスチェック手段、`/` の扱い、`api` との結合を確認する
- 開発サーバー(Vite)の `/api` の転送先を `web` の公開ポートにする設定は、フロント実装側の作業(HO-57)。本タスクでは `WEB_HOST_PORT` を用意する

## 対象範囲

- `apps/web/`(Dockerfile・`nginx/default.conf`・最小のスキャフォールド)、`deploy/compose/`、`apps/api/`(EP-13 の `web` 判定・設定・README・Dockerfile のコメント・テスト)、`tests/integration/api/`

## スコープ外

- Admin View の画面・機能の実装(最小のスキャフォールドを除く)
- OpenAPI の型の修正(別タスク `20261126_fix_admin_openapi_types`)
- 認証・認可の追加、Search View
- 設計書の改訂(必要な追従は A の HO-59〜65 で申し送り済み)

## 制約・前提条件

- 設計は `ui-admin-frontend-architecture-v0.2.md` の 3.3〜3.6(Nginx 配信・`web` と `api` の関係)に従う。ホストへの publish は `127.0.0.1` のみ(認証がなく、到達できる全員が破壊的操作を実行できるため)
- `web` イメージのビルドは、`apps/web` に `package.json` と `vite build` が通る最小の構成があることが前提。フロントの最初のスキャフォールドの後に着手する
- B(`web` コンテナ)と C(`api` の `web` 判定の置換)は同時に完了させる(片方だけだとダッシュボードの `web` が常に異常に見える)
- 外部 CDN などへの実行時の依存を持たない。IT のホスト側ポート(9200・8000・8001・8080)と重ならない `WEB_HOST_PORT` を使う
- 別プロジェクトのコンテナ(Fess など)を止めない

## 完了条件

- [ ] `docker compose up` で `web` が起動し、`http://127.0.0.1:<WEB_HOST_PORT>/admin/` が配信され、`/api/admin/v1/meta` が Nginx 経由で返る(`api` はホストに公開されていない)
- [ ] 深い SPA パスが `index.html`、欠落アセットが 404、`/admin` が 301、`/` が 302 になる
- [ ] ダッシュボード(EP-13)の `web` が、`web` の稼働中は normal、停止中は abnormal になる
- [ ] `apps/api` のテスト・lint、`api` の結合テストが通る
- [ ] README・compose の注意書きが新しい公開範囲に合っている
- [ ] レビュー(`code-reviewer`・`test-reviewer`)で Critical・Important が解消されている

## 成果物

- `apps/web/Dockerfile`・`apps/web/nginx/default.conf`・最小スキャフォールド、`deploy/compose/` の変更、`apps/api/` の変更、`tests/integration/api/` の変更、README

## 補足・参考情報

- `docs/v0.x/system-design/api/api-base-design-v0.1.md` の HO-53〜58(HO-36・37・40・41・46 の読み替えを含む)
- `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.2.md` の 3.3〜3.6・12.8、`ui-admin-frontend-module-structure-v0.2.md` の 8.9
- `agent_tasks/20261126_create_admin_ui_system_design/` の 0004(`api` 側の撤去範囲 X-C1)・0005(Nginx 設定案と検証結果)・0007(G4-2)
