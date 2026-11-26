# 0003 作業プラン

- 日付: 2026-11-26
- 作成: planner(`STATUS: PLAN_READY`)の報告をメインエージェントが保存
- 承認状況: **ユーザーの承認待ち**(承認後に P0 へ着手する)

## 1. 目的

前提タスク B+C を実装する。B と C は同時に完了させる(作業ツリーで全フェーズを揃えてからコミット・PR にする。B だけ先に公開しない)。

- **B**: `web` コンテナ(Nginx)を追加し、`api` をホストに publish しない
- **C**: EP-13 の `web` 判定を `HttpHealthCheck` に置換し、`web_dist.py` などを撤去する
- IT と README も追従させる

受け入れ基準は 0000 の完了条件 13 項目(8 章の対応表)。

## 2. 確定事項・前提

### ユーザー回答(0002)

1. スキャフォールドが先 → 完了済み(`6569993`)
2. IT の `web`: (a) 実 `web` を IT の compose に含める
3. healthcheck・EP-13 の確認先: `/admin/` の 200(`/healthz` は置かない)
4. `WEB_HOST_PORT` 既定値: 8090(実装時に使用中でないか確認)

### プランで決めた前提(承認時に確認)

- **P-1 IT の範囲**: IT の compose に実 `web` を含める(`IT_SERVICES`・`IT_WAIT_CHECKS` に `web`)。test_01 は実 `web` で `web=normal` を確認。test_90 に **AIT-93(`web` の停止と復旧)を追加**(停止中の EP-13 は `web=abnormal`・`reason` は `connection_refused` か `name_not_resolved`、他は normal、復旧後 `web=normal`)。`support.py` の `CONTROLLABLE_SERVICES`・`SERVICES_TO_AWAIT_AFTER_START` に `web` を追加。**`web` 経由で `/admin/`・`/api/` を呼ぶ自動テストは作らない**(0000 のスコープ外・設計 F 7.1。P5 の実機確認で代替)
- **P-2 IT でのポート 8090**: compose のマージは `ports` を追記するだけで上書きファイルから消せない(`!reset` は compose 2.24 以降で、対象は v2.3.3 以降のため使えない)。IT でも `web` は `127.0.0.1:8090` に publish される。`run-api-integration-test.sh` で `WEB_HOST_PORT=8090` を固定し、`IT_PORTS` に `web:8090` を足す(IT の固定ポートは 9200・8000・8001・8080・8090 の 5 つ)
- **P-3 環境変数**: `LORELEY_API_WEB_URL`(設計の例のまま)。**必須**で `CRAWLER_URL`・`INDEXER_URL` と同形(`http` のみ・パス/クエリなし・末尾 `/` 除去。`_validate_base_url`)。確認先は `{WEB_URL}/admin/`(パスはコードの定数。`HttpHealthProbe` はリダイレクトに従わないので末尾スラッシュ必須)。compose の値は `http://web:80`。必須の環境変数は 3 → 4
- **P-4 OpenAPI の不変性**: `ProbeReason` の `"missing"` は返す確認がなくなるが**残す**(消すと EP-13 の `reason` 列挙が変わり OpenAPI に差分が出る)。コメントで理由を残し、廃止は申し送り。`ComponentId` の docstring は直す
- **P-5 判定経路**: `web` は他の HTTP 確認と同じく `probe` の枠(`runner.run_all`。上限 8)で並行実行し全体の期限に含める(最大 7 件)。R9 の例外(`WebDistProbe` の直接呼び)は消え、アーキテクチャテストの「直接呼ぶ受け手」は空集合になる
- **P-6 apps/web の追加**: `apps/web/.dockerignore` を追加(`node_modules/`・`dist/` など)。`apps/web/README.md` と `vite.config.ts` の**コメントのみ**を B+C 後の状態に直す(コードは変えない。既定値 8090 は `WEB_HOST_PORT` と一致を確認済み)
- **P-7 Nginx の初期値**(変える場合は理由を作業記録に残す): `proxy_connect_timeout` 5s / `proxy_read_timeout` 90s(api の Crawler 待ち約 63 秒より長く)/ `proxy_send_timeout` 30s / `client_max_body_size` 2m / gzip は設計 3.3 の 5 種・`gzip_min_length` 1024 / `resolver 127.0.0.11 valid=10s ipv6=off` / `absolute_redirect off` / `Host` は `$http_host` / `add_header ... always` は使わない(404 に `Cache-Control` なし)/ セキュリティヘッダー(CSP 等)は足さず申し送り / `/` は暫定 302 `/admin/` / `/favicon.ico` は location なし(404)で申し送り
- **P-8 ベースイメージ**: Node は `node:24.<最新パッチ>-bookworm-slim`(Vite 8 のネイティブ依存の musl 差を避け alpine にしない)、Nginx は `nginx:<安定版>-alpine`。いずれもタグ+ダイジェスト固定。固定日・版を Dockerfile のコメントに書く(Indexer の流儀)
- **P-9 healthcheck**: `apps/web/Dockerfile` の `HEALTHCHECK`(`wget -q -O /dev/null http://127.0.0.1/admin/` 想定。`wget`/`curl` の有無は P1 で確認)。IT の上書きで `interval` だけ縮める
- **P-10 コミット**: 実施中はコミットしない(コミット・PR はユーザー)。比較基準は P0 で記録する HEAD(想定 `6569993`)

