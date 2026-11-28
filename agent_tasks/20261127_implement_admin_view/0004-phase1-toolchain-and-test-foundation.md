# 0004 フェーズ 1: ツールチェーン・型生成・テスト基盤の土台

作成日: 2026-11-27 / 工程: 実施(フェーズ 1 完了)
ブランチ: `feature/implement-admin-view` / 比較基準: `8a20d67` / 終了時 HEAD: `5ab0c1a`(本記録のコミットは含まない)

## 1. 実施した作業の概要

0002 フェーズ 1 + 0003 の差分に従い、依存の追加、OpenAPI 書き出しと型生成(`gen:api` / `gen:api:check`)、ESLint の依存ルール(R1〜R17)、Prettier、Vitest(jsdom)・Playwright の基盤、方式確認スパイク、Dockerfile の更新を実装した。`code-implementer` が実装し、`code-reviewer`・`test-reviewer` を 3 回(初回 + 再レビュー 2 回)並列に実施して、Critical・Important が解消するまで修正した。

途中でユーザー確認が 1 回あった(`npm audit` の 9 件)。回答は **B(`overrides` を追加)**。

## 2. コミット

| コミット | 内容 |
| --- | --- |
| `35b20ef` | 実装(ツールチェーン・型生成・テスト基盤) |
| `33e6f32` | レビュー指摘の修正 1(依存ルールの穴・E2E の未モック検出の誤検出) |
| `5ab0c1a` | レビュー指摘の修正 2(依存ルールの行列テスト・`tsconfig.test.json` の分離) |

## 3. 変更ファイル(`apps/web/` 配下。生成物 17 ファイルを除く。計 47 ファイル)

追加: `eslint.config.js`、`.prettierrc`、`.prettierignore`、`openapi-ts.config.ts`、`openapi/admin-v1.json`、`scripts/gen-api.sh`、`scripts/gen-api-check.sh`、`playwright.config.ts`、`tsconfig.test.json`、`src/admin/api/generated/**`(17 ファイル。手編集なし)、`tests/support/{setup,mount,e2eTest,unmockedApi,eslintInstance}.ts`、`tests/support/{environment,unmockedApi,dependencyRules,dependencyMatrix}.test.ts`、`tests/e2e/smoke.spec.ts`
変更: `package.json`、`package-lock.json`、`vite.config.ts`、`tsconfig.json`、`tsconfig.app.json`、`tsconfig.node.json`、`Dockerfile`、`.dockerignore`、`.gitignore`、`src/main.ts`(暫定の `eslint-disable` コメントのみ)、`src/admin/router/PlaceholderPage.vue`(Prettier 整形のみ)
変更していない: `nginx/`、`deploy/compose/`、`apps/api` ほか。

## 4. 検証結果(メインエージェントが再実行。Node 24.22.3 / npm 11.19.1)

| コマンド | 結果 |
| --- | --- |
| `npm ci` / `npm audit` | 警告 0 件 / **0 件**(`overrides` 後) |
| `npm run gen:api:check` | 成功。ファイルの追加・削除・内容差で失敗(終了コード 1)することを確認。生成は 17 ファイル、`baseUrl=/api/admin/v1` |
| `typecheck`(app・test・node の 3 本)・`lint`・`format:check`・`build` | 成功 |
| `npm run test` | 4 ファイル 211 件成功(3 回連続で安定、約 6〜7 秒) |
| `npm run test:e2e` | 5 件成功(専用ポート 15173) |
| `docker build -t loreley-web-check apps/web` | 成功(確認後にイメージを削除) |

ホストの Node は 25.2.1(`.nvmrc` は 24.15.0)のため、nodejs.org の `node-v24.22.3-darwin-x64.tar.gz`(SHA256 照合済み)を scratchpad に展開して使った。Playwright も Node 24 で実行した。

## 5. 実装時確認事項の結果(FARC-U / FMOD-U)

