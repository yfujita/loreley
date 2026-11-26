# 20261126_add_web_container_nginx

## 背景・目的

Admin View のフロントエンド設計 v0.2(タスク `20261126_create_admin_ui_system_design`)で、Web UI の配信を「`api` が静的配信する」から「**`web` コンテナ(Nginx)が `/admin/` を静的配信し、`/api/` を `api` へリバースプロキシする**」に変更した(ユーザー指示 2026-11-26。FARC-K-4)。ブラウザから見て同一オリジンのままなので CORS は要らない。

この設計を実現するため、前提タスク B+C として次をまとめて行う。**B と C は同時に完了させる**(B だけでは、`web` が別コンテナになるのに `api` の EP-13(Dashboard の D1)が `web` を「`api` のディスク上の `index.html` の有無」で判定し続け、全環境で `web` が異常に見える)。

- **B**: `web` コンテナ(Dockerfile・Nginx 設定・compose のサービス)の追加と、`api` のホスト公開の取りやめ(公開するのは `web` だけにして、認証なしの破壊的操作の入口を 1 つにする。G4-2)
- **C**: `api` の EP-13 の `web` 判定を、`HttpHealthCheck` による `web` の HTTP 確認に置き換え、`web_dist.py`・`LORELEY_API_WEB_DIST_DIR` を撤去する(G4-4 案 (a))。結合テストの追従を含む

## 要件

### 現状(As-Is)

- `apps/web` は存在しない(フロントの実装はこれから。設計は v0.2 で完了)
- `deploy/compose/compose.yaml` に `web` サービスはない。`api` は `127.0.0.1:${API_HOST_PORT:-8080}:8080` でホストに publish されている。ファイル冒頭の「公開範囲」の注意書きと README(`deploy/compose/README.md`・`apps/api/README.md`)は、`api` を公開する前提で書かれている(認証なしの破壊的操作・ブラウザ経由の書き込みへの保護なしの注意書き。HO-40・41)
- EP-13 の `web` は、`LORELEY_API_WEB_DIST_DIR`(既定 `/app/web`)の `index.html` が読めるかで判定している(`apps/api/src/loreley_api/infrastructure/probes/web_dist.py`・`WebDistCheck`)。`api` イメージは Web の成果物を含まないため、**本番の compose のままでは `web` が `missing`(異常)になる**。D1(EP-13 の `ComponentId`・`reason`)の OpenAPI は、他のコンポーネント(`crawler` など)を確認する `HttpHealthCheck` と同じ型を使う
- 結合テスト(`tests/integration/api/`)は、`compose.test.yaml` で `index.html` だけの `fixtures/web` を `/app/web` に mount して `web` を normal にし、`127.0.0.1:8080` の `api` を直接呼ぶ(`support.py`・`scripts/run-api-integration-test.sh`)。`test_01_startup.py`・`test_90_component_failures.py` が `web` の状態を検査している

### あるべき姿(To-Be)

- `docker compose up` で `web` コンテナ(Nginx)が起動し、`http://127.0.0.1:${WEB_HOST_PORT}/admin/` でビルド済みの Admin View(`dist/`)が配信され、`/api/` が `api` コンテナ(`api:8080`)にプロキシされる
- ホストへ publish されるのは `web` だけ(`127.0.0.1` のみ)。`api` は本番用の `compose.yaml` で `ports` を持たず、内部ネットワークのサービス名(`api:8080`)でのみ到達できる
- EP-13 の `web` は、`api` が `web` の URL を `HttpHealthCheck` で確認した結果(normal / abnormal)を返す。`ComponentId`・`reason` の OpenAPI は変わらない。`web_dist.py`・`LORELEY_API_WEB_DIST_DIR`・`/app/web` は撤去されている
- 結合テストは、`api` を `127.0.0.1:8080` に publish する上書き(`compose.test.yaml`)で従来どおり `api` を直接呼べ、`web` の fixtures に頼らない
- README が `web` を公開範囲の対象として注意書きを持ち、`api` はホストに公開されないことと、その確認方法(`docker compose ps`・`docker compose logs web api`・`docker compose exec`)を説明している

### 具体的にやること

**B: `web` コンテナの追加(`apps/web`・`deploy/`)**