## 3. 影響範囲

**追加**: `apps/web/Dockerfile`・`apps/web/nginx/default.conf`・`apps/web/.dockerignore`

**B(deploy)**
- `deploy/compose/compose.yaml`: 冒頭コメント(構成・「公開範囲」)、`api` の `ports` 削除とコメント、`api` に `LORELEY_API_WEB_URL`、`web` サービス追加
- `deploy/compose/.env.example`: `API_HOST_PORT` を `WEB_HOST_PORT=8090` に置換
- `deploy/compose/README.md`: 構成表・前提ポート・設定表・起動手順・`api` の節・公開範囲・トラブルシュート・`web` が abnormal に見える既知事項(削除)

**C(apps/api。網羅は実装時に grep)**
- `infrastructure/probes/`(`web_dist.py` 削除、`__init__.py`・`ports.py`)、`admin/services/dashboard.py`、`admin/dependencies.py`、`admin/settings.py`(`web_dist_dir` → `web_url`)、`config.py`、`main.py`、`admin/openapi_export.py`、`admin/base/codes.py`(docstring)、`common/probe_outcome.py`(コメント)、`apps/api/Dockerfile`(コメント)、`apps/api/README.md`
- テスト: `tests/admin/routers/test_dashboard.py`・`test_dashboard_over_http.py`、`tests/admin/services/test_dashboard.py`、`tests/api_config.py`、`tests/architecture/test_http_rules.py`・`test_read_only_rules.py`、`tests/fakes/fake_probes.py`・`test_fake_probes_protocol.py`、`tests/infrastructure/probes/test_web_dist.py`(削除)、`tests/test_config.py`、`tests/test_main.py`

**IT**
- `tests/integration/api/compose.test.yaml`(`api.volumes` 削除、`api.ports` と `web.healthcheck.interval` 追加)、`fixtures/web/index.html` 削除、`support.py`、`test_01_startup.py`、`test_90_component_failures.py`(AIT-93)、`README.md`、`scripts/run-api-integration-test.sh`

**apps/web(コメントのみ)**: `README.md`・`vite.config.ts`

## 4. 実装フェーズ

main=メインエージェント、impl=`code-implementer`。各フェーズ終了時に main が作業記録と `STATUS.md` を更新する(採番は 0004〜)。

