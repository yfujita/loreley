# 20261126_scaffold_admin_web_app

## 背景・目的

Admin View のフロントエンド設計 v0.2(タスク `20261126_create_admin_ui_system_design`)は完了したが、`apps/web` はまだ存在しない。

タスク `20261126_add_web_container_nginx`(前提タスク B+C。`web` コンテナ(Nginx)の追加と `api` の `web` 判定の置換)は、`web` イメージのビルド(Node 24 でビルド → Nginx。設計 E 3.5)が `package.json` と `vite build` の通ることを前提にしている。設計 E 12.8・F 8.9 は、B+C の着手条件を「**フロントの最初のスキャフォールド**(`apps/web` の `package.json`・`vite build` が通る最小の構成)の後」と定めている。ユーザー判断(2026-11-26)で、このスキャフォールドを別タスクとして先に実施することにした。

本タスクの目的は、**`apps/web` に「`npm ci` と `vite build` が通る最小の構成」を作る**こと。画面・API クライアント・テストなどの実装は、後続のフロントの実装タスクの責務とする。

## 要件

### 現状(As-Is)

- `apps/web` は存在しない。設計(`docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.2.md`(以下 E)・`ui-admin-frontend-module-structure-v0.2.md`(以下 F))だけがある
- ホストの Node は 25.2.1(`nodebrew`)。設計の Node の範囲(`^22.22.2 || ^24.15.0 || >=26`。推奨は 24)の**外**で、`engine-strict=true` のため、そのままでは `npm install` が失敗する(E 2.2)
- リポジトリの `.gitignore` に `node_modules/`・`dist/` の記載はない

### あるべき姿(To-Be)

`apps/web` で次が成り立つ。

- Node 24 系(24.15.0 以上)で `npm ci` が警告(peer・engines・deprecated)・エラーなしに通り、`npm audit` の脆弱性が 0 件
- `npm run build`(`vue-tsc --noEmit` → `vite build`)が通り、`dist/index.html` が**直下**にでき、アセットの URL が `/admin/assets/…` になる
- `npm run dev` で `http://localhost:5173/admin/` を開くと、**プレースホルダーの 1 画面**(Vuetify のコンポーネントが 1 つ以上描画される)が表示される。`/api` は開発サーバーのプロキシで転送される
- `npm run typecheck` が通る
- 成果物(`dist/`)が外部 CDN・外部フォントを参照しない(設計 E 3.1)
- 後続のフロントの実装タスク(`src/` の本実装)と、前提タスク B+C(`Dockerfile`・`nginx/default.conf`・compose)が、この上に積める

### 具体的にやること

設計の「名前は案」(F 2.1)の範囲で、最小限のものだけを作る。ファイルの中身は E・F の要点(F 2.4)に従う。

**`apps/web` のルート直下**

- `package.json`: `name`・`private: true`・`type: "module"`。`engines.node` は `^22.22.2 || ^24.15.0 || >=26`。スクリプトは `dev`・`build`(`vue-tsc --noEmit` → `vite build`)・`preview`・`typecheck`。依存は下の「依存の範囲」のとおり。固定の範囲は E 2.1・2.2 に従う
- `package-lock.json`(コミットする。`npm ci` の入力)
- `.nvmrc`(Node 24 系。24.15.0 以上)、`.npmrc`(`engine-strict=true`)
- `index.html`(`<html lang="ja">`、外部リソースなし)
- `vite.config.ts`: `base: '/admin/'`、`@vitejs/plugin-vue`、`vite-plugin-vuetify`(`autoImport: true`、`styles: { configFile }`)、`build.target` は既定のまま、dev の `server.proxy`(下記)
- `tsconfig.json`・`tsconfig.app.json`・`tsconfig.node.json`: `strict: true`。`exactOptionalPropertyTypes` は**有効にしない**。`tsconfig.node.json` に `@types/node` と `"types": ["node"]`(`vite.config.ts` が `process.env` を読むため)
- `.gitignore`(`node_modules/`・`dist/` など。`apps/web` の中、またはリポジトリ直下のどちらか。既存の流儀を確認して決める)
- `README.md`(最小。Node の版の合わせ方(`.nvmrc`)、`npm ci`・`dev`・`build` の使い方、dev プロキシの転送先と上書き方法を書く。ホストの Node が範囲外のときの対処(`.nvmrc` の版に切り替える)を含める)