| ID | 結果 |
| --- | --- |
| **FARC-U-9**(jsdom か Browser Mode か) | **jsdom 31 + Vitest 5.1.2 で Vuetify 4.3.4 が動く。Browser Mode は不要**。`VDataTableServer`・`VDialog`・`VNavigationDrawer` がマウントできる(`environment.test.ts`)。必須の対処が 3 つ: `window.visualViewport` のスタブ、`ResizeObserver` のスタブ、Vitest の **`test.fsModuleCache: false`**(既定の true だと、2 回目以降の実行で `vite-plugin-vuetify` の仮想モジュール `virtual:plugin-vuetify:…VApp.sass` が読めず全テストが落ちる)。`server.deps.inline: ['vuetify']` と併用。相対 `baseUrl` の `Request` は下記 FMOD-U-12 |
| **FARC-U-25**(`npm ci`・audit・peer) | E 2.1 の版で `npm ci` の peer・engines・deprecated 警告は 0 件。警告は `vue-demi` の postinstall 未指定のみ(`allowScripts` に `"vue-demi": false` で解消)。`npm audit` は E 2.1 のままだと 9 件(devDependencies の推移的依存のみ。`--omit=dev` は 0 件)。ユーザー回答 B により `overrides`(`js-yaml` 4.3.2・`minimatch` ^11.0.9・`glob` ^14.0.6)で 0 件。Hey API 0.99.0 での生成結果は `js-yaml` 4.2.0 のときと `diff -r` で完全一致。`@vue/test-utils` の `html()` は glob 14・minimatch 11 で動く |
| **FMOD-U-1**(R1〜R17 を `no-restricted-imports` で表せるか) | **表せる**(追加ライブラリ不要)。flat config は同じ規則を複数ブロックが設定すると後勝ちで**置換**されるため、**1 ファイルにつき設定ブロック 1 つのゾーン表方式**とした。`import type` だけ許す例外は `allowTypeImports`。「配下の一部だけ許す」例外(R9 の `queries/mutations`、R10 の `queries/meta`)は否定パターンで書けず正規表現で表した。R3・R14 は `no-restricted-globals`・`no-restricted-properties`・`no-restricted-syntax`。`ImportExpression`(動的 import)は `no-restricted-imports` が見ないため `no-restricted-syntax` で禁止 |
| **FMOD-U-12**(相対 `baseUrl` の `Request`) | jsdom でも `new Request('/api/…')` は `TypeError`(`Request` は Node の undici のもので `location` を使わない)。`tests/support/setup.ts` で `client.setConfig({ baseUrl: 'http://localhost/api/admin/v1' })` に上書きする(設計の退避策)。生成直後の `baseUrl === '/api/admin/v1'` は `vi.resetModules()` で別に検証。`client.ts` にテスト用の形は持たせていない |
| FARC-U-2(一部) | `VDataTableServer` の `@update:options` は初期に 1 回発火(`{page:1, itemsPerPage:25, sortBy:[], groupBy:[]}`)。`aria-sort` はソート指定のない列で属性なし。単一ソート・`hover` は未確認(フェーズ 3・7) |
| FARC-U-8 | Playwright の設定のみ。相対 `goto` の確認はフェーズ 3 |
| FARC-U-5 | 生成物は決定的で `gen:api:check` で確認(17 ファイル、約 111KB の想定どおり) |

## 6. 設計との差異(設計書は改訂しない。Q2。追従は別タスクへ申し送り)