- **P0 事前確認・ベースライン(main)**: HEAD の SHA 記録。`lsof` で 8090・8080・8000・8001・9200 の使用状況、`docker ps` で既存コンテナ把握(**他のコンテナは止めない**)。`docker compose version` 記録。変更前 OpenAPI を書き出し(`uv run python -m loreley_api.admin.openapi_export <scratch>/openapi-before.json`)。`apps/api` の `ruff check`・`ruff format --check`・`pytest` をベースラインに。8090 が使用中なら既定値をユーザーに確認。9200 が Fess に使われていれば IT は止めずに待つか実行不可の理由を記録
- **P1 `web` イメージ(impl → main 確認)**: `.dockerignore`・`Dockerfile`(Node ステージ `npm ci` → `npm run build`、`gen:api` なし/Nginx ステージ・`HEALTHCHECK`、タグ+ダイジェスト固定)・`nginx/default.conf`(0000 の具体項目・設計 3.3・P-7)。検証: `docker build`・`nginx -t`・`wget`/`curl` の有無確認・`api` 不在でも起動し healthy・curl(`/admin/` 200 `text/html` `no-cache`、`/admin/sources/xxx` 200、`/admin/assets/` 実在 200 `immutable` gzip・欠落 404、`/admin` 301、`/` 302、`/api` 301、`/healthz` 404、`/api/admin/v1/meta` HTML 502)・外部 URL がないこと(grep)。一時 user-defined network を使い終了後に削除
- **P2 `api` の `web` 判定置換(impl → main 検証。P1 と並行可)**: P-3〜P-5 に従い実装、`web_dist` 系の撤去、単体テスト追従(確認先 `{web_url}/admin/`・normal/abnormal/timeout・`web_url` 必須と形式違反の `ConfigError`・`test_dashboard_over_http` のローカル HTTP スタブ・R9)。検証: `ruff`・`pytest`、OpenAPI を書き出して `diff` が 0、`grep -rn "web_dist\|WebDist\|WEB_DIST\|/app/web" apps/api` が 0 件
- **P3 compose(impl → main 検証。P1・P2 に依存)**: `web` サービス追加(`build: ../../apps/web`、`127.0.0.1:${WEB_HOST_PORT:-8090}:80`、`depends_on: api: service_healthy`、`restart: unless-stopped`)、`api` の `ports` 削除と `LORELEY_API_WEB_URL: http://web:80`(`api` は `web` に depends_on しない)、冒頭コメント、`.env.example`。検証: `docker compose config`(`api` に `ports` なし、`web` は `127.0.0.1` のみ)
- **P4 IT の追従と実行(impl → main 実行。P3 に依存)**: 3 章 IT の変更、AIT-93 追加、スクリプトの `WEB_PORT=8090`・`IT_PORTS`・`IT_SERVICES`・`IT_WAIT_CHECKS`、README 追従(ポート 5 つ・`web` のビルドが前提・npm レジストリ接続が必要・AIT-93・fixtures 削除)。検証: lint、`scripts/run-api-integration-test.sh`(排他ロック・事前確認に従う)、全テスト成功と AIT-93 の `[observed] reason` の記録。実行不可なら理由と代替(P5)を記録
- **P5 実機確認(main。P4 と同時に動かさない)**: 専用プロジェクト名(例 `-p loreley-webcheck`)で `compose.yaml` のみ起動(同名資源がないこと確認、ポート使用中なら `OPENSEARCH_HOST_PORT`・`INDEXER_HOST_PORT` をずらす、`CRAWLER_DOCUMENTS_DIR` は scratch、終了後 `down -v`)。確認:
  1. `docker compose ps`(`api` に publish なし、`web` が `127.0.0.1:8090->80`、`127.0.0.1:8080` に接続不可)
  2. `/admin/` 系を P1 と同項目で compose 上で再確認
  3. `/api/admin/v1/meta` が 200・`application/json`・`Cache-Control: no-store`
  4. 書き込み系(EP-03 登録・EP-04 更新)・読み取り系(EP-01・02・13)
  5. EP-13: `web` normal → `stop web` で abnormal(`reason` 記録。api 内から `docker compose exec api python -c ...` で読む)→ `start` で normal
  6. `job_id` の `%2F`・`%2E`・`.`・`..`・`%3F`・`%23`: `web` 経由(`curl --path-as-is`)と `api` 直(`exec` で `http.client`)を比較。期待は `.`・`..`・`%2E`・`?`・`#` が 404 `job_not_found`、`%2F` が 404 `not_found`。**違えば直さず記録しユーザーに判断を仰ぐ**
  7. 1 MiB+1 バイトの POST が api の JSON 400(任意: 2 MiB 超が HTML の 413)
  8. `stop api` 後に HTML の 502/504、その状態で `web` を再作成しても起動(`host not found in upstream` なし)、`start api` で復旧
  9. `proxy_read_timeout` ≥ 90s を設定と `nginx -T` で確認(任意: `pause crawler` で約 63 秒の JSON 504 `crawler_response_lost` を実測、必ず `unpause`)
  10. ブラウザ(playwright-cli)で `/admin/` が描画される。コンソールエラーが `/favicon.ico` の 404 だけであること
  11. (任意)`npm run dev` → `web` → `api` の連鎖で `/api/admin/v1/meta` が届く
