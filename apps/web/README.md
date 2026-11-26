# web

Loreley の Web UI(Admin View)。Vue 3 + Vuetify 4 + Vite の SPA で、`/admin/` 配下で配信する。

現在は最小のスキャフォールド(プレースホルダー 1 画面)。画面・API クライアント・テストなどは後続のタスクで実装する。設計は `docs/v0.x/system-design/ui-admin/frontend/` を参照。

## Node の版

Node は `.nvmrc` の版(24.15.0)に合わせる。`package.json` の `engines` は `^22.22.2 || ^24.15.0 || >=26`、`.npmrc` は `engine-strict=true` で、範囲外の Node(例: 25)では `npm install` / `npm ci` が失敗する。その場合は `.nvmrc` の版に切り替える。

```sh
nvm use   # または nodebrew / Docker の node:24 など
```

## コマンド

```sh
npm ci              # 依存のインストール(package-lock.json どおり)
npm run dev         # 開発サーバー: http://localhost:5173/admin/
npm run typecheck   # vue-tsc による型検査
npm run build       # 型検査 → vite build(成果物は dist/。index.html は直下)
npm run preview     # dist/ の確認
```

- 開発サーバーの URL は末尾スラッシュ付きの `/admin/`。`/admin`(スラッシュなし)は dev では 404 になる。
- `sass` は Vuetify の SASS 設定(`src/shared/theme/settings.scss`)に必要なため dependencies に入れている。

## 開発サーバーの `/api` の転送先

dev サーバーは `/api` を `http://127.0.0.1:8090`(compose の `web` コンテナの公開ポートの既定値)に転送する。`web` コンテナの追加(タスク `20261126_add_web_container_nginx`)の前は、この既定値の転送先には何も待ち受けていない。

転送先は環境変数 `LORELEY_DEV_API_TARGET` で上書きできる(クライアントに露出させないため `VITE_` は付けない)。`web` コンテナの追加前は、compose の `api` が `127.0.0.1:8080`(`API_HOST_PORT`)に publish されているので、それを指定する。追加後は `api` はホストに publish されなくなり、既定の `web` 経由になる。

```sh
LORELEY_DEV_API_TARGET=http://127.0.0.1:8080 npm run dev
```
