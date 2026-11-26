# 0009 P5: 実機確認(Nginx → 実 api)

- 日付: 2026-11-26
- 実施: メインエージェント
- 環境: 専用プロジェクト名 `loreley-webcheck`、`deploy/compose/compose.yaml` のみで起動(`CRAWLER_DOCUMENTS_DIR` は scratchpad のダミー)。事前に 8090・8080・8000・8001・9200 が空き、同名の資源がないことを確認。終了後 `down -v` でこのプロジェクトだけを削除(ボリューム・ネットワーク・コンテナの残りなし。既存の停止中の `opensearch-opensearch-1` には触れていない)
- 注: 実機確認用の curl はホスト経由(`127.0.0.1:8090`)。`api` へは `docker compose exec api python` の `urllib`・`http.client`(コンテナ内の `127.0.0.1:8080`)で直接呼んだ

## 結果

| # | 項目 | 結果 |
| --- | --- | --- |
| 1 | `docker compose ps` / 公開範囲 | `api` は `8080/tcp` のみ(ホストに publish なし)、`web` は `127.0.0.1:8090->80/tcp`。ホストの `127.0.0.1:8080` は接続不可(curl `000`) |
| 2 | `/admin/` 系 | `/admin/` 200 `text/html` `no-cache`、`/admin/sources/xxx` 200 `no-cache`、`/admin` 301 `Location: /admin/`、`/admin/assets/nope.js` 404、`/` 302 `/admin/`、`/api` 301 `/api/`、`/healthz` 404 |
| 3 | `/api/admin/v1/meta` | 200 `application/json`、`cache-control: no-store` が素通し |
| 4 | 書き込み・読み取り | EP-03(`POST /sources`)201、EP-04(`PUT /sources/webcheck`)200(いずれも `no-store`)。EP-01・02(`/sources/webcheck`)・`/jobs`・`/opensearch/cluster`・`/dashboard` が 200 `application/json` |
| 5 | EP-13 の `web` | 起動中 `normal`。`stop web` 後、api 内から読むと `abnormal`・**`reason: name_not_resolved`**(ホストの 8090 は接続不可)。`start web` 後 `normal`(`web` は healthy)。`api` の `/healthz` はコンテナ内から `{"status":"ok"}` |
| 6 | `job_id` のパス(FARC-U-21) | `web` 経由(`curl --path-as-is`)と `api` 直(`http.client`、正規化なし)で **全件一致**: `.`・`..`・`%2E`・`%2E%2E`・`%3F`・`%23`・`x%3Fy`・存在しない ID は 404 `job_not_found`、`%2F`・`a%2Fb` は 404 `not_found`。Nginx 越しで `%2F`・`%2E` は保持される(ユーザー判断を要する差異なし) |
| 7 | 本文の上限 | EP-03 に対し、1 MiB ちょうど: `api` の JSON 400(検証エラー。サイズ上限内)、1 MiB+1: **`api` の JSON 400**(`invalid_request`。サイズ超過で details なし)、2 MiB ちょうど: `api` の JSON 400、2 MiB+1: **Nginx の HTML 413** |
| 8 | `api` 停止 | `stop api` で `/api/admin/v1/meta` は **HTML の 502**(`/admin/` は 200 のまま)。`api` を止めたまま `web` を再起動(`docker restart`)しても起動し、ログの `host not found in upstream` は 0 件。`start api` 後に `/api/` が 200 `application/json` に復旧 |
| 9 | `proxy_read_timeout` | `nginx -T`: `proxy_read_timeout 90s`・`proxy_connect_timeout 5s`・`proxy_send_timeout 30s`・`client_max_body_size 2m`。実測: `pause crawler` → `web` 経由の `POST /sources/webcheck/crawl-jobs` が **約 60 秒で `api` の JSON 504 `crawler_response_lost`(`outcome_unknown: true`)**。HTML の 504 ではない(`unpause` 済み) |
| 10 | ブラウザ(playwright-cli) | `http://127.0.0.1:8090/admin/` が描画される(タイトル `Loreley Admin`、「Admin View(準備中)」のプレースホルダー)。コンソールエラーは `/favicon.ico` の 404 の 1 件のみ(予想どおり) |
| 11 | dev サーバー → `web` → `api`(任意) | 未実施(任意。フロントの実装タスクで確認) |

## 補足(判明した事実)

- **compose v2.3.3 の `up -d --no-deps --force-recreate web` は、`depends_on`(`service_healthy`)の `api` も起動した**(停止中の `api` が起動して `meta` が 200 になった)。このため「`api` が停止中の `web` の起動」は `docker restart` で確認した(P1 でも、`api` のない一時ネットワークで `web` が起動することを確認済み)。README の確認手順には `--no-deps` を載せない
- `pause crawler` の後、`crawler` は一時的に `unhealthy` になった(`unpause` 後は回復する想定。`down -v` で削除したため回復の確認はしていない。本タスクの変更とは無関係の既存の挙動)

## 未対応・次の作業

- 11(dev サーバーの連鎖)は任意のため未実施。設計 3.4 の未確認点として、フロントの実装タスクへ申し送る
- P6(README・コメントの仕上げ)へ
