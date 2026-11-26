# 0004 `apps/web` スキャフォールドの実装と検証

- 日付: 2026-11-26
- 実施: 実装は `code-implementer`、検証はメインエージェント(0003 のフェーズ 2・3)

## 実施内容

`apps/web` に最小スキャフォールドを作った(すべて新規・未コミット)。

- ルート: `package.json`、`package-lock.json`、`.nvmrc`(24.15.0)、`.npmrc`(`engine-strict=true`)、`.gitignore`(`node_modules/`・`dist/`・`*.tsbuildinfo`・`vite.config.ts.timestamp-*`)、`index.html`(`lang="ja"`)、`vite.config.ts`、`tsconfig.json`・`tsconfig.app.json`・`tsconfig.node.json`、`README.md`
- `src/main.ts`(`vuetify/styles` を先頭で import → Vuetify・Router → マウント)、`src/admin/app/App.vue`、`src/admin/router/index.ts`(`createWebHistory(import.meta.env.BASE_URL)`・1 route)、`src/admin/router/PlaceholderPage.vue`、`src/shared/theme/settings.scss`(`@use 'vuetify/settings';` のみ)

## 決定事項

- dev プロキシ: `/api` → 既定 `http://127.0.0.1:8090`。上書きは環境変数 **`LORELEY_DEV_API_TARGET`**(`VITE_` なし。空文字は未設定扱い)
- 検証用 Node: `docker run node:24`(v24.22.3、npm 11.19.1)。ホストの Node(25.2.1)は変えていない。`package-lock.json` はスクラッチ内で生成して反映

## 実際にインストールされた版(直接依存)

vue 3.5.46、vuetify 4.3.4、vue-router 5.5.2、@mdi/js 7.4.47、sass 1.108.2、vite 8.3.8、@vitejs/plugin-vue 6.0.11、vite-plugin-vuetify 2.1.3、typescript 6.0.3、vue-tsc 3.3.14、@types/node 24.19.4。vue-router だけ E 2.1 の確認版 5.5.1 より patch が 1 つ上(5.5.2)。範囲内で、問題なし。

## 検証結果(`docker run node:24`)

- `package.json`・`package-lock.json`・`.npmrc` だけをコピーしたディレクトリで `npm ci` が成功(警告・エラーなし、112 パッケージ、脆弱性 0)。そこから `npm run build` も `.npmrc` の `engine-strict=true` のまま成功
- `npm audit`: 0 件
- `npm run typecheck`・`npm run build`: 成功。`dist/index.html` が直下。`dist/assets/index-*.js`・`index-*.css`。`index.html` のアセット URL は `/admin/assets/…`
- 外部参照(googleapis・gstatic・cdn・jsdelivr・unpkg・`@import url`・`url(http`)の grep: `dist/` で 0 件
- dev サーバー: `/admin/` が 200、`/admin` が 404(設計どおり)。ダミーの HTTP 待ち受け(127.0.0.1:9999)を `LORELEY_DEV_API_TARGET` で指定し、`/api/v1/ping` が転送先に届いた(`DUMMY /api/v1/ping`)
- ブラウザ(playwright-cli、`/admin/`): 「Admin View(準備中)」「管理画面はこれから実装します。」が描画され、コンソールのエラー・警告 0 件
- `node:25`(v25.9.0)で `npm install`: `EBADENGINE` 相当の `npm error notsup`(Required `^22.22.2 || ^24.15.0 || >=26`)で失敗(`engine-strict` が効く)
- ホストの `apps/web` に `node_modules`・`dist` は作っていない(`git status` は `?? apps/web/` のみ)。検証用のスクラッチ・コンテナは削除した

## 設計との乖離・追加(実装者の判断。レビューに回す)

1. `typecheck` を `vue-tsc --noEmit -p tsconfig.app.json && vue-tsc --noEmit -p tsconfig.node.json` にした。`tsconfig.json` が references のみで、`vue-tsc --noEmit` だけだと何も検査しないため。`build` は `npm run typecheck && vite build`(要件の「vue-tsc --noEmit → vite build」と同等で、表記だけ異なる)
2. `package.json` に `allowScripts: {"@parcel/watcher": false}` を追加。npm 11.19.1 が `@parcel/watcher`(sass の依存)の install script について出す警告を消すため。build に影響なし(元々実行されていなかった)。要件の「警告なし」を満たすための追加
3. `@` エイリアス(`vite.config.ts` と tsconfig の `paths`)。F の案に沿う
4. route コンポーネントを `src/admin/router/` に置いた(F の `router/` 配下)

設計書(E・F)との矛盾は見つかっていない。

## 未対応事項・次にやること

- `code-reviewer` のレビュー(実施中)と、指摘の反映
- 完了後、`20261126_add_web_container_nginx` を再開する(`apps/web` の `Dockerfile`・`nginx/default.conf` は B+C で作る)
- 上の 2(`allowScripts`)は、設計 E に反映するかを別途検討(npm のバージョンで警告が変わる点)