1. **`overrides` の追加**(`js-yaml`・`minimatch`・`glob`)と `allowScripts` の `"vue-demi": false`: ユーザー回答 B。**撤去条件**: `js-yaml` は Hey API(`@hey-api/json-schema-ref-parser`)が 4.2.0 を exact 固定しているため、上流が修正版に上げたら外す。`minimatch`・`glob` は `@vue/test-utils` → `js-beautify` 経由で、上流が修正版に上げたら外す。
2. **Vitest の `test.fsModuleCache: false` と `visualViewport` スタブ**: 設計 E 10.1 にない、jsdom 上の Vuetify に必須の対処(上記 FARC-U-9)。
3. **Playwright の `webServer`**: 専用ポート 15173、`--strictPort`、`reuseExistingServer: false`、`LORELEY_DEV_API_TARGET=http://127.0.0.1:1`。設計 E 10.2・F の `baseURL`・`webServer`(5173・`reuseExistingServer: !process.env.CI`)との差異(0003 4 章で計画済み)。
4. **`gen:api:check`**: Git に依存しない一時ディレクトリ比較(0003 2 章)。E 11.2 の `git diff --exit-code` とは異なる。`uv run --locked` で `uv.lock` を書き換えない。
5. **設計に無い規則**: `src/` 非テストでの `../` を含む相対 import の禁止(層をまたぐ import を `@/` に統一)、`process`・`Buffer` の禁止、動的 `import()`・`import.meta.glob` の禁止(FMOD-P-17)、`@/admin/api/**` の深い import の禁止(E 11.1・F R17 注記の機械化)、`@typescript-eslint/no-import-type-side-effects`、包括ゾーン(どのゾーンにも属さない `src/` のファイルを違反にする)。
6. **許可範囲**: 設計 F 1.2 の「主な入力」を許可リストとして扱い絞った(features→shell 不可、shell は composables・queries/meta・lib・shared・api の型のみ、router は templates・lib・features・shared・composables のみ、router・app の `.vue` から vuetify 禁止)。code-reviewer の指摘で、設計が禁止していない dialogs→composables、router→composables、shell→api の型だけは許可に戻した。「同じ層の相互 import は原則不可」(F 2.2)による禁止(dialogs→templates など)は、設計が明記したものではなく保守的な判断で、必要になれば足す。
7. **`tsconfig.test.json` の分離**: `tsconfig.app.json` は `types: ["vite/client"]`、テストは `types: ["vite/client", "node"]`。`typecheck` は app → test → node の 3 本。設計(F 2.4)に明記なし。
8. **`setup.ts` の生成クライアント import**: 公開口 `@/admin/api` がまだ無いため相対パスで import(理由付き `eslint-disable`。公開口が `client` を再 export したら切り替える)。`src/main.ts` の暫定 `eslint-disable` も、フェーズ 3 の作り直しで削除する。
9. `Dockerfile` の `COPY` に `openapi-ts.config.ts`・`playwright.config.ts`・`tests/`・`tsconfig.test.json` を追加(`vue-tsc` が検査するため)。`.dockerignore` に `test-results/`・`playwright-report/`。

## 7. レビュー結果

- 初回(`8a20d67..35b20ef`): code-reviewer は Critical 0・Important 3(依存ルールの穴)、test-reviewer は Critical 1(未モック検出の glob が Vite のモジュール URL を誤検出)・Important 4。
- 修正 1(`33e6f32`)後の再レビュー: code-reviewer は Important 1(`tsconfig.app.json` の `node`)、test-reviewer は Important 1(依存ルールの表の網羅の穴。変異 39 件のうち生き残りあり)・Important 1(同上 tsconfig)。
- 修正 2(`5ab0c1a`)後の最終再レビュー: **両者とも Critical・Important なし**。test-reviewer の変異試験は新規 39 件中 38 件が検出。

指摘への対応(見送りの判断):