- `apps/web/Dockerfile`: Node ビルドステージ(Node 24.15.0 以上の 24 系。タグ+ダイジェストで固定。`package.json`・`package-lock.json`・`.npmrc` を先にコピーして `npm ci` → ソース → `vue-tsc` と `vite build`)→ 配信ステージ(Nginx のイメージ。タグ+ダイジェストで固定)で `dist/` を `/usr/share/nginx/html/admin` にコピー。**型生成(`gen:api`)はビルドで行わない**(生成コードはリポジトリにコミットされる)。実行時に外部通信しない(外部 CDN・外部フォントなし)
- `apps/web/nginx/default.conf`(設計 E 3.3 の方針に従う):
  - `/admin/` と配下: `try_files $uri /admin/index.html`+`Cache-Control: no-cache`(SPA のフォールバック)
  - `/admin/assets/`: `try_files $uri =404`+`Cache-Control: public, max-age=31536000, immutable`、gzip。欠落は 404(`index.html` を返さない)
  - `/admin`(末尾スラッシュなし)は 301 `/admin/`(`absolute_redirect off`)、`/` は 302 `/admin/`、`/api`(末尾スラッシュなし)は 301 `/api/`。それ以外(`/healthz` など)は location を置かない
  - `/api/`: 宛先は変数+`resolver 127.0.0.11`(`api` が未起動でも nginx が起動できる)で `http://api:8080`。`proxy_pass` に URI 部を付けず、元のリクエスト URI をそのまま渡す。`proxy_cache` なし・`add_header` を足さない(upstream の `Cache-Control: no-store` を素通し)。`error_page` で JSON を返さない(502・503・504・413 は Nginx の HTML のまま)
  - `add_header` は子 location に継承されないので、location ごとに書く
  - 数値の最終値を決める(設計の値は仮値): `proxy_connect_timeout`(仮 5 秒)、`proxy_read_timeout`(**90 秒以上**。`api` の書き込みの Crawler 待ち(約 63 秒)で返す JSON の 504 より先に切れないこと)、`proxy_send_timeout`、`client_max_body_size`(`api` の本文上限 1 MiB より少し大きく。その値で `api` の JSON 400 が返ること)、gzip の対象と `gzip_min_length`
  - 実装時確認事項を決めて記録する: `Host` を `$host` か `$http_host` か、`add_header ... always` とセキュリティヘッダー(CSP など)、404 の `Cache-Control`、`/` の扱い(Search View の置き場が決まるまでの暫定)、ブラウザの暗黙の `/favicon.ico`
- compose の `web` サービス: `build: ../../apps/web`(コンテキスト=アプリのディレクトリ)、`127.0.0.1:${WEB_HOST_PORT}` に publish(コンテナ内は 80。`WEB_HOST_PORT` の既定値は 8080・8000・8001・9200 と重ならない値を選ぶ。`.env.example` にも記載)、`depends_on: api`(`service_healthy`)、再起動 `unless-stopped`。`api` は `web` を `depends_on` に入れない。`web` の healthcheck の手段を決める(`curl`・`wget` の有無に頼るか、専用の `/healthz` の location を置くか。これは C の `web` 判定の確認先にも関わる)
- **`api` の `ports` を `compose.yaml` から外す**(`API_HOST_PORT` は本番用では不要になる)。`compose.yaml` 冒頭の「公開範囲」の注意書きと、`deploy/compose/README.md`・`apps/api/README.md` を `web` が公開される前提に更新する(認証なしの破壊的操作・ブラウザ経由の書き込みへの保護なしの注意書き(HO-40・41)を `web` に適用。運用の確認方法として `docker compose ps`・`docker compose logs web api`、`api` の `/healthz` は `docker compose exec` でコンテナ内から確認、と書く)
- `%2F`・`%2E` を含む `job_id`(EP-07 のパス)が Nginx 越しで保持されることを、実機(Nginx → 実 `api`)で確認する(FARC-U-21)。保持されない場合の扱いは、確認結果に応じて作業記録に書き、ユーザーに判断を仰ぐ

**C: `api` の `web` 判定の置換(`apps/api`)**