- **P6 README・コメント仕上げ(impl → main 確認。P5 に依存)**: `deploy/compose/README.md`(`web` を公開対象に、HO-40・41 の注意書きを `web` に適用、`api` 非公開と確認方法 `docker compose ps`・`logs web api`・`exec` で `/healthz`、`WEB_HOST_PORT`、既知事項の削除)、`apps/api/README.md`(必須環境変数 4 つ・`WEB_URL` 行・`WEB_DIST_DIR` 削除)、`apps/web` の README・`vite.config.ts` コメント。最終 grep: `grep -rn "web_dist\|WebDist\|WEB_DIST_DIR\|/app/web" apps deploy tests scripts`(`.venv`・`node_modules` 除く)が 0 件、`API_HOST_PORT` は IT の上書きとスクリプトだけ
- **P7 レビュー → P8 指摘対応 → P9 タスクレビュー**(5〜7 章)

## 5. レビューフェーズ

- `code-reviewer` と `test-reviewer` を並列で実施(`code-reviewer` は公開範囲の変更なので省略しない)
- 比較基準: P0 の SHA と作業ツリー(未コミット分を含む)。対象: 3 章の全ファイル。文脈: 0000・0002・本プラン・P0〜P6 の作業記録、設計 E 3.3〜3.6
- `code-reviewer` の観点: Nginx 設定(location 優先順・`add_header` 継承・`resolver`・`proxy_pass` の URI・タイムアウトと本文上限)、Dockerfile の固定と層キャッシュ、compose の公開範囲、C の撤去の網羅と SSRF 予防、OpenAPI の不変性、README の正確さ
- `test-reviewer` の観点: 単体テスト置換の網羅、R9 変更の妥当性、AIT-93 と `ComposeControl` 許可リスト追加の安全性、test_01 の前提記述
- `web-ui-reviewer` は省略(画面・コンポーネント・スタイルの変更がなく、`apps/web` の変更は配信設定とコメントのみ。描画は P5 で確認)
- 完了条件: 指摘なし、または Critical / Important がすべて解消

## 6. 指摘対応

Critical / Important は impl が修正し、影響フェーズの検証(ruff・pytest、P5 該当項目、IT)をやり直し、同じレビュアーで再レビュー。Suggestion / Nitpick は対応可否を判断して理由を記録。

## 7. タスクレビュー

実施する(複数フェーズ・複数セッション、公開範囲という高リスクの変更、0000 の「(a) は後続タスク」とのずれの整理があるため)。5 章のレビューと指摘対応の作業記録ができてから実行。観点は要件・プラン・作業記録・実変更の突き合わせ(完了条件 13 項目、P-1〜P-10 の遵守、申し送りの記録)。Critical / Important が解消するまで完了にしない。