**`src/`(プレースホルダー)**

- `src/main.ts`: `import 'vuetify/styles'`(**必須**。E 3.1)→ Vuetify・Vue Router(`createWebHistory(import.meta.env.BASE_URL)`)の最小の組み立て → マウント
- `src/admin/app/App.vue` など: `VApp`・`VMain` などで「Admin View(準備中)」程度の 1 画面。`vite-plugin-vuetify` の tree-shaking が効いていることを、描画する Vuetify のコンポーネントで確認できればよい
- SASS の設定ファイル(`styles.configFile` が指す `src/shared/theme/settings.scss`)は、**変数を上書きしない最小の中身**(プレースホルダー)にする。DS 3.3 の値の反映は後続のタスク

**開発サーバーの転送先**(設計 E 3.4。HO-57)

- `server.proxy` で `/api` を転送する。既定の転送先は **`http://127.0.0.1:8090`**(`web` の公開ポートの既定値。前提タスク B+C の `WEB_HOST_PORT` の既定値と同じ)
- dev 専用の環境変数で上書きできるようにする。環境変数名は本タスクで決め、作業記録と README に残す(`VITE_` を付けない(クライアントに露出させない)ことを推奨)。B+C の前は、`api` を自分で publish した `http://127.0.0.1:8080` などに上書きして使う

**検証**

- Node 24.15.0 以上の 24 系で、クリーンな状態(`node_modules` なし)から `npm ci` → `npm run typecheck` → `npm run build` が通ることを確認する
- 成果物の確認: `dist/index.html` が直下にある。`dist/assets/` のハッシュ付き JS・CSS ができる。アセットの URL が `/admin/assets/…`。外部ドメイン(googleapis・gstatic・cdn・jsdelivr・unpkg・`@import url`・`url(http`)の参照が 0 件(grep で確認する)
- `npm run dev` で `http://localhost:5173/admin/` が表示される。ブラウザ(または curl)で、プレースホルダーの描画と、`/admin`(末尾スラッシュなし)が dev では 404 になること(設計どおり)を確認する。`/api/` が転送先に届くこと(転送先に何かを待ち受けさせて確認する。実際の `api` でなくてよい)
- 前提タスク B+C が使える形になっている確認: `npm ci` が `package.json`・`package-lock.json`・`.npmrc` だけで再現できる(Docker のビルドステージが先にコピーするファイルだけで `npm ci` できる)。`npm ci` の後に `npm run build` を `.npmrc` の `engine-strict=true` を効かせたまま通す

#### 依存の範囲

設計の確認(0005 の技術検証)で、**`npm install`・`npm ci` とも警告 0 件、`npm audit` 0 件**だった組み合わせは次の 11 個のパッケージだけ。本タスクの依存はこれに限る(E 2.1)。

| 区分 | パッケージ | 固定(E 2.1・2.2) |
| --- | --- | --- |
| dependencies | `vue` | `^3.5` |
| 〃 | `vuetify` | `4.3.4`(exact) |
| 〃 | `vue-router` | `~5.5`(minor 固定) |
| 〃 | `@mdi/js` | caret |
| 〃 | `sass` | caret(**dependencies に明記**。`styles.configFile` を使うと必須) |
| devDependencies | `vite` | `~8.3.8` |
| 〃 | `@vitejs/plugin-vue` | `~6.0.11`(patch まで) |
| 〃 | `vite-plugin-vuetify` | `~2.1.3`(patch まで) |
| 〃 | `typescript` | `~6.0.3` |
| 〃 | `vue-tsc` | `~3.3.14` |
| 〃 | `@types/node` | `^24` |