- EP-13 の `web` を、`HttpHealthCheck` で `web` の URL を確認する方式に置き換える。環境変数名・確認先(URL とパス)は本タスクで決める(設計の例は `LORELEY_API_WEB_URL`。確認先は B の healthcheck の手段と整合させる)。`compose.yaml` の `api` に環境変数を足す。`ComponentId`・`reason` の OpenAPI は変えない
- 撤去・変更(パスは `apps/api/src/loreley_api/` からの相対。設計書の調査時点の一覧で、網羅は実装時に grep で確かめる): `infrastructure/probes/web_dist.py`・`probes/__init__.py`・`probes/ports.py`(`WebDistCheck`)、`admin/dependencies.py`・`admin/services/dashboard.py`・`admin/settings.py`・`config.py`・`main.py`・`admin/openapi_export.py` の `web_dist_dir`・`web_probe` の配線、`LORELEY_API_WEB_DIST_DIR`(既定 `/app/web`)、`ComponentId` の docstring、`apps/api` の README・`Dockerfile` の古いコメント、`deploy/compose/README.md`・`compose.yaml` のコメント、関連するテスト(調査時点で 11 ファイル)

**結合テストの追従(`tests/integration/api/`)**

- `compose.test.yaml` が、`api` を `127.0.0.1:8080` に publish する(Crawler と同じ診断・テスト用の上書き。本番用の `compose.yaml` には書かない)。`support.py`・`scripts/run-api-integration-test.sh` が `127.0.0.1:8080` を直接呼ぶ前提は維持する
- `/app/web` の mount(`compose.test.yaml` の `api.volumes`)と `fixtures/web/index.html` を不要にし、`test_01_startup.py`・`test_90_component_failures.py` の `web` の扱いを、新しい判定方式に合わせる(`web` の normal を成立させる方法は、プランで決める。下の「要確認」を参照)

**開発サーバーの転送先(設計 HO-57。`apps/web` の `vite.config.ts`)**

- `apps/web` の最初のスキャフォールドで `vite.config.ts` が作られる際の既定の転送先を、`web` の公開ポート(`http://127.0.0.1:<WEB_HOST_PORT>`)にする方針が設計にある。本タスクでは、**スキャフォールド側にその設定がある場合に、`WEB_HOST_PORT` の既定値と整合していること**を確認する(`vite.config.ts` 自体の実装は、フロントの実装タスクの責務)

## 対象範囲

- `apps/web/Dockerfile`・`apps/web/nginx/default.conf`(`apps/web` の他のファイルは、フロントの実装タスクが作る)
- `deploy/compose/compose.yaml`・`.env.example`・`README.md`
- `apps/api`(`web` 判定の置換と撤去、README・Dockerfile のコメント、単体テスト)
- `tests/integration/api/`(`compose.test.yaml`・`fixtures/web/`・`test_01_startup.py`・`test_90_component_failures.py`・必要なら `support.py`・README)、`scripts/run-api-integration-test.sh`
- (実機確認のための)ビルド・起動・curl とブラウザでの動作確認

## スコープ外

- `apps/web` のフロントエンドの実装(`package.json`・Vue アプリ・型生成・画面)。**本タスクは、フロントの最初のスキャフォールドの後に着手する**(下の「制約・前提条件」)
- 設計書(A・B・C・D・DS・画面仕様)本文の追従改訂(A の申し送り HO-59・60・65 など。別途。本タスクは実装と、実装に関わる README・コメントの更新まで)
- 前提タスク A(`ttl_days`・`ttl_seconds` の OpenAPI の型。別タスク `20261126_fix_admin_openapi_types`)
- Search View の配信・`/` の恒久的な扱い(将来、同じ `web` が配信しうるが、本タスクでは設計しない。`/` は暫定の 302 `/admin/`)
- 認証・HTTPS(TLS 終端)・外部公開(MVP は認証なし・ループバックのみ)・CSP の網羅的な設計
- Nginx のログ・メトリクスの詳細設計、`web` のスケール・複数化
- `web` 経由の接続確認の自動テスト(`tests/integration/<名前>/` の新設。設計 F 7.1。フロントの実装後のタスク)
- Crawler の実 uvicorn での `job_id` のパスの挙動確認(HO-46 の残り。本タスクの確認は Nginx 越しの保持のみ)

## 制約・前提条件