## 8. 完了条件との対応

| 完了条件(0000) | フェーズ |
| --- | --- |
| `/admin/` 配信・SPA・assets 404・リダイレクト | P1・P5-2 |
| `/api/` 素通し・書き込みと読み取り | P5-3・4 |
| `api` 非 publish・`web` だけ `127.0.0.1` | P3・P5-1 |
| `api` 未起動でも nginx 起動・停止中は HTML 502/504 | P1・P5-8 |
| 1 MiB 超の JSON 400・`proxy_read_timeout` | P5-7・9 |
| `%2F`・`%2E` の `job_id` | P5-6 |
| EP-13 の `web` normal/abnormal・OpenAPI 差分なし | P2・P4(AIT-01・93)・P5-5 |
| 撤去の grep | P2・P6 |
| api の ruff・pytest | P2(指摘対応のたびに再実行) |
| IT が通る | P4 |
| README の記述 | P6 → レビュー |
| 数値・環境変数名・healthcheck・既定ポートの記録 | P1・P2・P5 の作業記録 |
| 未対応事項の記録 | 最終の作業記録 |

## 9. リスクと対策

- IT・P5 が `web` のビルド(npm レジストリ接続)に依存 → `npm ci` 層のキャッシュ、IT README に前提明記、失敗原因を記録
- 9200 を Fess が使用 → 他コンテナを止めず待つか、実行不可の理由と P5 の代替を記録
- 8090 使用中 → P0 で確認しユーザーに既定値を確認
- 停止時の `reason` が環境で分かれる → 両方許容し `[observed]` で記録(AIT-90〜92 と同じ)
- `%2F`・`%2E` が保持されない → 直さず記録しユーザー判断
- `"missing"` 削除で OpenAPI が変わる → 残す(P-4)。P2 の diff で検出
- AIT-93 後に `web` が戻らない → `stopped()` が必ず `start` して healthy を待つ。test_90 は最後に実行
- `wget` がイメージから消える → P1 で確認、前提を Dockerfile コメントに記載
- `api` の IP 変更後の名前解決キャッシュ → `valid=10s`。P5-8 で再起動後の復旧確認
- P5 が既存環境を壊す → 専用プロジェクト名・事前確認・`down -v` はそのプロジェクトのみ

ロールバック: 未コミットなので `git restore`・`git clean` で P0 の SHA に戻す。ローカルイメージは `docker image rm`。コミット後は B と C を同じ範囲で revert する。

## 10. 申し送り(最終の作業記録に書く)

- 設計書の追従改訂: HO-59(A 本文。静的配信を `web` が担う)、HO-60(B 8.1・10.2 など。`ComponentId` の説明・`web` 判定)、HO-65(C・D の `admin/` 設計書)
- 本タスクで決めた値の設計への反映: `LORELEY_API_WEB_URL`(必須・確認先 `/admin/`)、healthcheck の手段、`WEB_HOST_PORT=8090`、Nginx 最終値、Node・Nginx イメージ、FARC-U-6・21 と HO-53〜58 の状態更新(api-base-design 9 章、E 3.3・3.6・12.4)
- `ProbeReason` の `"missing"` の廃止(OpenAPI 変更を伴うため別タスク)
- セキュリティヘッダー(CSP 等)と `/favicon.ico` の扱い
- `web` 経由の接続確認の自動テスト(`tests/integration/<名前>/` 新設。設計 F 7.1。フロント実装後)
- IT の固定ポートが 5 つ(8090 追加)になったことの設計への反映(HO-56 の補足)
- 0000 の「(a) は後続タスク」とのずれ: IT の範囲は P-1 で解消し、`web` 経由の自動テストだけ後続に残す(承認時にユーザーに確認)
