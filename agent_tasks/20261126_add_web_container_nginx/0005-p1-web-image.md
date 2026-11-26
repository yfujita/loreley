# 0005 P1: `web` イメージ(Dockerfile・Nginx 設定)

- 日付: 2026-11-26
- 実施: code-implementer(実装・検証)→ メインエージェントが再ビルドして再確認

## 変更ファイル(新規)

- `apps/web/.dockerignore`
- `apps/web/Dockerfile`(2 ステージ。ビルドに要るファイルを個別に `COPY`。`public/` などが増えたら足す旨をコメントに記載)
- `apps/web/nginx/default.conf`

## 確定したイメージ(2026-11-26 に固定。マニフェストインデックスのダイジェスト)

- Node: `node:24.22.3-bookworm-slim@sha256:873f586f3794f52281bd039bf02c048a0be08fde619338f9941bad1eb6b34530`(`.nvmrc` 24.15.0 以上に適合。glibc 系)
- Nginx: `nginx:1.30.8-alpine@sha256:8eb04fe3b385090e9aa02961f77398ad09b6bf33ab07f6669a5bb7acce22c0d3`(stable 系。設計 0005 の確認は mainline 1.31.10 だったが、同じ設定が 1.30.8 でも通ることを確認)

## healthcheck

`CMD ["wget","-q","-O","/dev/null","http://127.0.0.1/admin/"]`、`--interval=15s --timeout=5s --start-period=10s --retries=3`。`wget` は busybox 版でイメージに標準で入っている(`curl` もある)。`127.0.0.1` 固定(`localhost` は IPv6 に解決されうるが Nginx は IPv4 のみ待ち受け)。`/healthz` は置かない。

## Nginx の最終値

0003 の P-7 の値をそのまま採用(`proxy_connect_timeout 5s`・`proxy_send_timeout 30s`・`proxy_read_timeout 90s`・`client_max_body_size 2m`・`gzip_min_length 1024`・`resolver 127.0.0.11 valid=10s ipv6=off`・`absolute_redirect off`・`Host $http_host`・`add_header` は location ごとで `always` なし・セキュリティヘッダーなし・`/healthz` `/favicon.ico` の location なし)。

P-7 から変えた点(2 つ):

1. **gzip の範囲**: `gzip on` を `server` ではなく `/admin/assets/` の location 内に置いた(`server` に置くと `/api/` の JSON 応答も圧縮されるため。要件は assets への gzip のみ)。`gzip_types` は設計 3.3 の 5 種
2. **`gzip_vary on` を追加**(`/admin/assets/` 内のみ)。長期キャッシュのファイルが gzip の有無で別表現になるため、中間キャッシュに非圧縮版が入るのを避ける。不要なら 1 行削除可

実装メモ: `/admin` は `location = /admin { return 301 /admin/; }`、`/` は `location = / { return 302 /admin/; }`。`/api`(スラッシュなし)は明示の location を置かず Nginx 既定の 301 に任せた(クエリも保持される)。`resolver`・`set $api_upstream` は `/api/` の location 内。

## 検証結果

実装担当(一時 user-defined network。ホストのポート公開なし)の結果:

- `docker build apps/web` 成功(`npm ci`・`npm run build`)、`nginx -t` OK
- `api` が存在しない状態で起動し healthy。`host not found in upstream` で落ちない。`/api/` は HTML の 502。後から `api` というスタブを起動すると再起動なしで名前解決された
- `/admin/` 200・`text/html`・`no-cache`、`/admin/sources/xxx` 200(index.html)、`/admin/assets/<実在>` 200・`public, max-age=31536000, immutable`・`Content-Encoding: gzip`・`Vary: Accept-Encoding`、`/admin/assets/存在しない.js` と `/admin/assets/` は 404(`Cache-Control` なし)、`/admin` 301 `Location: /admin/`、`/` 302、`/api` 301 `Location: /api/`、`/healthz` 404、`/favicon.ico` 404、`/admin/favicon.ico` 200(index.html。許容)
- スタブ `api` 経由: `Cache-Control: no-store` の素通し、`Host` がポート付きで渡る、`/jobs/a%2Fb`・`/jobs/%2E%2E`・`/jobs/..`・`/jobs/x%3Fy?z=1` の元 URI がそのまま渡る(実 `api` での確認は P5)
- 本文サイズ(スタブ `api` の上限 10m): 1,100,000 バイトと 2 MiB は通り、2 MiB+1 は Nginx の HTML 413(1 MiB 超の `api` JSON 400 は P5 で確認)
- `nginx -T`: `proxy_read_timeout 90s`・`client_max_body_size 2m`
- `dist/` に外部 URL(googleapis・cdn・jsdelivr・unpkg・`@import url`)なし(`http://www.w3.org` の XML 名前空間 4 件と `https://vuejs.org` のエラーメッセージ 1 件のみ。通信しない)
- 一時コンテナ・ネットワーク・ローカルイメージは削除済み。既存の `opensearch-opensearch-1`・`opensearch_default` には触れていない

メインエージェントの再確認: 再ビルド成功、`nginx -t` OK、`api` なしで起動して `/admin/`・`/admin/x/y` が 200 `no-cache`、`/admin` 301→200、`/api` 301→502、`/healthz` 404、`/api/admin/v1/meta` 502。後始末済み。

## 未対応・次の作業

- 実 `api` との結合(`job_id` の `%2F`・`%2E`、1 MiB 超の JSON 400、`api` 停止後の復旧、`/favicon.ico` のコンソールエラー)は P5
- ホスト公開・`depends_on`・`WEB_HOST_PORT` は P3、`/admin/` を確認先にした EP-13 の判定は P2
- 設計書への申し送り: Nginx は stable 1.30.8 を採用、gzip の範囲と `gzip_vary`、セキュリティヘッダー・`/favicon.ico` は未対応
