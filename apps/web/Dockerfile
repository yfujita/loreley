# Loreley web のコンテナイメージ(Admin View の静的配信と、/api/ の api への中継)。
# ビルドコンテキストは `apps/web`: docker build -t loreley-web apps/web
#
# 再現性のため、ベースイメージ(タグ+ダイジェスト)を固定している。
# Node のバージョンは `.nvmrc`(24.15.0)・`package.json` の `engines`(24 系は ^24.15.0)に合わせる
# (`.npmrc` の `engine-strict=true` により、範囲外の Node では `npm ci` が失敗する)。
# 依存は `package-lock.json` から入れる。Vite 8 のネイティブ依存は glibc 系と musl 系で
# 取得する成果物が変わるため、ビルドステージは Debian(glibc)系を使う。
# 型生成(`npm run gen:api`)はここでは行わない(生成コードはリポジトリにコミットされている)。
# 実行時(Nginx)は外部と通信しない(外部 CDN・外部フォントを参照しない成果物を配信する)。

# ベースイメージは 2026-11-26 に固定した(Node 24.22.3 は 2026-11-24 ビルド、
# Nginx 1.30.8 の stable 系は 2026-11-25 ビルド)。
# 古いタグのままだと、OS と OpenSSL などの脆弱性修正が入らないため。
# 運用: 定期的に再ビルドし、そのとき `24-bookworm-slim` と nginx の stable 系 `-alpine` の最新の
#   タグとダイジェストに更新する。Renovate / Dependabot などで自動化してもよい(任意)。
#   更新したら、ビルドと動作確認を通してから使う。
ARG NODE_IMAGE=node:24.22.3-bookworm-slim@sha256:873f586f3794f52281bd039bf02c048a0be08fde619338f9941bad1eb6b34530
ARG NGINX_IMAGE=nginx:1.30.8-alpine@sha256:8eb04fe3b385090e9aa02961f77398ad09b6bf33ab07f6669a5bb7acce22c0d3

# --- ビルドステージ: 依存を入れて dist/ を作る(最終イメージには Node を持ち込まない) ---
FROM ${NODE_IMAGE} AS builder

WORKDIR /app

# 依存だけを先に入れる。ソースを変えても、この層はキャッシュが効く。
# `npm ci`: `package-lock.json` のとおりに入れ、ロックが `package.json` と食い違うと失敗する。
# `.npmrc` を先にコピーするのは、`engine-strict=true` を `npm ci` に効かせるため。
COPY package.json package-lock.json .npmrc ./
RUN npm ci

# ビルドに要るファイルだけを個別にコピーする(`nginx/` の変更でビルドをやり直さないため)。
# ビルドに要るファイルが増えたとき(`public/` など)は、ここに足す。
# `npm run build` は `vue-tsc`(型検査)→ `vite build`。成果物は `dist/`(`index.html` が直下)。
COPY index.html vite.config.ts tsconfig.json tsconfig.app.json tsconfig.node.json ./
COPY src ./src
RUN npm run build


# --- 配信ステージ ---
FROM ${NGINX_IMAGE} AS runtime

# `dist/` は Vite の `base: '/admin/'` で作られ、アセットの URL が `/admin/assets/…` になる。
# Nginx の `root /usr/share/nginx/html` の下の `admin/` に置く。
COPY --from=builder /app/dist /usr/share/nginx/html/admin
# 公式イメージの `default.conf`(「Welcome to nginx」)を置き換える。
COPY nginx/default.conf /etc/nginx/conf.d/default.conf

# コンテナ内は 80。ホストへの公開(`127.0.0.1` のみ)は compose で行う。
# **/api/ を中継するため、認証なしの破壊的操作(設定の変更・ソースの削除など)がこのポートから
# 呼べる。ホストや外部に公開せず、`127.0.0.1` に限る**。
EXPOSE 80
# 公式の nginx イメージのまま、master プロセスは root で動く(80 番で待ち受けるため。worker は nginx ユーザー)。
# 公開は `127.0.0.1` のみに限る前提。将来、非 root にするときは `nginx-unprivileged`(8080 番)に変える。

# `/admin/` の 200 を確認する(`/healthz` は置かない)。同じ確認先を api の Dashboard(EP-13)の
# `web` の判定も使うため、ここが 200 でなければ `web` は異常と見なされる。
# `wget` は alpine イメージの busybox にあるので、追加のインストールは要らない。
# ホストは `127.0.0.1` 固定(`localhost` は IPv6 の `::1` に解決されうるが、Nginx は IPv4 だけで待ち受ける)。
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1/admin/"]