- **着手の順序**: `web` イメージのビルドは、`apps/web` に `package.json` と `vite build` が通る最小の構成(フロントの最初のスキャフォールド)があることが前提。スキャフォールドが未完了なら、本タスクは着手しない(または着手前にユーザーへ確認する)
- **B と C は同時に完了させる**。B だけを先に完了・公開しない
- 設計(`docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.2.md` の 3.3〜3.6・12.8、同 module-structure の 8.9、`api-base-design-v0.1.md` の HO-53〜58)と矛盾しない。設計の仮値(Nginx の数値など)を変える場合は、理由を作業記録に残す
- `api` イメージは Web に依存しない(Node のステージを持たない)。`api` は静的ファイルを配信しない
- 公開範囲: `web` は `127.0.0.1` にのみ publish する(`0.0.0.0` を省いた書き方はしない)。`api` を本番用の `compose.yaml` で publish しない。認証なしで破壊的操作ができるため
- ホストのポートの重複: 結合テストは 9200・8000・8001・8080 を固定で使う(`WEB_HOST_PORT` の既定値はこれらと重ならない値にする)。別プロジェクトのコンテナ(Fess など)が 9200 を使っていることがあるため、**他のコンテナを勝手に止めない**
- `ComponentId`・`reason` の OpenAPI を変えない(画面側の変更を要らなくするため)
- 変更に対応する検証(ビルド・リント・単体テスト・結合テスト)を実施する。結合テストを実行する場合は、既存の実行スクリプト(`scripts/run-api-integration-test.sh`)を使い、排他ロック・安全策に従う
- Nginx のイメージ・Node のベースイメージは、タグ+ダイジェストで固定する(Indexer の Dockerfile と同じ流儀)。外部への依存(ビルド時の npm レジストリ)以外を実行時に持たない

## 完了条件

- [ ] `docker compose up` で `web` が起動し、`http://127.0.0.1:${WEB_HOST_PORT}/admin/` が 200(`text/html`・`Cache-Control: no-cache`)を返す。深い SPA パス(例 `/admin/sources/xxx`)も `index.html` を返し、`/admin/assets/` の欠落は 404 になる。`/admin` は 301 `/admin/`、`/` は 302 `/admin/`
- [ ] `web` 経由で `/api/admin/v1/meta` が 200(`application/json`・`Cache-Control: no-store` が素通し)で届く。実際の `api` との結合で、書き込み系(例: 設定の登録・更新)と読み取り系の両方が通る
- [ ] `api` コンテナは本番用の `compose.yaml` でホストに publish されず(`docker compose ps` で確認)、`web` だけが `127.0.0.1` に publish されている。ホストの `127.0.0.1:8080` で `api` に直接つながらない
- [ ] `api` が起動していない状態でも `web`(nginx)が起動する(`host not found in upstream` で落ちない)。`api` の停止中は `/api/` が HTML の 502・504 になる
- [ ] 1 MiB 超の本文(`client_max_body_size` の設定値以下)が `api` の JSON 400 で返り、`proxy_read_timeout` が `api` の書き込みの Crawler 待ち(約 63 秒)より長いことを確認している(後者は設定値の確認でよい。実際の Crawler 停止時の待ちを実測できる場合は実測する)
- [ ] `%2F`・`%2E` を含む `job_id` の `GET /api/admin/v1/jobs/{job_id}` が、Nginx 越しで `api` に直接アクセスした場合と同じ結果(`.`・`..`・`%2E`・`?`・`#` は 404 `job_not_found`、`%2F` は 404 `not_found`)になる
- [ ] EP-13(Dashboard)の `web` が、`web` 起動中は normal、`web` 停止中は abnormal(`reason` は `connection_refused` または `name_not_resolved`)になる。`ComponentId`・`reason` の OpenAPI に差分がない(修正の前後に書き出した OpenAPI を比較する)
- [ ] `web_dist.py`・`WebDistCheck`・`LORELEY_API_WEB_DIST_DIR`・`/app/web` への参照が `apps/`・`deploy/`・`tests/`・`scripts/` から消えている(grep で確認する)
- [ ] `apps/api` の単体テストとリント(`ruff`・`pytest`)がすべて通る
- [ ] 結合テスト(`scripts/run-api-integration-test.sh`)が通る(`web` の扱いを新方式に合わせたうえで)。実行できなかった場合は、その理由と代わりの確認を作業記録に残す
- [ ] `compose.yaml` 冒頭の「公開範囲」の注意書き・`deploy/compose/README.md`・`apps/api/README.md` が、`web` を公開対象とする記述になっており、`api` の確認方法(`docker compose ps`・`logs`・`exec`)が書かれている
- [ ] 設計の仮値から変えた Nginx の数値・決めた環境変数名・`web` の healthcheck の手段・`WEB_HOST_PORT` の既定値が、作業記録に残っている(設計書への反映は別タスクの申し送りとして記録)
- [ ] 未対応事項(設計書の追従改訂 HO-59・60・65 の依頼など)を最新の作業記録に書いている