実際にインストールされる版は、**インストール時点の最新ではなく、設計の確認版(E 2.1)**から大きく外れないこと。外れる場合は、理由と版を作業記録に残す。

## 対象範囲

- `apps/web/` 配下の上記のファイル(ルートの設定ファイル・`index.html`・`src/` のプレースホルダー・`package-lock.json`・`README.md`)
- 必要なら、リポジトリ直下の `.gitignore`(`node_modules/`・`dist/`)
- (確認のための)`npm ci`・`typecheck`・`build`・`dev` の実行

## スコープ外

- `apps/web/Dockerfile`・`apps/web/nginx/default.conf`・`.dockerignore`・compose の `web` サービス・`api` の変更(前提タスク B+C。`20261126_add_web_container_nginx`)
- 型生成(`gen:api`・`@hey-api/openapi-ts`・`openapi/admin-v1.json`・`src/admin/api/generated/`・`openapi-ts.config.ts`)と API クライアント(`configureApiClient`)。前提タスク A(`20261126_fix_admin_openapi_types`)の完了後が望ましい
- `@tanstack/vue-query`・Vitest・jsdom・`@vue/test-utils`・Playwright・ESLint・Prettier・`typescript-eslint`・`eslint-plugin-vue` の導入と設定、これらのスクリプト(`test`・`test:e2e`・`lint`・`format`)。**Vite 系と同時に install した状態の `npm ci`・`npm audit` は未確認(FARC-U-25)のため、導入するタスクで確認する**
- 画面・ルート・シェル・テンプレート・テーマ(DS のトークン・SASS 変数の値)・ダイアログ・フィーチャーの実装(F 2.1 の `shared/ui`・`admin/shell`・`admin/features` など)
- 依存方向の機械検査(F 6 章。ESLint)・品質ゲート(E 11.2)・CI の設定
- 設計書の改訂(設計と矛盾が見つかった場合は、作業記録に残して別途申し送る)

## 制約・前提条件

- 設計(E・F)と矛盾しない。特に: Vuetify・Vite・TypeScript・Vue Router などの固定の範囲(E 2.1・2.2)、`base: '/admin/'`(E 3.1)、`vuetify/styles` の import(必須)、`sass` を dependencies に、`@types/node` を `^24`、`build.target` は既定、`exactOptionalPropertyTypes` は無効(E 3.1・11.1)
- Node は `.nvmrc`・`engines`・`.npmrc` の `engine-strict=true` で固定する。ホストの Node(25.2.1)は範囲外のため、検証は **Node 24.15.0 以上の 24 系**で行う(`nodebrew`・`nvm`・Docker の `node:24` のいずれかで用意する。ホストの Node を勝手に入れ替えない場合は、`docker run` で検証してもよい。方法は作業記録に残す)
- 実行時に外部通信しない(外部 CDN・外部フォントなし)。ビルド時の npm レジストリへの接続だけを許す
- 要件にない依存・機能を足さない(「入れないもの」: Pinia・Tailwind・vue-i18n・axios など。E 2.4)。本タスクの範囲外の依存は、後続のタスクで足す
- 本タスクのスキャフォールドは、後続の本実装でそのまま置き換え・拡張されるもの。過剰な作り込みをしない
- 前提タスク B+C(`web` イメージ)が `npm ci`・`vue-tsc`・`vite build` で `dist/` を作れる形にしておく。`Dockerfile` の中身は B+C が書く

## 完了条件