| 指摘 | 判断 |
| --- | --- |
| `forbidOnly: Boolean(process.env.CI)`(Nitpick) | 害がないので残す。CI 導入時のための設定 |
| 行列に `shared/theme/icons.ts` の行が無い(Suggestion。`icons.ts` に `@/admin/lib` を許す変異が通る) | **フェーズ 2 の最初に追加**する |
| 行列の `unclassified` 行の `unspecified` に `vueRouter`・`vueQuery`・`vuetify` が入っている(Nitpick) | フェーズ 2 で `vue` だけにして他を禁止にする |
| `tsconfig.test.json` が `src/**/*.d.ts` を含まない(Suggestion。`meta.d.ts` の `RouteMeta` 拡張がテストの型検査に入らない) | **フェーズ 3 で `src/admin/router/meta.d.ts` を足すとき**に include へ追加する |
| テストの型検査では `src/` の非テストにも Node の型が効く(`setTimeout` の戻り値が `Timeout` になる)(Suggestion) | **規約**として、タイマーは `window.setTimeout` / `window.setInterval`(または `ReturnType<typeof setTimeout>`)で書く。フェーズ 2 の実装で守る。必要なら ESLint で bare `setTimeout`・`setInterval` を禁止 |
| 包括ゾーンが `.d.mts`・`.d.cts` を例外にしていない(Nitpick) | 必要になったときに `'**/*.d.{ts,mts,cts}'` へ |
| `settings` の印(`loreley-zone:*`)への依存(Suggestion) | 記録のみ。ESLint の将来変更で壊れたらテストが落ちる |

## 8. 後続フェーズへの申し送り

- **フェーズ 2**: (1) `tests/support/e2eTest.ts`・`unmockedApi.ts` は URL の pathname で未モックを判定する。`mockApi.ts` のモックは `/api/admin/v1/…` までのパスで書く規約とし、`**/api/**` のような広い glob は使わない(Vite のモジュール URL と一致する誤検出が再発するため)。(2) `configureApiClient()` と `setup.ts` の絶対 `baseUrl` の上書きが衝突し得る(setup は全テストより先に走る)。`configureApiClient` が baseUrl を渡せる(未指定なら変更しない)設計にするか、フェーズ 2 で決める。本番の相対 `baseUrl` が実ブラウザで動くことは E2E でしか保証されない。(3) `fetchStub` はテスト後に fetch 設定を戻す後始末を持つ。(4) 公開口 `@/admin/api` が `client` を再 export したら、`setup.ts`・`environment.test.ts` の直接 import(理由付き `eslint-disable`)を切り替える。(5) 上記 7 章の行列テストの追加・修正。(6) タイマーの規約。(7) Playwright が `@/` の別名を解決するかは、e2e に型以外の `@/` import を入れるときに確認する。
- **フェーズ 3**: `src/main.ts` の暫定 `eslint-disable` を削除。`mount.ts` を本番の `setupVuetify` に差し替え(`mobileBreakpoint` を本番設定と一致させる)。`smoke.spec.ts` が `PlaceholderPage`(「Admin View(準備中)」)に依存しているため書き換える。`tsconfig.test.json` に `src/**/*.d.ts` を追加。`QueryClient` のテスト後 `clear()`。
- **フェーズ 11(README)**: `npm run test` は `apps/web` で実行する前提(リポジトリ直下から `vitest --root apps/web` は、`vite-plugin-vuetify` が cwd から vuetify を解決するため `NODE_PATH` が要る)。`gen:api`・`gen:api:check`・Playwright のブラウザ導入(`npx playwright install chromium`)を記載する。
- **設計書の追従改訂の申し送り候補**(別タスク): FARC-U-9 の結果(`fsModuleCache`・`visualViewport`)、`overrides`、Playwright の専用ポート、`gen:api:check` の方式、`../` 禁止ほか 6 章の規則、`tsconfig.test.json`。

## 9. 未対応事項

- 上記 7・8 章の申し送りのとおり(フェーズ 2・3・11 で対応)。
- `docker build` は実装担当・メインエージェントが実行して成功。reviewer は実行していない(読解のみ)。

## 10. 次のアクション

- フェーズ 2(データ取得層と純粋ロジック)を `code-implementer` に依頼する。開始時の比較基準は、本記録のコミットの SHA。
