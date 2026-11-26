# 0007 P3: compose(`web` サービスの追加・`api` の `ports` 削除)

- 日付: 2026-11-26
- 実施: メインエージェント(1 ファイル+ `.env.example` の軽微な変更のため直接実施)

## 変更ファイル

- `deploy/compose/compose.yaml`
  - `web` サービスを追加: `build: ../../apps/web`、`ports: "127.0.0.1:${WEB_HOST_PORT:-8090}:80"`、`depends_on: api: service_healthy`、`restart: unless-stopped`。healthcheck はイメージの `HEALTHCHECK`(`/admin/` の 200)を使う
  - `api` の `ports` を削除(ホストに publish しない)。`api` は `web` を `depends_on` に入れない
  - `api` の環境変数に `LORELEY_API_WEB_URL: http://web:80` を追加(必須の環境変数)
  - 冒頭コメントを更新: 構成に `web`、「公開範囲」を「ホストに publish するのは `web` だけ(`127.0.0.1`)」、`web` の認証なし・ブラウザ経由の書き込みへの保護なし(HO-40・41)、`api` は本番用で publish せず IT の上書きだけが publish する旨、起動順(`web` は `api` の healthy を待つ)
- `deploy/compose/.env.example`: `API_HOST_PORT=8080` を `WEB_HOST_PORT=8090` に置換

## 検証

- `docker compose -f compose.yaml config`: `api` に `ports` なし、`web` は `host_ip: 127.0.0.1`・`target: 80`・`published: "8090"`、`api` に `LORELEY_API_WEB_URL: http://web:80`
- 8090 は P0 で空きを確認済み(`WEB_HOST_PORT` の既定値は 8090 のまま)

## 未対応・次の作業

- `deploy/compose/README.md` の更新(`API_HOST_PORT` の行(50・113 行目)、既知事項(109 行目)ほか)は P6
- IT の `compose.test.yaml` は `api.ports` を足す必要がある(P4)