## 成果物

- `apps/web/Dockerfile`・`apps/web/nginx/default.conf`
- `deploy/compose/` の変更(`compose.yaml`・`.env.example`・`README.md`)
- `apps/api` の変更(`web` 判定の置換・撤去・テスト・README)
- `tests/integration/api/` と `scripts/run-api-integration-test.sh` の追従
- 作業記録(`agent_tasks/20261126_add_web_container_nginx/NNNN-*.md`)

## 補足・参考情報

- 出典: `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.2.md` の 3.3(配信・プロキシ)・3.4(開発サーバー)・3.5(Docker ビルド)・3.6(`web` と `api` の関係)・5.7(D1 の `web`)・12.7・12.8
- 出典: `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-module-structure-v0.2.md` の 2.4・8.9
- 出典: `docs/v0.x/system-design/api/api-base-design-v0.1.md` 9 章の HO-53(Dockerfile・Nginx 設定・compose の `web`)・HO-54(公開範囲)・HO-55(EP-13 の `web` 判定)・HO-56(結合テスト)・HO-57(dev の転送先)・HO-58(Nginx の実装時確認)。HO-36・37 は読み替え
- 調査の根拠: `agent_tasks/20261126_create_admin_ui_system_design/` の 0003(配信担当の変更)・0004(OpenAPI・コードの照合。X-C1・X-C2)・0005(技術検証。Nginx の設定案は `nginx:alpine`(nginx/1.31.10)の `nginx -t` とダミーの upstream で確認済み。**実際の `api` との結合は未確認**)・0007(ゲート4。G4-1・G4-2・G4-4・G4-5)
- 関連タスク: `20261126_fix_admin_openapi_types`(前提タスク A。独立。どちらが先でもよい)
- 運用: 別プロジェクトの Fess が 9200 を使っていることがある(結合テストの実行前にポートを確認する)

### 要確認(要件確認の工程でユーザーに聞く点。推奨案つき)

1. **結合テストでの `web` の扱い**: C の置換後、結合テストの `web` を normal にする方法。(a) 結合テストの compose に実際の `web` を含める(`apps/web` のビルドが IT の前提になる。実 `web` の起動を確認できるが、IT がフロントのビルドに依存する)/ (b) `compose.test.yaml` に、HTTP 200 を返すだけの軽い代役(`web` という名前のサービス)を置く(フロントに依存しない)/ (c) `web` の判定を IT の対象外にする(既存の 5 コンポーネント検査から外す)。推奨は **(b)**(IT を `apps/web` のビルドから独立させつつ、`HttpHealthCheck` の経路を実機で通せる)。**(a) は B の `web` 経由の接続確認と重なるため、後続のタスク(設計 F 7.1)で扱う**
2. **`web` の healthcheck と EP-13 の確認先**: `web` 専用の `/healthz` の location を置く(`/healthz` は設計では「location を置かない(404)」としているので設計の変更になる)か、`/admin/` や `/admin/index.html` の 200 を確認先にするか。推奨は **`/admin/` の 200(設計を変えない)**。healthcheck のコマンド(イメージに含まれる `wget` の有無)は実装時に確認する
3. **`WEB_HOST_PORT` の既定値**: 8080・8000・8001・9200 と重ならない値(例: 8090)。推奨は **8090**(実装時に使用中でないことを確認)
4. **スキャフォールド前に着手する場合**: 本タスクの着手前に、`apps/web` の最小のスキャフォールドが別タスクで終わっている前提でよいか。推奨は **「スキャフォールドの後に着手」**(設計 E 12.8 のとおり)。スキャフォールドが後になるなら、本タスクは `Dockerfile` を含めて着手できない