- [ ] `apps/web` に、上記のファイル(`package.json`・`package-lock.json`・`.nvmrc`・`.npmrc`・`index.html`・`vite.config.ts`・`tsconfig*.json`・`src/`・`README.md`・`.gitignore`)がある
- [ ] Node 24.15.0 以上の 24 系で、クリーンな状態から `npm ci` が警告・エラーなしに通り、`npm audit` が 0 件
- [ ] `npm run typecheck` と `npm run build` が通る。`dist/index.html` が直下にあり、アセットの URL が `/admin/assets/…`
- [ ] `dist/` に外部ドメイン・CDN・外部フォントの参照がない(grep で 0 件)
- [ ] `npm run dev` で `http://localhost:5173/admin/` にプレースホルダーが表示され、`/api` が転送先に届く(確認方法を作業記録に残す)
- [ ] 依存が上の「依存の範囲」の 11 個に限られ、固定の範囲が設計(E 2.1・2.2)と一致している。実際の版を作業記録に残す
- [ ] dev プロキシの既定の転送先が `http://127.0.0.1:8090` で、上書きの環境変数名が決まっている(README と作業記録に記載)
- [ ] `node_modules/`・`dist/` が git の管理外になっている(`git status` で確認)
- [ ] Node 25 など範囲外の Node で `npm install` が `engine-strict` により失敗することを確認している(または確認できなかった理由を作業記録に残す)
- [ ] 設計と矛盾・乖離が見つかった点(版の差、設定の不都合など)と、未対応事項を最新の作業記録に書いている

## 成果物

- `apps/web/` の最小スキャフォールド(上記)
- 作業記録(`agent_tasks/20261126_scaffold_admin_web_app/NNNN-*.md`)。実際にインストールされた版、環境変数名、検証に使った Node の用意の仕方、設計との乖離を含める

## 補足・参考情報

- 出典: E の 2 章(技術スタックとバージョン固定)・3.1(Vite の設定)・3.2(Router の `base`)・3.4(開発サーバー)・3.5(Docker のビルド)・11.1(静的解析)・12.8(前提タスクと依存)
- 出典: F の 2.1(ディレクトリ構成)・2.4(ルート直下の設定ファイル)・8.9(前提タスクへの依存)
- 調査の根拠: `agent_tasks/20261126_create_admin_ui_system_design/` の 0005(技術検証。Vite 8・Vuetify 4・`vite-plugin-vuetify`・`styles.configFile`・`vuetify/styles` の確認)
- 関連タスク: `20261126_add_web_container_nginx`(本タスクの後に着手。B+C)、`20261126_fix_admin_openapi_types`(前提タスク A。型生成の前に完了が望ましい。本タスクとは独立)
- 運用: dev プロキシの既定の転送先(8090)は、B+C の完了までは何も待ち受けていない。B+C の前は、`api` を自分で publish して(結合テストの `compose.test.yaml` の流儀。`127.0.0.1:8080`)上書きする

### 要確認(要件確認の工程でユーザーに聞く点。推奨案つき)

1. **依存の範囲**: 設計で警告 0 件・`npm audit` 0 件を確認した 11 パッケージだけにとどめ、Vitest・ESLint・Prettier・Hey API・Playwright・`@tanstack/vue-query` は後続の実装タスクで足す(推奨)。代案は、F 2.4 のスクリプト(`lint`・`test` など)の枠だけでも先に入れる(Vite 系との同時 install が未確認(FARC-U-25)なので、本タスクで確認する範囲が広がる)
2. **プレースホルダーの `src/`**: Vue Router を最小で組み込む(`createWebHistory`・1 route)か、Router なしで `App.vue` だけにするか。推奨は **Router を最小で組み込む**(`base: '/admin/'` と `import.meta.env.BASE_URL` の整合を本タスクで確認でき、後続が拡張しやすい)
3. **検証用の Node の用意**: ホストの Node は 25.2.1(範囲外)。`nodebrew` などで 24 系を入れて切り替えるか、`docker run node:24` で検証するか。推奨は **`docker run`(ホストの環境を変えない)**。ただし開発者のローカルでは `.nvmrc` の版に切り替える必要がある点を README に書く
4. **`.gitignore` の置き場**: `apps/web/.gitignore` とする(推奨。`apps/api` などの流儀に合わせる。実装時に既存の置き方を確認する)か、リポジトリ直下に足すか
