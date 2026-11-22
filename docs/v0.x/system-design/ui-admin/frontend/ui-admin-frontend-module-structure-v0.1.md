# ui-admin フロントエンドモジュール構成設計書 v0.1

- 版: v0.1(ドラフト。E(`ui-admin-frontend-architecture-v0.1.md`)と B 本文に基づく。ゲート3(2026-11-23)の承認を反映済み。実装はスコープ外で、実装時確認事項(FMOD-U)が残る)
- 更新日: 2026-11-23
- 前版: なし(初版)
- 位置づけ: Admin View(`apps/web/`)のコード上の**モジュール分割・ディレクトリ・依存ルール・画面とモジュールの対応**を定める。「何を、どのモジュールが担うか」を一目で分かるようにする。技術構成・データ取得の方針・エラー処理の UI 対応・テスト方針は E、見た目・部品の仕様は DS と画面仕様、EP・DTO・エラー code は B が正本で、本書は**参照して置き場を決める**(再掲しない)。
- 本書は **Admin 画面の詳細設計タスク(`20261122_create_admin_system_design`)の成果物**で、SD・PD・DS・画面仕様・A・B・E を変更しない。E・B に直してほしい点があれば 8.7 に「修正依頼」として挙げる(現在は修正依頼なし)。既存設計との食い違いは `I-n`(8.5)に挙げる。追従改訂が要る点は A の 9章(HO-1〜HO-50。本書に関わるものは HO-27)に集約し、本書は申し送りを持たない。
- 改訂履歴: v0.1 は初版(フェーズ3-2)。E 12.6 の「F への引き継ぎ」と、0013・0015 の追加の引き継ぎ(パスエンコード、`unavailable` を引く関数、番兵日時、S4 のしきい値の丸め注意、ルート遅延読み込みの判断)を、すべて 8.6 の表で割り当てた。R3 の指摘(区分の統一、`viewState`・パンくず・`featureFlag`・ロック状態の置き場、依存ルールの整合、I-104 の解消ほか)に対応した。フェーズ5の統合(2026-11-23): 申し送りへの参照を A 9章の実番号に置き換え、関連文書の表に C・D を足し、更新日を統一した。R4 指摘の反映(2026-11-23): FARC-K-8 の参照を FARC-P-38 に直し、FMOD-K-2 から「コード・設定ファイルは作らない」を外した(確定にせず FARC-P-38 に従う)。 ゲート3の承認(2026-11-23)の反映: 案の区分を承認済みの案(ゲート3。2026-11-23)に更新した(設計の内容は変更なし)。PR #10 のレビュー指摘への対応(2026-11-23。0037・0038): 一覧の `unavailable` を行単位にする B の変更(AAPI-P-42)に追従した(3.5 の `unavailable.ts` を行・最上位の 2 系統に、3.9・5.5・7 章。FMOD-P-14・31 を修正、FMOD-P-33 を新設。区分は承認済みの案(ゲート3)の修正で、`-K-` は増やしていない)。

区分の凡例(A・B・E と同じ。`crawler-api-v0.4.md` に合わせる):

| 区分 | 意味 |
| --- | --- |
| 確定 | ユーザーが明示的に回答・確定した事項(出典を書く)、または確定として書かれた既承認文書(DS・画面仕様・SD・PD・機能設計・crawler / indexer 設計)の引用 |
| 案 | ユーザーが承認していない提案。確定(`-K-`)にしない。本書で新たに決めた判断は、ゲート3(2026-11-23)で承認され、すべて承認済みの案になった(本文中で「案」と書いた判断は、ID の区分欄が正で、承認済みの案(ゲート3)に読み替える) |
| 承認済みの案 | ゲート1・ゲート2(2026-11-22。ユーザー承認)、またはゲート3(2026-11-23。ユーザー承認)で承認されたもの。既承認文書(DS・画面仕様)の「承認済みの案」「承認済み」の引用で、本タスクのユーザー確認がないものも確定にせず、この区分とし、出典を区分欄に書く |
| 未決 | 決めていない。実装時に確認するものを含む |
| 推測 | 根拠が弱い想定 |
| 導出 | 他の記述から導いた事項 |

ID 体系: `FMOD-K-n` / `FMOD-P-n` / `FMOD-U-n`。既存設計との不整合は `I-n`(本書の予約範囲は I-100〜109 と I-130〜139。E は I-80〜89 と I-120〜129、B は I-70〜79、A は I-60〜69、C は I-90〜99、D は I-110〜119)。E の ID は `FARC-*`、A は `BAPI-*`、B は `AAPI-*`、エンドポイントは B の `EP-nn`。DS・画面仕様の節は `DS 4.5`・`sources 2.3` のように書く。

関連文書(いずれも `docs/v0.x/` 配下):

| 略称 | 文書 | 本書との関係 |
| --- | --- | --- |
| E | `system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.1.md`(v0.1。作成済み) | 技術構成・データ取得層・エラー処理・テスト方針の正本。本書は置き場を決める |
| B | `system-design/api/admin/admin-api-v0.1.md`(v0.1。作成済み) | EP・DTO・code の正本。1.3 の画面×EP 対応表と 4章を突き合わせた |
| A | `system-design/api/api-base-design-v0.1.md`(v0.1。作成済み) | 静的配信・URL・エラー形式。9章が申し送り(HO-1〜)の置き場 |
| C・D | `system-design/api/admin/admin-api-architecture-v0.1.md`、`admin-api-module-structure-v0.1.md`(いずれも v0.1。作成済み) | Admin API の内部設計。本書は EP・code の結果だけを使い、内部には依存しない |
| DS | `ui-design/design-system-v0.1.md` | 共通コンポーネント(4章)・シェル(5章)・テンプレート(6章)・`data-testid`(9章) |
| admin-view・画面仕様 | `ui-design/admin-view-v0.1.md`、`ui-design/admin/*.md` | route `meta`(4.2)・画面ごとの部品・状態・`data-testid` |

---

## 1. 概要

### 1.1 設計の考え方(前提: FMOD-P-26・FMOD-K-2・FMOD-K-3・FMOD-K-4)

- **層で分ける**。下の層は上の層を知らない。データ取得(`api`・`queries`)と見た目(`components`・`templates`)と画面(`features`)を混ぜない(2章・6章)。
- **画面は薄く**する。画面は「どのデータを、どの部品に、どの状態で見せるか」だけを持ち、取得・エラーの変換・検証・URL の読み書きは下の層の共通部品に任せる(E 1.2。対応表を 1 か所に持つ)。
- **DS の共通コンポーネントはすべて決まった場所に置く**(3.6)。画面固有の組み合わせだけを `features` に置く。
- **Search View と共有できる層を分ける**(DS 11)。共有するのはトークン・Vuetify `defaults`・共通の状態表示と、API 共通のエラーの形だけ。Search View は設計しない(境界だけ)。

### 1.2 モジュール表

`apps/web/src/` 配下。上の行ほど上位の層(2.2 の層番号)。

| モジュール | 層 | 役割 | 主な入力 | 主な出力 |
| --- | --- | --- | --- | --- |
| `admin/app` | 7 | アプリの組み立て(Vuetify・Query・Router の登録、`App.vue`、マウント) | 各モジュール | 起動した SPA |
| `admin/router` | 6 | route 定義(`meta`)、`navGroups`、ガード(MVP は遷移後の処理だけ。認証・`featureFlag` の評価はない)、`RouteMeta` の型 | `features` のページ | `Router` |
| `admin/features/*` | 5 | 画面(D1・S1〜S4・J1・J2・X1・O1)。ページ・画面の composable・画面固有の部品・定義表・フォームモデル | `queries`・`dialogs`・`components`・`templates`・`lib` | 画面 |
| `admin/dialogs` | 4 | 複数の画面から開く操作ダイアログ(DLG-1〜5・削除の再実行)と、その状態機械 | `queries`(書き込み)・`components` | ダイアログ |
| `admin/shell` | 4 | サイドバー(外部リンク領域と `featureFlag` の評価を含む)・上部バー・スキップリンク。パンくずの組み立て(`useBreadcrumbs`)を `PageHeader` に provide する | `composables`・`queries/meta`・`vue-router` | シェル |
| `admin/templates` | 3 | ページテンプレート 4 型、`PageHeader`(パンくずは inject)、操作の出し分け(`PageActions`)。状態は `viewState` を props で受ける | props・inject | ページの骨格 |
| `admin/components` | 3 | DS 4章の共通部品のうち Admin 専用のもの | props | 部品 |
| `admin/queries` | 2 | key factory・読み取りの composable・書き込み(mutation)・invalidate の表・ポーリング・Query の既定値 | `admin/api` | Query の結果 |
| `admin/composables` | 2 | 汎用の composable(URL ↔ 条件、要素の幅、debounce、タイトル、`useBreadcrumbs`、`useViewState`) | vue・vue-router・`admin/api/errors`・`lib` | composable |
| `admin/api` | 1 | 生成コード・API ラッパー・エラー変換表・パスエンコード | OpenAPI 生成物、`shared/api` | 型付きの SDK 関数、`ApiError`、`describeError` |
| `admin/lib` | 1 | 純粋な関数・型(`unavailable` の参照・セルの表示状態、番兵日時、検証規則、単位・丸め、route 名の定数、`ViewState`・`lockStateView`・inject の key) | — | 値 |
| `shared/ui` | 0 | Search View と共有できる共通部品(`StatusTag`・状態ブロック・アラート・フォーム項目・スナックバー) | props | 部品 |
| `shared/theme` | 0 | トークン(色・variables)・Vuetify `defaults`・`display`・SASS・アイコン | — | `createVuetify` の設定 |
| `shared/api` | 0 | `ApiError` の型と正規化(A 5.2 の形) | `fetch` の結果 | `ApiError` |
| `shared/lib` | 0 | 日時・数値の整形 | — | 文字列 |

---

## 2. 構成

### 2.1 ディレクトリ構成(承認済みの案(ゲート3)。FMOD-P-1)

名前は案(コード・設定ファイルは本タスクで作らない)。`@` は `src` の別名(案)。

```text
apps/web/
├─ index.html                      # <html lang="ja">。外部リソースなし(E 3.1)
├─ package.json / package-lock.json
├─ vite.config.ts                  # base '/admin/'、vuetify プラグイン、dev proxy、Vitest 設定
├─ tsconfig.json / tsconfig.app.json / tsconfig.node.json
├─ eslint.config.js / .prettierrc / .prettierignore     # 依存ルールは 6章
├─ openapi-ts.config.ts            # Hey API の設定
├─ playwright.config.ts            # baseURL は http://localhost:5173/admin/(E 10.2)
├─ openapi/
│  └─ admin-v1.json                # app.openapi() の書き出し(コミット。E 5.2)
├─ src/
│  ├─ main.ts                      # admin/app を起動するだけ
│  ├─ shared/                      # ── Search View と共有できる層(層 0)──
│  │  ├─ theme/                    # tokens.ts・defaults.ts・display.ts・icons.ts・settings.scss・global.css
│  │  ├─ ui/                       # StatusTag・statusMaps・StateBlock・PageAlert・FormField・ErrorSummary
│  │  │                            # AppSnackbar・useSnackbar・TopProgress・IdText・TimeText
│  │  ├─ api/                      # apiError.ts(ApiError・normalizeError)
│  │  └─ lib/                      # datetime.ts・number.ts
│  └─ admin/                       # ── Admin View 専用 ──
│     ├─ app/                      # App.vue・setupVuetify.ts・setupQuery.ts・setupRouter.ts
│     ├─ router/                   # routes.ts・navGroups.ts・guards.ts・scroll.ts・meta.d.ts・NotFoundPage.vue・index.ts
│     ├─ shell/                    # AppShell.vue・SideNav.vue・MobileAppBar.vue・SkipLink.vue・ExternalLinks.vue・externalLinks.ts
│     ├─ templates/                # ListPage.vue・DetailPage.vue・FormPage.vue・DashboardPage.vue・PageHeader.vue・PageBreadcrumbs.vue・PageActions.vue
│     ├─ components/               # DS 4章の Admin 専用部品(3.6 の表)。部品ごとに 1 ディレクトリ
│     ├─ dialogs/                  # crawl-start/・source-delete/・job-cancel/・job-rerun/・lock-release/・useOperationDialog.ts
│     ├─ features/
│     │  ├─ dashboard/             # D1
│     │  ├─ sources/               # S1・S2・S3・S4
│     │  ├─ jobs/                  # J1・J2
│     │  ├─ documents/             # X1
│     │  └─ opensearch/            # O1
│     ├─ queries/                  # keys.ts・queryClient.ts・polling.ts・placeholder.ts・invalidation.ts
│     │                            # meta.ts・dashboard.ts・sources.ts・jobs.ts・documents.ts・opensearch.ts・mutations/
│     ├─ composables/              # useListParams.ts・useContainerWidth.ts・useDebouncedRef.ts・useDocumentTitle.ts・useBreadcrumbs.ts・useViewState.ts
│     ├─ api/                      # generated/(Hey API 出力。手で編集しない)・client.ts・pathParams.ts・index.ts
│     │  └─ errors/                # errorTable.ts・describeError.ts
│     └─ lib/                      # unavailable.ts・expectedFields.ts・leaseExpiry.ts・routeNames.ts・actions.ts・units.ts・lockStateView.ts・viewState.ts・injectionKeys.ts・validation/
└─ tests/
   ├─ support/                     # setup.ts・mount.ts・fetchStub.ts・mockApi.ts・apiErrors.ts・fixtures/
   └─ e2e/                         # *.spec.ts(Playwright)
```

- **ファイル名**: Vue の部品は `PascalCase.vue`、composable は `useXxx.ts`、それ以外は `camelCase.ts`、ディレクトリは `kebab-case`(承認済みの案(ゲート3)。FMOD-P-24)。
- **単体テストは対象の隣**(`*.test.ts`。7章)。
- **生成コード**(`src/admin/api/generated/`)と `dist/` は lint・format の対象外(E 11.1)。

### 2.2 層と依存の向き(詳細は 6章)

```text
層 7  admin/app
層 6  admin/router ──▶ features の各ページ
層 5  admin/features/*   (features どうしは import しない)
層 4  admin/dialogs        admin/shell
層 3  admin/components     admin/templates
層 2  admin/queries        admin/composables
層 1  admin/api            admin/lib
層 0  shared/{theme,ui,api,lib}      ← Search View と共有できる
```

- 上の層は下の層だけを import する(同じ層のモジュールどうしは原則 import しない。6章の例外を除く)。
- `shared/` は `admin/` を import しない(将来 `search/` が同じ `shared/` を使える)。
- `queries` は UI を知らず、`components`・`templates` はデータ取得を知らない。画面(`features`)と `dialogs` が両者を結ぶ。

### 2.3 Search View との境界(FMOD-P-2)

- **共有する**: `shared/theme`(トークン・`defaults`・`display`・SASS・アイコン。DS 11)、`shared/ui`(`StatusTag` と `statusMaps`、状態ブロック、アラート、フォーム項目、スナックバー)、`shared/api`(API 共通のエラーの形。A 5.2)、`shared/lib`。
- **共有しない(Admin 専用)**: シェル(サイドバー)、テンプレート 4 型、データテーブル(行の操作つき)、危険度別の確認ダイアログ、`KeyValueList`(DS 11)、`admin/` 配下すべて。
- Search View の配置・同一ビルドにするか・`search/` の構成は決めない(FARC-U-17。FMOD-U-7)。

### 2.4 ルート直下の設定ファイル(名前だけ。FMOD-P-25)

E の要点に対応する。`package.json`(`engines`・スクリプトは E 11.1)、`vite.config.ts`、`tsconfig*.json`、`eslint.config.js`、`.prettierrc`、`openapi-ts.config.ts`、`playwright.config.ts`、`openapi/admin-v1.json`(E 5.2)。中身は実装で書く。

---

## 3. モジュール詳細

### 3.1 `shared/theme`

| ファイル | 内容(正本) |
| --- | --- |
| `tokens.ts` | `theme.themes.light.colors`(DS 2.1 の色名と値。独自の色名 `*-container`・`on-*-container`・`focus`・`ink`・`line-strong` を含む。DS 3.1・3.4)・`variables`(`border-color`・`border-opacity`・`medium-emphasis-opacity`。DS 3.1) |
| `defaults.ts` | Vuetify の `defaults`(DS 3.2 の表) |
| `display.ts` | `display.mobileBreakpoint: 'md'`(DS 3.1・7。実機確認は FARC-U-14) |
| `icons.ts` | 使う `@mdi/js` のアイコンを**ここだけ**で名前付き import して再 export。`mdi-svg` の iconset 設定(DS 3.1。FMOD-P-23) |
| `settings.scss` | `vite-plugin-vuetify` の `styles.configFile`(DS 3.3)。`$body-font-family` など |
| `global.css` | フォーカスリング・役割名のタイポグラフィのクラス(`text-page-title` など。DS 2.2・2.6)・`prefers-reduced-motion` |

`createVuetify` の組み立ては `admin/app/setupVuetify.ts`(`shared/theme` を読むだけ)。Search View も同じ 3 ファイルを読む。

### 3.2 `shared/ui`・`shared/api`・`shared/lib`(`shared/api` は FMOD-P-3)

| モジュール | 内容 | 根拠 |
| --- | --- | --- |
| `StatusTag.vue`・`statusMaps.ts` | `kind`(`job`・`source`・`health`・`deletion`・`cluster` ほか)と `value` を受け、**1 つのマップ**から色・アイコン・形・文言を引く。未登録の値は中立+開発時に警告。値の追加は行を足すだけ | DS 4.1 |
| `StateBlock.vue` | 空・エラー(データなし)・見つかりません・読み込み中(スケルトン)の共通ブロック。`role`・`aria-busy`・視覚的に隠した文言を持つ | DS 4.5。E 6.2 |
| `PageAlert.vue` | 左帯つきのページ内・ダイアログ内アラート(`info`・`warning`・`error`。`role` を props で切替) | DS 4.7 |
| `FormField.vue`・`ErrorSummary.vue` | ラベル上・「必須」表示・ヘルプ・検証エラー(`aria-invalid`・`aria-describedby`)、エラー要約(件数つき・項目へのリンク) | DS 4.6 |
| `AppSnackbar.vue`・`useSnackbar.ts` | アプリで 1 つの `VSnackbar`(同時に 1 つ、新しい通知で置き換え)と、呼び出しの composable(モジュール内の `ref`。永続化なし) | DS 4.7。E 4.2・8章 |
| `TopProgress.vue` | カード上端の進行バー(再取得中) | DS 4.5 |
| `IdText.vue`・`TimeText.vue` | 識別子(等幅・折り返し可)、日時(`<time>`。ブラウザのローカル時刻) | DS 4.9 |
| `shared/api/apiError.ts` | `ApiError`(E 5.3 の概形)と、`fetch` の結果・例外から作る `normalizeError`。A 5.2 の形(`error.code`・`retryable`・`details`)を読む | E 5.3。A 5.2 |
| `shared/lib/datetime.ts` | `YYYY-MM-DD HH:mm`(秒が要る箇所だけ `:ss`)で `Intl.DateTimeFormat` により整形(ブラウザのローカル時刻。日時ライブラリを足さない) | DS 4.9。E 5.9(FARC-P-24) |
| `shared/lib/number.ts` | 3 桁区切り・「—」の扱い | DS 4.9 |

### 3.3 `admin/api`(生成コード・ラッパー・エラー。FMOD-P-3・FMOD-P-6)

| ファイル | 内容 |
| --- | --- |
| `generated/` | Hey API の出力(型・SDK 関数・Query 用の `xxxOptions`)。**`admin/api` の外から import しない**(R2)。置き場は 1 か所に固定し、再生成の差分をレビューする(FARC-P-6) |
| `client.ts` | 生成クライアントの設定(`baseUrl='/api/admin/v1'`・`throwOnError`・クライアント側タイムアウト 読 45 秒・書 90 秒)と、失敗を `ApiError` に正規化して送出する薄いラッパー(E 5.3。FARC-P-7)。`baseUrl` を設定する**唯一の場所** |
| `pathParams.ts` | パスの値のエンコード(下の「パスエンコード」) |
| `index.ts` | **公開口**。生成された SDK・型のうち使うものだけを再 export し、`pathParams` を通した呼び出しにする。`queries` と `tests` は `@/admin/api` だけを import する |
| `errors/errorTable.ts` | **エラー変換表**(E 6.3 の表をデータにしたもの): `code`(と `lock_state` などの `details`)→ 表示先(項目別・ダイアログ内アラート・状態ブロック・成功扱い)・variant・再試行の可否・結果不明。Admin 固有 14 種+共通 6 種を網羅する(B 2.3。E 10.1 のテストの正) |
| `errors/describeError.ts` | `ApiError` と文脈(読み取り・書き込み・フォーム・ダイアログの種類)から、`errorTable` を引いて**表示の記述**(`{ target, variant, retryable, outcomeUnknown, fieldErrors, diagnostic }`)を返す純関数。画面は結果を表示するだけ |

**パスエンコード(FARC-U-18 に対する承認済みの案(ゲート3)。FMOD-P-4)**: `job_id`・`source_id` は **`admin/api` の層で保証**する。

- **理由**: `job_id` は検証が緩く(`%`・`?`・`#`・`.` を含みうる。B 2.12)、画面・Query・テストが直接 URL を組み立てると、保証が散るため。パス値の組み立ては `pathParams.ts` の 1 関数に集約する。
- **手順**: (1) 生成 SDK がパスの値をどうエンコードするかを実装時に確認する(FMOD-U-2)。(2) `encodeURIComponent` で足りない文字(`.`・`!`・`'`・`(`・`)`・`*`)を `pathParams.ts` が補う。SDK が既にエンコードするなら二重にならないよう、SDK の設定(パスのシリアライザ)側で一元化する。(3) 契約テスト(7章)で、`job_id='a%b?c#d'` などを渡した実際のリクエスト URL を検証する。
- **`.`・`..` だけの ID**: ブラウザの URL の正規化でパスが変わるため(`%2e%2e` も `..` として扱われる。推測)、取得を行わず「見つかりません」と同じ扱いにする(案。FMOD-U-9)。
- `/` を含む ID は Admin API が 404 `not_found` を返す(B 2.12)。E 6.2 のとおり「見つかりません」の扱い。

### 3.4 `admin/queries`(FMOD-P-5。FARC-P-8・11・27 の置き場)

読み取りも書き込みも、**サーバーとのやりとりはすべてここ**に置く(画面・ダイアログは `queries` の composable だけを呼ぶ)。

| ファイル | 内容 | EP |
| --- | --- | --- |
| `queryClient.ts` | `QueryClient` の既定値(E 5.4。`retry` 1(`timeout` は再試行しない)・`staleTime` 0・フォーカス・再接続での再取得なし・**マウント時は再取得**・mutation の再試行なし・グローバル通知なし) | — |
| `keys.ts` | **key factory**(E 5.4 の表。`['meta']`・`['dashboard']`・`['sources', 'list' または 'detail' または 'edit', id]`・`['jobs', 'list' または 'detail', …]`・`['documents', sourceId, params]`・`['opensearch', 'cluster']`)。生成 `queryKey` は使わず上書きする | — |
| `polling.ts` | `refetchInterval`: D1 の 30 秒(スイッチ連動)・J2 の関数(`queued`・`running` のときだけ 10 秒。E 5.5) | — |
| `placeholder.ts` | `placeholderData` の関数(**同じスコープの**ページ・並べ替えの変更だけ前回データを保持。E 5.6) | — |
| `invalidation.ts` | **invalidate の表**(E 5.8)。操作 → prefix の配列を 1 か所に持ち、mutation が呼ぶ | — |
| `meta.ts` | `useMetaQuery`(`staleTime: Infinity`。FARC-P-25)、`useDashboardsUrl`・`useCronTimezone`(失敗は `null` と同じ) | EP-14 |
| `dashboard.ts` | `useDashboardQuery(autoRefresh)` | EP-13 |
| `sources.ts` | `useSourcesListQuery`・`useSourceDetailQuery(id)`・`useSourceEditQuery(id)`(`gcTime: 0`・`staleTime: Infinity`。E 5.8。FARC-P-12) | EP-01・02 |
| `jobs.ts` | `useJobsListQuery(params)`・`useJobDetailQuery(id)`(ポーリング) | EP-09・10 |
| `documents.ts` | `useDocumentsQuery(source, params)`(`source` 未選択は `enabled: false`) | EP-11 |
| `opensearch.ts` | `useOpenSearchClusterQuery` | EP-12 |
| `mutations/createSource.ts`・`updateSource.ts` | S3・S4 の保存 | EP-03・04 |
| `mutations/startCrawl.ts` | クロールの起動(DLG-1 と DLG-4 の再実行が**共有**) | EP-06 |
| `mutations/deleteSource.ts` | ソース削除ジョブの起動(DLG-2 と削除の再実行が共有) | EP-05 |
| `mutations/cancelJob.ts`・`releaseLock.ts` | 取消・ロック解放 | EP-07・08 |

- 各 composable は `computed(() => xxxOptions({ … }))`(E 5.9)で生成された `xxxOptions` を包み、key を key factory で上書きする。引数は**型付きの条件**(URL から導いた `params`。3.5)。
- `queries` は `vue-router`・UI・`admin/components` を import しない(URL を直接読まない。条件は引数で受ける)。
- mutation は「実行 → 成功時に `invalidation.ts` の表で invalidate」までを担い、**成功後の遷移・スナックバー・ダイアログの開閉は呼び出し側**(`dialogs`・`features`)が決める。

### 3.5 定義表・共通ロジックの置き場(E 12.6 の引き継ぎ 5。FMOD-P-12・FMOD-P-13)

「対応を 1 つの表(データ)に持ち、画面で分岐を散らさない」(E 1.2)ための置き場を決める。

| 定義表・ロジック | 置き場 | 内容・規則 |
| --- | --- | --- |
| route 定義(`meta`) | `admin/router/routes.ts` | admin-view 4.2 の表をそのまま。`name` は `admin/lib/routeNames.ts` の定数 |
| `navGroups` | `admin/router/navGroups.ts` | DS 5.3 の定義表(`overview`・`operate`・`inspect`)。新しいグループは 1 行足す |
| route 名の定数 | `admin/lib/routeNames.ts` | features が `routes.ts` を import せずに遷移できるようにする(循環を避ける。R8) |
| 外部リンクの定義表 | `admin/shell/externalLinks.ts` | route を持たない外部リンク項目(MVP は OpenSearch Dashboards 1 件。`id`・表示名・アイコン・URL の取得元(`/meta` の `dashboards_url`)・`featureFlag`)。`SideNav` の外部リンク領域が描き、**`featureFlag` の評価はここだけ**(E 4.2・4.5。I-89。FMOD-P-29) |
| ロック状態の写像 | `admin/lib/lockStateView.ts` | `lock.state` 7 値+取得失敗 → S2 のロック状態カードの 6 種+取得失敗(E 5.10。FARC-P-34)。S2 の `LockStateCard`・J2 の `LockCard`・DLG-1 の拒否表示が共有する(features どうしを import しないため `lib`。FMOD-P-30) |
| `RouteMeta` の型 | `admin/router/meta.d.ts` | E 4.3 の概形(`title` は `string \| (route) => string`。I-83) |
| `dashboardComponents` | `features/dashboard/dashboardComponents.ts` | D1 の 8 コンポーネント(`id`・役割・必須/任意・導線。dashboard 3.2)。タイルはこの表から描く |
| `documentTabs` | `features/documents/documentTabs.ts` | 4 タブ。**URL の `id`(kebab)↔ API の `tab`(snake)**(I-85)・ラベル・列定義・並べ替え可能な列・既定の並び・注記・空状態の文・件数の取得(documents 5章) |
| URL ↔ API の対応(一覧の条件) | `features/{jobs,documents,opensearch}/*Params.ts` | 画面ごとの条件の定義(URL のキー・API のキー・既定値・正規化・`push`/`replace`)を、`composables/useListParams` に渡す。E 5.6 の対応表の実体 |
| フォーム `field` 対応 | `features/sources/form/fieldMap.ts` | API の `details.errors[].field`(`ttl_days`・`ttl_seconds`・`ratio_threshold_percent`・`min_delete_count`・`schedule_cron`・`source_id`・`connector_config.root`・`connector_config.include_patterns[i]` …)→ 入力欄・行。表にない `field`(`connector_config` 自身を含む)は上部アラート(E 6.4) |
| `unavailable` を引く関数 | `admin/lib/unavailable.ts` | 下の「`unavailable` の参照」 |
| 番兵の日時 | `admin/lib/leaseExpiry.ts` | 下の「番兵の日時」 |
| 失敗理由・警告・削除結果のコードの日本語表記 | `features/jobs/catalogs/`(`failureReasons.ts`・`warningCatalog.ts`・`deletionStatus.ts`) | jobs 2.5・2.7・2.9 の表。**未知のコードは一般的な文言**(B 5.2) |
| 画面の検証規則 | `admin/lib/validation/`(`rules.ts`・`patterns.ts`) | 項目 → 規則の表と純関数(E 7.1)。パターンの最大 100 件・1,024 バイトは仮値として 1 か所の定数(`limits.ts`) |
| 単位変換・丸め | `admin/lib/units.ts` | 日 ↔ 秒の表示、しきい値の桁判定と丸め(E 7.3・7.7) |
| 操作の出し分けの型 | `admin/lib/actions.ts` | `ActionSpec`(`id`・`label`・`visible`・`disabledReason`・`level`)。`PageActions` が描き、画面ごとの表(`sourceActions.ts`・`jobActions.ts`)が返す(DS 4.13) |

**`unavailable` の参照(`admin/lib/unavailable.ts`。FMOD-P-14)**:

- **行の `unavailable`(一覧の EP。EP-01・09・11。FMOD-P-33)**: `rowUnavailableReason(row, path)` は、各 `items[i]` の `unavailable`(常に存在)を**行内の相対パス**(EP-01: `last_crawl`・`last_crawl.stalled`・`last_completed_at`・`delete_job`・`delete_job.stalled`・`document_count`、EP-09: `stalled`、EP-11: `existence`)で引き、理由コードまたは `undefined` を返す。**取得できなかったか否かは、その行の `unavailable` のキーだけで判定する**(他の行の失敗に影響されない)。
- **最上位の `unavailable`**: `topUnavailableReason(response, path)` は、最上位の `unavailable` を応答の項目の**正式なパス**で引く。単一の応答(EP-02・10・12・13・14)は `index.document_count`・`deletion.current`・`last_crawl.stalled`・`lock` など。一覧の EP の最上位は**行に属さない項目だけ**(EP-11 の `tab_counts.<タブ>`・`document_count`。EP-01・09 では常に `{}`)。
- 旧規則の `isRowUnavailable`(一覧でキーがあり行が `null` なら取得できません)は**廃止**した(行ごとに失敗を区別できるため。AAPI-P-42)。
- `cellState(unavailable, path, value, { expected })`: セルの表示状態を返す(E 5.9 の (a)・(b)。FMOD-P-31)。`unavailable` は**引く対象の 1 つの `unavailable` オブジェクト**で、呼び出しは薄い 2 つのラッパー `rowCell(row, path, value, opts)`(行の `unavailable`)と `topCell(response, path, value, opts)`(最上位)を通す。`value` があれば `value`。`null` でその `unavailable` にキーがあれば `unavailable`(「—」+「取得できません」)。キーがなく `null` のとき、`expected=true`(`JobBrief` の `status`・`job_type`・`trigger`・`queued_at`、`registration` の件数・`partial`・`phase` など、値があるはずの項目)なら `unreadable`(「—」+視覚的に隠した「読み取れません」)、`expected=false`(`started_at`・未実行の `last_crawl` など)なら `none`(「—」+「なし」。`last_crawl` は「未実行」)。`expected` の項目の一覧は 1 つの表(`admin/lib/expectedFields.ts`)に持つ。`unavailable` の見える文言の有無は画面仕様に従う(表のセルは視覚的に隠した「取得できません」、S2 のカードは見える文言。E 5.9)。
- 画面は `unavailable` を直接読まず、これらの関数だけを使う(行の関数と最上位の関数を取り違えないよう、一覧の行には `rowCell`、単一の応答・一覧の最上位には `topCell` を使う)。理由コードは画面では区別しない(E 6.2。`malformed` だけ S4 で扱いが違う)。パスの文字列は定数にまとめ、B の変更に追従する場所を 1 か所にする。

**番兵の日時(`admin/lib/leaseExpiry.ts`。FMOD-P-15)**:

- 409 の `details.existing_job.lease_expires_at` は、Crawler が日時として読めないときだけ `0001-01-01T00:00:00.000Z` を返す(B 2.11・I-73)。`formatLeaseExpiry(iso)` が番兵を判定し、**「期限切れ」の値**を返す(日時として整形しない)。`null` は「期限なし(実行待ち)」で別。
- `lease_expires_at` を表示する箇所(DLG-1 の `lock_held`・DLG-5 の `lock_in_use`・S2 のロック状態カード・J2 の概要)は、すべて `formatLeaseExpiry` を通す。一般の日時整形は `shared/lib/datetime.ts`。S2 の `lock.job.lease_expires_at` は読めなければ `null` で、番兵は出ない(B 3.2)。

### 3.6 DS 共通コンポーネントの置き場(全件。FMOD-P-7)

規則: **DS 4 章に名前・仕様がある部品は、使う画面が 1 つでも `admin/components/`(または共有できるものは `shared/ui`)に置く**。画面固有の「組み合わせ」だけを `features` に置く。

| DS | 部品 | 置き場 | 使う画面 |
| --- | --- | --- | --- |
| 4.1 | `StatusTag`・状態のマップ | `shared/ui/StatusTag.vue`・`statusMaps.ts` | D1・S1・S2・J1・J2・O1 |
| 4.2 | ボタン(primary・tonal・outlined・text・danger・warning) | 部品なし。`shared/theme/defaults.ts` と色トークン(danger・warning は theme の色名) | 全画面 |
| 4.3 | データテーブル(`VDataTable`・`VDataTableServer`) | `admin/components/data-table/`(`AdminDataTable.vue`・`AdminDataTableServer.vue`・`RowActions.vue`・`columnPriority.ts`) | S1(client)・J1・X1(server) |
| 4.3 | 列の省略 | **J1 だけ**カード幅(コンテナクエリ・`ResizeObserver`。`admin/composables/useContainerWidth.ts`)で決める。**S1・X1 は viewport 基準**(`useDisplay`)のまま(DS 4.3 の区別)。画面ごとの列定義は `features/*/columns.ts` | J1(カード幅)・S1・X1(viewport) |
| 4.4 | `KeyValueList` | `admin/components/key-value-list/` | S2・J2 |
| 4.5 | 空・エラー・読み込み・古いデータ | `shared/ui/StateBlock.vue`・`TopProgress.vue`・`PageAlert.vue`(stale)。状態の決定(Query の結果+`describeError` → `viewState`)は `features` の composable が `admin/composables/useViewState.ts` で行い、`templates` は `viewState` だけを受けて描く(E 4.4・6.2。FMOD-P-27) | 全画面 |
| 4.6 | フォーム項目・検証エラー・エラー要約 | `shared/ui/FormField.vue`・`ErrorSummary.vue` | S3・S4・DLG 入力確認 |
| 4.7 | アラート・スナックバー | `shared/ui/PageAlert.vue`・`AppSnackbar.vue`・`useSnackbar.ts` | 全画面 |
| 4.8 | 確認ダイアログ(通常・標準・警告つき・要入力確認) | `admin/components/confirm-dialog/`(`ConfirmDialog.vue`・`ConfirmCheck.vue`・`TypeToConfirm.vue`・`dialogLevel.ts`=最も重い指定の色の規則) | `dialogs/*` |
| 4.9 | 日時・数値・識別子 | `shared/ui/TimeText.vue`・`IdText.vue`・`shared/lib/{datetime,number}.ts` | 全画面 |
| 4.10 | `StatList`(件数ブロック) | `admin/components/stat-list/` | J2(登録結果)・O1(概況の小型版は `ClusterSummary` が使う) |
| 4.11 | `WarningList` | `admin/components/warning-list/` | J2 |
| 4.12 | `FilterBar` | `admin/components/filter-bar/` | J1・X1 |
| 4.13 | 操作の出し分け | `admin/lib/actions.ts`(型)・`admin/templates/PageActions.vue`(描画)・`features/*/*Actions.ts`(表) | S2・J2 ほか |
| 4.14 | `CountTabs` | `admin/components/count-tabs/` | X1 |
| 4.15 | `ShardMatrix`(+凡例・ページ送りバー・列見出し) | `admin/components/shard-matrix/`(`ShardMatrix.vue`・`ShardLegend.vue`・`ShardPager.vue`・`ShardChip.vue`・`columnsPerPage.ts`) | O1 |
| 4.15 | `ClusterSummary`(概況) | `admin/components/shard-matrix/ClusterSummary.vue` | O1 |
| 4.15 | `IndexFilter`(絞り込みフォーム) | `admin/components/shard-matrix/IndexFilter.vue`(`FilterBar` の変種。DS 4.12・4.15 と同じ位置づけ) | O1 |
| 4.16 | `SummaryBand`・`ComponentTile` | `admin/components/dashboard-parts/` | D1 |
| 4.17 | `AutoRefreshSwitch` | `admin/components/auto-refresh-switch/` | D1 |
| 4.18 | `PatternListInput` | `admin/components/form-parts/PatternListInput.vue` | S3・S4 |
| 4.19 | `SettingSwitch` | `admin/components/form-parts/SettingSwitch.vue` | S3・S4 |
| 4.20 | `FormDisclosure` | `admin/components/form-parts/FormDisclosure.vue` | S3・S4 |
| 5 | シェル(サイドバー・上部バー・パンくず・スキップリンク・外部リンク領域) | `admin/shell/` | 全画面 |
| 5.2 | パンくず | `admin/templates/PageBreadcrumbs.vue`(描画。`PageHeader` と同じ `templates` に置き、同層の import を避ける)・`admin/composables/useBreadcrumbs.ts`(項目の組み立て)・`shell/AppShell`(provide)・`templates/PageHeader`(inject) | 2 階層以上の全画面 |
| 6 | ページテンプレート 4 型・ページ見出し領域 | `admin/templates/`(`ListPage`・`DetailPage`・`FormPage`・`DashboardPage`・`PageHeader`) | 全画面 |
| (画面仕様) | 注記ブロック(アイコン+文。`role` なし) | `admin/components/note-block/` | X1(documents 4章) |

- DS に独立した節がない部品(`PageHeader`・注記ブロック・確認ダイアログの名前・`IndexFilter`・`ClusterSummary`)の命名は本書が決める(I-100〜103)。
- 部品の `data-testid` は、部品が**ルート要素に付ける `testid` の props**を持ち、画面側が DS 9 の名前を渡す(Vuetify の部品ごとに付く位置が違うため、付く位置は部品の中で固定する。DS 9)。命名そのものは DS 9・画面仕様に従い、本書は付ける場所を決める(FMOD-P-21)。

### 3.7 `admin/templates` と `admin/shell`(FMOD-P-8・FMOD-P-9)

| モジュール | 内容 |
| --- | --- |
| `ListPage`・`DetailPage`・`FormPage`・`DashboardPage` | DS 6 の 4 型の骨格。`PageHeader`+本文のスロット。**状態ブロックの出し分け**を持つ: 画面(`features` の composable)が `useViewState` で作る **`viewState`**(`loading`・`empty`・`error`・`notfound`・`stale`・`ready`+更新中・更新時刻・診断・再試行の可否。`admin/lib/viewState.ts` の型)を props で受け、E 6.2 の表で スケルトン・エラー・見つかりません・stale アラート・進行バーを描く。**`templates` は `error.code` を判定せず、Query・`admin/api` に依存しない**(R7。FMOD-P-27) |
| `PageHeader` | `h1`(`tabindex=-1`。遷移後のフォーカス先)、状態タグ、説明、`PageActions`。**パンくずは inject で受ける**(`admin/lib/injectionKeys.ts` の key)。描画は同じ `templates` の `PageBreadcrumbs.vue`(props の項目を描くだけ) |
| `PageActions` | `ActionSpec[]` を描く(主操作は 1 つ。出さない/無効+理由 `aria-describedby`。DS 4.13) |
| `shell/AppShell` | `VApp`+`SideNav`+`VMain`+(840px 未満のみ)`MobileAppBar`+`AppSnackbar`(DS 5.1) |
| `shell/SideNav` | `router.getRoutes()`(vue-router)の `meta.nav` を抽出して描く。順は `navGroups`→`nav.order`。下部の**外部リンク領域**は `shell/externalLinks.ts` の定義表から描き、`useDashboardsUrl`(`queries/meta`)が `null`(EP-14 の失敗を含む)なら領域ごと出さない。**`featureFlag` の評価はここだけ**(E 4.2・4.5。I-89) |
| `shell/AppShell` のパンくず | `AppShell` が `composables/useBreadcrumbs`(`meta.parent` を辿り、現在の `params` を引き継いで親の URL を作る。E 4.2)で項目を作り、`provide` する。**理由**: `PageHeader`(`templates`、層 3)は `shell`(層 4)を import できないため、また各ページがパンくずを渡す繰り返しを避けるため(FMOD-P-28)。動的な `meta.title`(関数。I-83)の解決は FMOD-U-10 |

### 3.8 `admin/dialogs`(FMOD-P-10)

複数の画面から開く操作ダイアログは `features` の外(`dialogs`)に置く。`features` どうしを import しないため、S1・S2・J2 で共有するダイアログを 1 か所にまとめる。

| ダイアログ | 場所 | 開く画面(admin-view 4.1) | mutation(`queries/mutations`) | 水準(admin-view 6章) | `data-testid` |
| --- | --- | --- | --- | --- | --- |
| DLG-1 クロール起動 | `dialogs/crawl-start/` | S1・S2 | `startCrawl`(EP-06) | 要確認(標準/警告つき) | `dlg-crawl-start` |
| DLG-2 データソース削除 | `dialogs/source-delete/SourceDeleteDialog.vue` | S1・S2 | `deleteSource`(EP-05) | 要入力確認 | `dlg-source-delete` |
| 削除の再実行 | `dialogs/source-delete/SourceDeleteRerunDialog.vue` | S1・S2・J2 | `deleteSource`(EP-05) | 要確認・標準 | `dlg-source-delete-rerun` |
| DLG-3 取消 | `dialogs/job-cancel/` | J1・J2 | `cancelJob`(EP-07) | 要確認・標準 | `dlg-job-cancel` |
| DLG-4 再実行 | `dialogs/job-rerun/` | J2 | `startCrawl`(EP-06。J2 の `source_id`・`force_delete`・`rewrite_mode` を渡す) | 指定による | `dlg-job-rerun` |
| DLG-5 ロック解放 | `dialogs/lock-release/`(S2 の孤児ロック版と J2 のリース切れ版を `variant` で切替) | S2・J2 | `releaseLock`(EP-08) | 要確認・警告つき | `dlg-lock-release` |

- 共通の状態機械は `dialogs/useOperationDialog.ts`: 開閉・実行中(二重送信防止・入力の無効化)・失敗(`describeError` の結果を**ダイアログ内アラート**に。消えない)・成功(閉じる+`useSnackbar`+呼び出し側の `onSuccess`)。E 7.4・6.3 の流れの実装。
- 拒否・失敗の組み立て(`lock_held` の variant・既存ジョブ・「指定は反映されていない」・`lock_state` による warning/error、`crawler_response_lost` の結果不明)は `dialogs/crawl-start/refusal.ts` など、ダイアログごとの純関数にする(admin-view 7.7。E 6.3・FARC-P-35)。ロック状態の写像は `admin/lib/lockStateView.ts` を共有する。**`existing_job.status` が `null` のとき「ジョブを表示」を出さず、S2 のロック状態カードへ導く**(I-88。E 6.3)。
- ダイアログは**対象と成功時の動作を props・イベントで受ける**(遷移は呼び出し側。DLG-4 の成功は新しいジョブの J2 へ。#32)。

### 3.9 `admin/features`

各 feature は同じ形(FMOD-P-11):

```text
features/<名前>/
  pages/         ルートに対応するページ(*Page.vue)。ページ = テンプレート+画面の composable の結果を部品に渡す
  components/    その画面だけの部品(DS 4章の部品の組み合わせ)
  composables/   画面の composable(use<Screen>Page.ts)。queries・URL の条件・状態の決定を束ねる
  models/        純粋なロジック(表示用の変換、フォームモデル、絞り込み、並べ替え)
  *.ts           定義表(3.5)・画面ごとの操作表(*Actions.ts)・条件の定義(*Params.ts)
```

#### D1 `features/dashboard/`

| 要素 | 内容 |
| --- | --- |
| `pages/DashboardPage.vue` | `DashboardPage` テンプレート+`SummaryBand`+タイル+「この表示について」。`AutoRefreshSwitch`・手動の「更新」 |
| `composables/useDashboardPage.ts` | `useDashboardQuery(autoRefresh)`・自動更新スイッチの状態(`ref`。永続化なし)・最終取得成功日時=`dataUpdatedAt` |
| `models/dashboardViewModel.ts` | **取得失敗時の降格**(純関数): `isRefetchError` のとき、前回「正常」「異常」のタイルを判定不能にし「前回の状態」を添える。未設定は維持(dashboard 4.3。E 5.7)。概況の件数・優先順位(3.4)も算出 |
| `dashboardComponents.ts` | 8 コンポーネントの定義表(3.5) |

D1 は EP-14 を直接使わない(Dashboards のリンクはシェル。I-104 は解消済み)。

#### S1〜S4 `features/sources/`

| 要素 | 内容 |
| --- | --- |
| `pages/SourcesListPage.vue`(S1) | `ListPage`+`SourcesTable`。主操作「データソースを登録」。行の操作から `dialogs`(DLG-1・DLG-2・削除の再実行)を開く |
| `pages/SourceDetailPage.vue`(S2) | `DetailPage`+4 つのカード(`SourceSettingsCard`・`LockStateCard`(`lockStateView` の写像。E 5.10)・`LastJobCard`・`IndexCard`)。操作は `sourceActions.ts` の表 |
| `pages/SourceCreatePage.vue`(S3)・`SourceEditPage.vue`(S4) | `FormPage`+`SourceForm`(**共有**)。S4 は現在値を取得できなければフォームを出さない |
| `components/` | `SourcesTable.vue`(S1。クライアント側のページ・並べ替え。`AdminDataTable`)・`SourceRowActions.vue`・`SourceSettingsCard.vue`・`LockStateCard.vue`・`LastJobCard.vue`・`IndexCard.vue`・`SourceForm.vue`・`SourceFormAlerts.vue`(読めない項目・丸め・削除中・上部アラート) |
| `composables/` | `useSourcesListPage`(EP-01・EP-14。表の行モデル)、`useSourceDetailPage`(EP-02・EP-14)、`useSourceForm`(下) |
| `models/sourceRow.ts` | 一覧の行の表示用変換(`last_crawl` と `delete_job` からタグ・補足文。行の `unavailable` を `rowCell` で引く。source-a の未実行と source-b の読み取り失敗を区別する) |
| `sourceActions.ts` | 状態 → 操作の表(DS 4.13・sources 1.8): 削除中は起動・編集・削除を出さない、削除ジョブが失敗なら「削除を再実行」、ロック状態に応じた「ロックを解放…」の入口 |
| `form/` | S3・S4 のフォーム(下) |

**`features/sources/form/`(S3・S4 共有。FMOD-P-16)**:

| ファイル | 内容 |
| --- | --- |
| `connectors/fileSystem.ts` | `file_system` の取得設定 5 項目の**項目定義の表**(項目名・型・必須・既定・部品・ラベル・説明文・検証・`data-testid`。sources 2.3.1 と同じ形)。Connector の種別を足すときは、種別ごとにこの形のファイルを足す(admin-view 8.3.1) |
| `sourceFormModel.ts` | フォームの値の型(`connector_config` の 5 項目・TTL のモード(日・秒)と値・しきい値・最小件数・`schedule_cron`・S3 では `source_id`・`connector_type`)と初期値(必須は空欄。既定を補わない) |
| `fromSettings.ts` | EP-02 の応答 → フォームの値。**TTL のモード**は応答の `ttl_days` の有無で決める(`null` なら秒)。**しきい値の丸め注意**: 応答の値が小数第 2 位を超えるとき、丸めた値(四捨五入が案)を入れ、`roundedNotice`(元の値・丸めた値)を返す(E 7.7)。**読めない項目**(`unavailable.<項目名>=malformed`)は空欄・必須にし、`connector_config` が読めないときは「フォームを出さない」判定を返す(E 7.6) |
| `toRequest.ts` | フォームの値 → EP-03・EP-04 のリクエスト(E 7.5): 文字列を検証してから数値化、`ttl_days` か `ttl_seconds` の一方、S4 は `source_id`・`connector_type` を含めない、`connector_config` は 5 項目を常に全部、`schedule_cron` の空は `null` |
| `rules.ts` | 項目 → 検証規則(`admin/lib/validation` を使う) |
| `fieldMap.ts`・`serverErrors.ts` | サーバーの `details.errors` を入力欄・行・上部アラートに振り分ける(3.5。`config_invalid` の `detail` は完全一致の対応表で照合、照合不能は上部アラート。E 6.4) |
| `composables/useSourceForm.ts` | フォームの状態(値・クライアント検証・サーバーエラー・送信中)。保存は `createSource`・`updateSource`。成功は S2 へ移動+スナックバー(sources 2.5)。`describeError` の結果をフォームの 3 つの表示先に分ける |

#### J1・J2 `features/jobs/`

| 要素 | 内容 |
| --- | --- |
| `pages/JobsListPage.vue`(J1) | `ListPage`+`FilterBar`(データソース・状態)+`JobsTable`(`AdminDataTableServer`)。取消は `dialogs/job-cancel` |
| `pages/JobDetailPage.vue`(J2) | `DetailPage`+カード(`JobSummaryCard`・`FailureAlert`・`WarningList`・`RegistrationCard`(`StatList`。件数・`partial`・`phase` が `null` なら「—」。`cellState`)・`DeletionCard`・`LockCard`)。操作は `jobActions.ts` |
| `composables/useJobsListPage.ts` | `jobsParams.ts` による URL の条件・`useJobsListQuery`・EP-01 の選択肢 |
| `composables/useJobDetailPage.ts` | `useJobDetailQuery`(10 秒のポーリング)・最終更新・「見つかりません」の判定 |
| `jobsParams.ts` | J1 の条件(URL `source`↔API `source_id`・`status`・`page`・`size`↔`items_per_page`・`sort`)の定義(E 5.6) |
| `jobActions.ts` | **J2 の操作の出し分けの表**(jobs 2.3 の表)。取消: `cancellable=true` のときだけ。再実行: `rerunnable=true` なら「再実行」、`rerun_blocked_reason` が `superseded`・`stalled` なら**無効+理由**(「新しいジョブがあるため」「ロックを解放すると再実行できます」)、`not_failed`・`not_crawl`・`source_deleting` は出さない(DS 4.13。削除中は補足)。**`source_missing`(データソースの設定がない=削除済み。AAPI-P-41。案)も出さない**(削除済みのソースを再実行しない。専用文言は画面仕様に足す(HO-30)。E 6.7。FMOD-P-32)。**`status=null` のジョブには操作を出さない**。**`stalled`・`rerunnable`・`latest_for_source` が `null`(`rerunnable=null` は設定の読み取り失敗を含む)なら再実行・取消を出さず、理由を補足に**(E 1.2・6.7)。ロック解放は `stalled=true` のとき。ソース削除ジョブは失敗のときだけ「削除を再実行」 |
| `catalogs/` | 失敗理由・警告・削除結果の日本語表記(3.5) |
| `components/` | 上のカード・`JobsTable.vue`・`JobStatusCell.vue`(`stalled` でタグを切替。**`status=null` のジョブにはタグを出さず「—」**(読み上げは「読み取れません」)。取消・再実行も出さない。E 5.9・FMOD-P-31) |

#### X1 `features/documents/`

| 要素 | 内容 |
| --- | --- |
| `pages/DocumentsPage.vue` | `ListPage`+データソース選択(`FilterBar`)+`CountTabs`+注記+`AdminDataTableServer`。タブごとに独立した状態(エラーはパネルだけ) |
| `composables/useDocumentsPage.ts` | `documentsParams.ts`(`source`・`tab`・`page`・`size`・`sort`)・`useDocumentsQuery`・`useSourcesListQuery`(選択肢。削除中は選べない)・タブ件数(**応答の `tab_counts`**。データソースが同じ間だけ前回の値を残す。E 5.6)・`existence` の扱い |
| `documentTabs.ts`・`columns.ts` | タブ定義と列定義(3.5)。列は優先順位つきで、カード幅の閾値は画面ごと(DS 4.3) |
| `components/` | `SourceSelect.vue`・`DocumentsTable.vue`(列定義から描く)・`NoSourceState.vue`(未選択・登録 0 件) |

#### O1 `features/opensearch/`

| 要素 | 内容 |
| --- | --- |
| `pages/OpenSearchPage.vue` | `DashboardPage` テンプレート+1 カード「クラスタ状態」(`ClusterSummary`・`IndexFilter`・`ShardMatrix`) |
| `composables/useOpenSearchPage.ts` | `useOpenSearchClusterQuery`・`opensearchParams.ts`(`q`・`state`。**`replace`**。`page` は URL に入れない)・絞り込み・`useContainerWidth` による 1 ページの列数 |
| `models/indexFilter.ts` | 絞り込みの純関数(名前=部分一致・大文字小文字無視・空白だけは条件なし、状態=OR、3 つ選択=条件なし、未知の状態値は除外。opensearch 3.5) |
| `models/matrixModel.ts` | 行=ノード(+未割り当ての行)・列=インデックスのモデル。並び=状態の悪い順→名前、`indices[]` にないインデックスの補完、凡例の対象 |
| (部品の `columnsPerPage.ts`) | 1 ページの列数 `max(1, floor((W − H) ÷ 112))`(DS 4.15。`components/shard-matrix/`) |

---

## 4. 画面 → route → ページ → composable → EP の対応表

### 4.1 画面ごとの対応(FMOD-P-22)

B 1.3 の画面×EP 対応表と突き合わせた(9 画面+シェルで一致。D1 の EP-14 の食い違い(I-104)は 0017 で E・B が直り、解消済み)。key・更新・失敗時の表示は E 5.4・5.5・5.7、`data-testid` は各画面仕様に従う。

| 画面 | route(`name`・path。admin-view 4.2) | ページ | 画面の composable | queries(E 5.4 の key) | EP | 更新 | 状態の `testid` の接頭辞 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | `dashboard`・`/` | `DashboardPage.vue` | `useDashboardPage` | `useDashboardQuery` | EP-13 | 30 秒+手動 | `d1-` |
| S1 | `sources`・`/sources` | `SourcesListPage.vue` | `useSourcesListPage` | `useSourcesListQuery`、`useMetaQuery` | EP-01、EP-14 | 手動 | `s1-` |
| S2 | `source-detail`・`/sources/:sourceId` | `SourceDetailPage.vue` | `useSourceDetailPage` | `useSourceDetailQuery`、`useMetaQuery` | EP-02、EP-14 | 開いたとき・操作後 | `s2-` |
| S3 | `source-new`・`/sources/new` | `SourceCreatePage.vue` | `useSourceForm` | `useMetaQuery`、`createSource` | EP-14、EP-03 | — | `s3-`・`source-form-` |
| S4 | `source-edit`・`/sources/:sourceId/edit` | `SourceEditPage.vue` | `useSourceForm` | `useSourceEditQuery`、`useMetaQuery`、`updateSource` | EP-02、EP-14、EP-04 | 開くたび(編集中は再取得しない) | `s4-`・`source-form-` |
| J1 | `jobs`・`/jobs` | `JobsListPage.vue` | `useJobsListPage` | `useJobsListQuery`、`useSourcesListQuery` | EP-09、EP-01 | 手動 | `j1-` |
| J2 | `job-detail`・`/jobs/:jobId` | `JobDetailPage.vue` | `useJobDetailPage` | `useJobDetailQuery` | EP-10 | 10 秒(実行待ち・実行中) | `j2-` |
| X1 | `documents`・`/documents` | `DocumentsPage.vue` | `useDocumentsPage` | `useDocumentsQuery`、`useSourcesListQuery` | EP-11、EP-01 | 手動 | `x1-` |
| O1 | `opensearch`・`/opensearch` | `OpenSearchPage.vue` | `useOpenSearchPage` | `useOpenSearchClusterQuery` | EP-12 | 手動 | `o1-` |
| シェル | (全画面) | `shell/AppShell.vue` | — | `useMetaQuery`(`useDashboardsUrl`) | EP-14 | 再読み込みまで | `nav-` |
| (404) | `not-found`・`/:pathMatch(.*)*` | `admin/router/NotFoundPage.vue`(`StateBlock` の最小ページ) | — | — | — | — | — |

- 「更新」列の「手動」は、定期更新とフォーカス・再接続による再取得をしない意で、**画面を開く・戻るときの再取得は行う**(E 5.4・5.5)。
- ページの `.vue` は `features/<名前>/pages/`(3.9)。すべての route は同期 import(単一チャンク。FMOD-P-17)。
- 404 の route は、新しい画面を作らず `ListPage` のエラーブロックを使う(admin-view 4.2)。`admin/router/NotFoundPage.vue` に置く。

### 4.2 操作(ダイアログ・保存)ごとの対応

E 5.8 の表を、置き場に対応づけた。

| 操作 | ダイアログ/画面 | mutation | EP | 成功後 | invalidate(`invalidation.ts`) |
| --- | --- | --- | --- | --- | --- |
| クロール起動 | DLG-1(S1・S2) | `startCrawl` | EP-06 | スナックバー+「ジョブを表示」 | `['sources']`・`['jobs']` |
| 再実行 | DLG-4(J2) | `startCrawl` | EP-06 | 新しいジョブの J2 へ移動 | 同上 |
| データソース削除・削除の再実行 | DLG-2・再実行ダイアログ(S1・S2・J2) | `deleteSource` | EP-05 | スナックバー+行が「削除中」 | `['sources']`・`['jobs']` |
| 取消 | DLG-3(J1・J2) | `cancelJob` | EP-07 | スナックバー(200・202・409 `job_already_finished` を成功扱い) | `['jobs']`・`['sources']` |
| ロック解放 | DLG-5(S2・J2) | `releaseLock` | EP-08 | スナックバー | `['sources']`・`['jobs']` |
| 登録 | S3 | `createSource` | EP-03 | S2 へ移動+スナックバー | `['sources']` |
| 保存 | S4 | `updateSource` | EP-04 | S2 へ移動+スナックバー | `['sources']` |

---

## 5. 主要シナリオの流れ

(`→` は呼び出し。EP・code の中身は B、方針は E を参照。)

### 5.1 S1 からのクロール起動と 409 `lock_held`(FARC-P-14)

1. `SourcesListPage` が `useSourcesListPage` → `useSourcesListQuery`(EP-01)で一覧を表示。行の「クロール起動」で `CrawlStartDialog`(DLG-1)を開く(`dlg-crawl-start`)。
2. ダイアログで強制削除・再書き込みを指定(`ConfirmDialog` の水準と帯の色は `dialogLevel.ts`)。実行 → `useOperationDialog` が `startCrawl`(EP-06。`force_delete`・`rewrite_mode` を明示)を呼ぶ。
3. **202**: ダイアログを閉じ、`useSnackbar` で「受け付けました(ジョブ ID)」+「ジョブを表示」(J2 へ)。`invalidation.ts` の表で `['sources']`・`['jobs']` を invalidate。S1 の一覧が再取得される。
4. **409 `lock_held`**: `ApiError`(`kind='api'`)→ `describeError`(`errorTable`)が「ダイアログ内アラート」と variant を返す(E 6.3。FARC-P-35)。`lease_expired`(ジョブ記録あり)なら warning+「ジョブ詳細でロックを解放」(J2 へ)。`orphan` なら warning+「ロック状態を確認」(**S2 のロック状態カード**。孤児ロックの解放の入口は S2 だけ)。`just_acquired`(取得から 60 秒以内)・`unknown` は「ジョブを表示」を出さず、待って確認する案内(S2 へのリンク)。`held_crawl`・`held_delete`(ジョブ記録あり)は error+「ジョブを表示」(`existing_job`)。**`existing_job.status` が `null` のときは J2 へ導かない**(EP-10 が 404 になりうる。admin-view 7.7 との差は I-88。ゲート3でユーザー確認済み。2026-11-23)。`options_applied=false` なので「指定は反映されていない」を太字で出す。`refusal.ts` が文面を組み立て、`existing_job.lease_expires_at` は `formatLeaseExpiry` を通す。ダイアログは開いたまま、実行ボタンは「閉じる」に置き換わる。
5. **504 `crawler_response_lost`**・クライアントのタイムアウト: 結果不明(再試行を出さず、一覧・S2 で確認する導線)。

### 5.2 D1 の 30 秒ポーリングと取得失敗

1. `useDashboardPage` が `autoRefresh`(`ref`。既定オン)を持ち、`useDashboardQuery(autoRefresh)` が `polling.ts` の `refetchInterval: 30000`(オンのときだけ)・`refetchIntervalInBackground: false` で EP-13 を取得。
2. 成功のたびに `dataUpdatedAt` が「最終取得成功」の日時になる(クライアント保持)。タイルは `dashboardComponents` の順に `components[]`(8 件)から描き、`SummaryBand` が件数を出す。
3. 取得に失敗(`network` など。EP-13 自体は 200 を返す限り失敗しない): 初回は `StateBlock`(`d1-state-error`)。2 回目以降は `isRefetchError` → `dashboardViewModel` が前回「正常」「異常」のタイルを判定不能に降格し「前回の状態」を添え、`PageAlert`(stale。`d1-state-stale`)を出す。通知(スナックバー)は出さない。成功すれば通常の表示に戻る。
4. スイッチをオフにすると `refetchInterval` が `false` になり、「自動更新は停止中」の文を出す。手動の「更新」は `refetch()`。

### 5.3 S3 の登録と `config_invalid` の項目別表示・上部アラート

1. `SourceCreatePage` → `useSourceForm`。入力はフォーカスが外れたとき・送信時に `rules.ts` で検証。エラーがあれば `ErrorSummary`(件数つき・項目へのリンク)を出して送信しない(DS 4.6)。
2. 送信: `toRequest.ts` が文字列を検証してから数値化し、`ttl_days`・`ratio_threshold_percent`・`min_delete_count`・`connector_config`(5 項目)を組む → `createSource`(EP-03。`Content-Type: application/json`)。
3. **201・200**(冪等): S2 へ移動+スナックバー、`['sources']` を invalidate。
4. **400 `invalid_request`**: `serverErrors.ts` が `details.errors[].field` を `fieldMap` で入力欄に対応づけ、`reason` を文言にして項目の下に出す。**400 `config_invalid`**: `field` が `connector_config.include_patterns[2]` なら該当の行の下へ(`detail` の固定文を完全一致の表で画面の文言に)。**`errors` が空、または `field="connector_config"`(プレフィックスなし)、照合できない `detail`** は、フォーム上部のアラートに出す。入力内容は残す。
5. **409 `source_already_exists`**: 識別子の項目の下(`details.status=deleting` なら補足)。**503・504**: フォーム上部の消えないアラート(504 は「S2 で確認する」と「もう一度保存」を出す。保存系は再送が安全。E 6.5)。

### 5.4 J2 の取消と再実行(EP-06 を呼ぶ)

1. `JobDetailPage` → `useJobDetailPage` → `useJobDetailQuery`(EP-10)。実行待ち・実行中は `polling.ts` が 10 秒ごとに再取得(終端で停止)。
2. `jobActions.ts` が応答(`cancellable`・`rerunnable`・`rerun_blocked_reason`・`stalled`・`latest_for_source`)から操作を返す。`cancellable=true` のときだけ「取消」。`rerunnable=true` なら「再実行」(primary)、`superseded`・`stalled` は**無効+理由**、`not_failed`・`not_crawl`・`source_deleting`・`source_missing`(AAPI-P-41。案)は出さない。**`null` のフラグは「不可」**(`status=null` のジョブには操作そのものを出さない)(取消・再実行を出さず、補足に「確認できません」)。`PageActions` が描く(jobs 2.3)。
3. **取消**: `JobCancelDialog`(DLG-3)→ `cancelJob`(EP-07)。200・202 はスナックバー。**409 `job_already_finished` は成功扱い**(ダイアログを閉じ「すでに終了しています(状態: …)」)。202 の後も終端までポーリングが続く。
4. **再実行**: `rerunnable=true` のとき「再実行」を出す。`superseded`・`stalled` は無効+理由、それ以外(`not_failed`・`not_crawl`・`source_deleting`・`source_missing`・`null`)は出さない(手順 2。専用の EP はない。B 4.1)。`JobRerunDialog`(DLG-4)が J2 の応答の `source_id`・`force_delete`・`rewrite_mode` を**読み取り専用で提示**し、確認チェックの後、`startCrawl`(EP-06。同じ値を渡す)を呼ぶ。成功は**新しいジョブの J2 へ移動**(#32)。409 `lock_held` なら 5.1 と同じ表示。
5. リース切れ(`stalled=true`)は「ロックを解放…」(DLG-5 → `releaseLock`(EP-08))が主操作。`lock_in_use` の `lock_state=unknown` は理由を断定しない文言。

### 5.5 X1 のタブ切替

1. `DocumentsPage` → `useDocumentsPage`。URL の `source`・`tab`・`page`・`size`・`sort` を `documentsParams` で正規化(不正値は既定値にして `replace`)。
2. `source` 未選択なら `useDocumentsQuery` は `enabled: false`(「データソースを選んでください」)。選択肢は `useSourcesListQuery`(EP-01。削除中は選べない)。
3. タブの切替は `router.push` で `tab` を変え、1 ページ目に戻る(`documentTabs` の kebab の `id` を URL に、snake の `tab` を API に)。`useDocumentsQuery`(EP-11)が取得。前回データは**同じデータソース・同じタブ**のページ・並べ替えの変更のときだけ保持(`placeholder.ts`)。
4. 応答の `tab_counts` を `CountTabs` の件数に使う(`null`・最上位 `unavailable` の `tab_counts.<タブ>` は「—」。引くのは `topCell`)。スキップのタブは各行の `existence`(`unknown` は「確認できません」。その行の `unavailable` の `existence`。一括検索(1 回の `ids` クエリ)の失敗は全行。行ごとに成否が分かれることはない。引くのは `rowCell`)。
5. エラーはパネルだけ(`x1-state-error`)。タブ名・データソースの選択は操作できる。更新は手動の「更新」のみ(`refetch()`)。

---

## 6. 依存ルール

機械検査は **ESLint の `no-restricted-imports`**(flat config の `files` ごとの設定)を第一候補とする(E 11.1。FMOD-P-18)。パターンで書けない規則は FMOD-U-1。**`tests/**`・`*.test.ts` は R2・R3 だけを適用する**(生成コードと `fetch` を直接使わない。fixtures の型は公開口 `@/admin/api` から。7.1)。他の規則は対象外。

| # | 規則 | 理由 |
| --- | --- | --- |
| R1 | `shared/` は `admin/`・`vue-router`・`@tanstack/vue-query`・生成コードを import しない | Search View と共有するため(2.3) |
| R2 | `admin/api/generated/` を import してよいのは `admin/api/` の中だけ。外は `@/admin/api`(公開口)だけ | 生成物の形の変更を `admin/api/` に閉じる(Hey API 0.x。E 5.2) |
| R3 | `fetch`・`XMLHttpRequest`・`@hey-api/*`・文字列 `'/api/admin/v1'` は `admin/api/` と `shared/api/` の中だけ | HTTP の入口を 1 か所にする(E 5.3) |
| R4 | `@tanstack/vue-query` を import してよいのは `admin/queries/` と `admin/app/setupQuery.ts` だけ(例外: **型の import(`import type`)は `admin/composables/useViewState.ts` でも可**。入力を構造的な型で受ける形にしてもよい) | 画面が Query の API を直接使わない |
| R5 | `admin/lib/` は `vue`・`vue-router`・`vuetify`・`.vue`・`queries` を import しない(純粋。ただし `import type { InjectionKey } from 'vue'` は可)。型の import(`import type`)は `admin/api` から可 | 単体テストしやすく、サーバー・UI から独立 |
| R6 | `admin/queries/` は `vue-router`・`.vue`・`vuetify`・`components`・`templates`・`dialogs`・`shell`・`features`・`router`・`app` を import しない | データ取得を UI から分ける |
| R7 | `admin/components/`・`admin/templates/` は `queries`・`admin/api`(値の import)・`vue-router`・`features`・`dialogs`・`shell` を import しない(`admin/api` は `import type` のみ可)。`templates` が必要とする状態は **`viewState`(`admin/lib/viewState.ts` の型)を props で受け**、`error.code` を判定しない。パンくずは `admin/lib/injectionKeys.ts` の key で inject する(`shell` を import しない)。`composables`・`lib`・`shared` は可 | 見た目の部品はデータ取得を知らない(DS 11)。`templates` が `shell`(層 4)・`admin/api`(値)を import しない理由 |
| R8 | `admin/features/<A>/` は他の `features/<B>/` を import しない。`admin/router/`(`routeNames` は `admin/lib/` にあるので不要)・`admin/app/` も import しない。共有したいものは `components`・`dialogs`・`queries`・`lib` に移す | features どうしの結合を避ける |
| R9 | `admin/dialogs/` は `features`・`shell`・`router`・`app` を import しない。`admin/queries/mutations/` と `admin/api/errors/`(`describeError`。`admin/api` の公開口でなく `errors/` を直接 import してよい)を使ってよい | 画面から独立した操作の部品 |
| R10 | `admin/shell/` は `features`・`dialogs`・`app` を import しない。`queries/meta`・`composables`(`useBreadcrumbs`)・`vue-router` は可。`featureFlag` の評価は `shell`(`SideNav`・外部リンク領域)だけで行う | I-89 |
| R11 | `admin/router/` は `features` のページ・`templates`(404)・`lib` を import する。`queries`・`shell`・`app` は import しない(ガードは認証・`featureFlag` を持たない。MVP は遷移後の処理だけ) | |
| R12 | `@mdi/js` を import してよいのは `shared/theme/icons.ts` だけ(他はそこから)。`@mdi/font` は禁止 | アイコンを 1 か所で管理し、tree-shaking とポリシー確認(FARC-U-3)を 1 か所にする |
| R13 | `vuetify` の部品を import してよいのは `shared/ui`・`shared/theme`・`admin/components`・`templates`・`shell`・`dialogs`・`features` の `.vue` だけ(`api`・`queries`・`lib`・`composables` は不可)。`createVuetify` を呼ぶのは `admin/app/setupVuetify.ts` だけ | Vuetify の設定の入口を 1 か所にする(DS 3) |
| R14 | `localStorage`・`sessionStorage` を使わない(ユーザー設定を持たない) | E 8章 |
| R15 | `admin/app/` を import するのは `main.ts` だけ | 最上位 |
| R16 | `admin/composables/` は `queries`・`components`・`templates`・`dialogs`・`shell`・`features`・`router`・`app` を import しない。`vue`・`vue-router`・`admin/api/errors/`(`describeError`。`useViewState` が使う)・`lib` は可 | 汎用の composable を層 2 に保つ |

- **層の向き**(2.2)は R1〜R16 の組み合わせで表す。同じ層どうし(`dialogs` と `shell`、`components` と `templates`、`queries` と `composables`)の import は、上の規則に書いたもの以外は**禁止**とする(案)。
- 規則はパターンの否定(`!`)で書けるか、`features` ごとの override が冗長にならないかを実装時に確認する(FMOD-U-1)。足りなければ `eslint-plugin-boundaries` か `dependency-cruiser` を足す(E 11.1)。
- **規則を破りやすい場所**(実装時にレビューで見る): `features` からの `vue-query` 直接利用(R4)、`components` からの `useRoute`(R7)、`api` の `generated` の直接 import(R2)、`lease_expires_at` を `formatLeaseExpiry` を通さず整形すること(3.5。lint では検出しにくい)。

---

## 7. テスト構成

E 10 の方針の置き場。テストコード・設定ファイルは作らない(FARC-P-38)。

### 7.1 配置(FMOD-P-19)

```text
src/**/<対象>.test.ts          # Vitest。対象の隣に置く(純粋ロジック・composable・部品)
tests/support/
  setup.ts                     # Vitest の setup: ResizeObserver のモック、TZ=Asia/Tokyo(`test.server.deps.inline: ['vuetify']` は vite.config.ts。E 10.1)
  mount.ts                     # createVuetify()+VLayout+Router+QueryClient(retry:false)で包む共通ヘルパー
  fetchStub.ts                 # Vitest 用: fetch を差し替え、生成クライアントを実際に通す(MSW は使わない)
  mockApi.ts                   # Playwright 用: page.route('**/api/admin/v1/**')。未モックの /api/ への要求は失敗させる(E 10.2)
  apiErrors.ts                 # A 5.2 の形のエラー応答を code ごとに作るビルダー(型付き)
  fixtures/                    # EP ごとの応答。生成した型で `satisfies`(meta.ts・dashboard.ts・sources.ts・jobs.ts・documents.ts・opensearch.ts)
tests/e2e/
  *.spec.ts                    # Playwright。画面ごと+shell(ガード・SPA 内 404)+smoke(実 API。読み取りのみ)
```

- `tests/` は `@/admin/api`(公開口)の**型だけ**を import し、`generated/` を直接 import しない(R2 を `tests/` にも適用する。fixtures の型付けのため)。
- ルートの `playwright.config.ts` が `tests/e2e/` を指す。`baseURL` は `http://localhost:5173/admin/`(末尾スラッシュ。E 10.2)。
- 実 API のスモークは、既存の結合テスト(`tests/integration/`)と固定ポートが衝突しうるため同時に動かさない(E 10.2)。置き場は `tests/e2e/smoke.spec.ts` を案とする(結合テストの慣習の `tests/integration/<名前>/` に置くかは FMOD-U-8)。

### 7.2 モジュール別のテストの種類

| 対象 | 種類 | 内容 |
| --- | --- | --- |
| `admin/api/errors/errorTable` | Vitest(単体) | **B 2.3 の全 `code`(Admin 固有 14 種+共通 6 種)を表から網羅**(code を足すとテストが落ちる。E 10.1)。`lock_state` ごとの variant |
| `admin/api/pathParams`・`client` | Vitest(契約) | `job_id='a%b?c#d'` などの実 URL(生成 SDK を通す)、`ApiError` への正規化(`network`・`timeout`・`invalid_response`・A 5.2 の形) |
| `admin/queries/*` | Vitest | key factory、`polling.ts`(D1 のオン・オフ、J2 の状態ごとの間隔)、`placeholder.ts`(同スコープだけ)、`invalidation.ts` の表、`enabled: false` |
| `admin/lib/unavailable`・`leaseExpiry`・`lockStateView`・`viewState`・`units`・`validation` | Vitest(純粋) | 正式パス(最上位)と行内の相対パス(行の `unavailable`)・`cellState` の 4 状態(行・最上位のそれぞれ)・**source-a の未実行(キーなし)と source-b の読み取り失敗(キーあり)の区別・全行失敗(全行に同じキー)・1 行だけの失敗(他の行に影響しない)**・番兵・ロック状態 7 値+取得失敗の写像(E 5.10)・`viewState` の写像(E 6.2)・日 ↔ 秒・丸め・9 桁・パターンのバイト数 |
| `admin/composables/useListParams`・`useBreadcrumbs`・`useViewState` | Vitest | URL ↔ 条件、不正値の正規化(`replace`)、条件を変えたら 1 ページ目に戻る、`push`/`replace`。パンくずの親の解決(`params` の引き継ぎ)。`viewState` の組み立て(404 の「見つかりません」・stale・`describeError` の結果) |
| `features/*/models`・`*Actions.ts`・`*Params.ts` | Vitest(純粋) | `dashboardViewModel`(降格)、`indexFilter`・`matrixModel`、`jobActions`・`sourceActions`(状態 → 操作の全組合せ)、`documentTabs` の kebab ↔ snake、`fromSettings`・`toRequest`(TTL モード・丸め・`malformed`) |
| `shared/ui`・`admin/components` | Vitest(コンポーネント) | props と状態の出し分け(`StatusTag` の未登録警告、`ConfirmDialog` の実行ボタンの有効/無効と理由、`PatternListInput` の追加・削除・Enter、`ShardMatrix` の列数)。レイアウト・コンテナクエリ・フォーカスの実挙動は E2E と実機 |
| `admin/dialogs` | Vitest+E2E | 状態機械(`useOperationDialog`)、拒否の組み立て(`refusal.ts`)。フォーカスの閉じ込め・復帰は E2E |
| `features/*` のページ | E2E(Playwright) | 画面のフロー(5章の各シナリオ)、状態(読み込み中・空・エラー・stale・見つかりません)、URL の同期、ポーリング(時計の操作。FARC-U-8) |
| `admin/router`・`shell` | E2E | ガード・遷移後のフォーカス・タイトル・SPA 内 404・サイドバーの出し分け(840px の境) |
| 依存ルール | lint | 6章(ESLint) |

### 7.3 モックとフィクスチャの規約(E 10.2。FMOD-P-20)

- フィクスチャは **EP ごと・状態ごと**(正常・空・部分失敗(`unavailable`。行単位: 全行失敗・1 行だけの失敗・未実行の行と失敗の行が混在)・`null` のフラグ・値の読めない `null`(`status=null` のジョブ)・`source_missing`・番兵日時・読めない設定項目・保存値のしきい値が小数第 3 位以下)の関数として `tests/support/fixtures/` に集め、Vitest と Playwright で**共有**する。すべて生成した型で `satisfies` する(B の変更が型エラーになる)。
- エラー応答は `apiErrors.ts` のビルダーで A 5.2 の形を作る(`code`・`retryable`・`details`)。
- `mockApi.ts` は「パス+メソッド → 応答(固定または関数)」の宣言を受け、`**/api/admin/v1/**` に束ねる。ポーリング・再取得のテストのため、応答の差し替え(呼び出し回数ごと)ができる。

---

## 8. 確認状況

### 8.1 確認した事実(2026-11-22)

- 読んだ文書: E(R3 の修正と 0020・0022 の追従後)、0002・0009・0013・0015(F への引き継ぎ)、B(1.3 の画面×EP 対応表、EP-01〜14、2.2・2.9・2.11・2.12)、A(2・5・8 章)、DS(0・4〜6・9〜11 章)、admin-view(4・7・8・10 章)、画面仕様 5 本(各コンポーネント・状態・更新・`data-testid`)、`crawler-module-structure-v0.5.md`(書式の手本)。
- PR #10 のレビュー指摘(0037)に基づく B の修正(0038。AAPI-P-42。一覧の `unavailable` を行単位に)を読み、3.5・3.9・5.5・7 章を E 5.7・5.9 と合わせた。
- リポジトリ: `apps/web/` は存在しない(新規)。`apps/crawler`・`apps/indexer` の構成(`tests/architecture/`・`tests/fakes/`)は `crawler-module-structure-v0.5.md` 経由で確認した。
- 技術事実(Hey API・Vite・Vitest・Playwright の挙動)は E・0004 による。**本書の作成者は再確認していない**。

確認していないこと: 8.4 の FMOD-U。ほかに、ブラウザの URL 正規化が `%2e%2e` を `..` として扱うこと(推測。3.3)。

### 8.2 確定(FMOD-K)

確定にしたのは、ユーザーの明示回答と、確定として書かれた既承認文書の引用だけ。

| ID | 内容 | 出典 |
| --- | --- | --- |
| FMOD-K-1 | (欠番。確定ではなく承認済みの案(DS のゲート B・C の承認事項の引用)のため FMOD-P-26 に移した。R3 の指摘。E の FARC-K-5 → FARC-P-32 と同じ整理) | — |
| FMOD-K-2 | UI は Vuetify 4.3.4(exact pin)・TypeScript 6.x・`@mdi/js`・自前ナビで作る | DS 10.1(承認済み(ゲート B))。E の FARC-K-1。「コード・設定ファイルは作らない」は確定にせず E の FARC-P-38(案を含む)に従う |
| FMOD-K-3 | 要素の特定はロール・ラベル基準で、必要な箇所だけ `data-testid`。命名は DS 9章・画面仕様 | DS 0.1 の前提 6(承認済み)。E の FARC-K-9。名前の細則は案 |
| FMOD-K-4 | Web UI は `api` が静的配信する(同一オリジン。CORS 不要)。Search View は設計しない(配置の境界だけ) | BAPI-K-2(ユーザー回答 2026-11-22。0001 Q2)。E の FARC-K-4 |

### 8.3 案・承認済みの案(FMOD-P)

すべて、本書で新たに決めた案で、ゲート3(2026-11-23)で承認された。区分欄の「承認済みの案」は、E・A・B の承認済みの案を実装に落としたもの。

| ID | 内容 | 区分 | 章 |
| --- | --- | --- | --- |
| FMOD-P-1 | `apps/web/` の構成: `src/shared/`(共有層)・`src/admin/`(Admin 専用。層 1〜7)・`tests/`、ルート直下の設定ファイル | 承認済みの案(ゲート3。2026-11-23。ディレクトリ `apps/web/` は承認済みの案(ゲート2。BAPI-P-11)) | 2.1・2.2 |
| FMOD-P-2 | Search View と共有する範囲=`shared/{theme,ui,api,lib}`。Admin 専用=シェル・テンプレート・データテーブル・確認ダイアログ・`KeyValueList` | 承認済みの案(ゲート3。2026-11-23。DS 11 の方針に沿う) | 2.3 |
| FMOD-P-3 | `shared/api` に `ApiError` と正規化、`admin/api` に生成コード・クライアント・エラー表 | 承認済みの案(ゲート3。2026-11-23。E 5.3 の置き場) | 3.2・3.3 |
| FMOD-P-4 | **パスエンコード(FARC-U-18 への案)**: `admin/api` の層で `pathParams.ts` に集約して保証し、契約テストで検証。`.`・`..` だけの ID は取得しない | 承認済みの案(ゲート3。2026-11-23) | 3.3 |
| FMOD-P-5 | `admin/queries`: 読み取りも書き込みもここ。key factory・`polling.ts`・`placeholder.ts`・`invalidation.ts`・`mutations/` | 承認済みの案(ゲート3。2026-11-23。E 5.4・5.5・5.8 の置き場) | 3.4 |
| FMOD-P-6 | エラー変換表 `errors/errorTable.ts` と `describeError.ts`(Admin 固有 14 種+共通 6 種を網羅) | 承認済みの案(ゲート3。2026-11-23。E 6.3 の置き場) | 3.3 |
| FMOD-P-7 | DS 4章の部品の置き場の規則(DS に仕様がある部品は `admin/components` か `shared/ui`)と、全件の置き場の表 | 承認済みの案(ゲート3。2026-11-23) | 3.6 |
| FMOD-P-8 | テンプレート 4 型・`PageHeader`・`PageActions`。状態は `viewState` を props で受ける(FMOD-P-27) | 承認済みの案(ゲート3。2026-11-23) | 3.7 |
| FMOD-P-9 | シェルの構成(`AppShell`・`SideNav`・`MobileAppBar`・`SkipLink`・`ExternalLinks`・`externalLinks.ts`)。パンくずの provide は `AppShell` | 承認済みの案(ゲート3。2026-11-23) | 3.7 |
| FMOD-P-10 | 複数画面から開く操作ダイアログは `admin/dialogs/`(`useOperationDialog`・拒否の組み立ての純関数) | 承認済みの案(ゲート3。2026-11-23) | 3.8 |
| FMOD-P-11 | `features/<名前>/` の内部構成(`pages`・`components`・`composables`・`models`・定義表)と各画面のファイル | 承認済みの案(ゲート3。2026-11-23) | 3.9 |
| FMOD-P-12 | 定義表の置き場(`navGroups`・`documentTabs`・`dashboardComponents`・条件の定義・`fieldMap`・catalogs・検証・単位・操作表) | 承認済みの案(ゲート3。2026-11-23) | 3.5 |
| FMOD-P-13 | 一覧の条件は `composables/useListParams` と画面ごとの `*Params.ts` で URL ↔ API を対応づける | 承認済みの案(ゲート3。2026-11-23。E 5.6 の実装) | 3.5・3.9 |
| FMOD-P-14 | `admin/lib/unavailable.ts`: 行の `unavailable` を引く関数(`rowUnavailableReason`・`rowCell`)と最上位を引く関数(`topUnavailableReason`・`topCell`)、`cellState`。**行単位で判定**し、旧規則の `isRowUnavailable` は廃止。値の読めない `null` は `cellState` で別に扱う | 承認済みの案(ゲート3。2026-11-23)の修正(PR #10 のレビュー指摘への対応。AAPI-P-42。E 5.9・FARC-P-27・36・39 の置き場) | 3.5 |
| FMOD-P-15 | `admin/lib/leaseExpiry.ts`: 番兵日時を判定し「期限切れ」にする 1 か所。`lease_expires_at` の表示はすべてここを通す | 承認済みの案(ゲート3。2026-11-23。E 5.9・FARC-P-24 の置き場) | 3.5 |
| FMOD-P-16 | S3・S4 共有のフォーム(`form/`): `connectors/fileSystem.ts`・`fromSettings`・`toRequest`・`rules`・`fieldMap`・`serverErrors`。TTL モード・しきい値の丸め注意・`malformed` の判定を `fromSettings` に持たせる | 承認済みの案(ゲート3。2026-11-23。E 7.5〜7.7・FARC-P-16・28・29 の置き場) | 3.9 |
| FMOD-P-17 | ルートは**遅延読み込みしない**(MVP。同期 import の単一チャンク)。根拠: 9 画面で規模が小さく、再配備後の開いたままのタブの旧アセット取得失敗(E 3.3)と構成の複雑さを避けられる。ただし**ビルドサイズの実測前の判断**で、実装後に測って再判断する(FMOD-U-11)。使うことにした場合は `router.onError` を足す(E 3.3・FARC-P-18) | 承認済みの案(ゲート3。2026-11-23。E 12.6 の「遅延読み込みの判断」への回答) | 4.1 |
| FMOD-P-18 | 依存ルール R1〜R16(ESLint `no-restricted-imports` を第一候補。`tests/` は R2・R3 のみ) | 承認済みの案(ゲート3。2026-11-23) | 6章 |
| FMOD-P-19 | テストの配置: 単体は対象の隣(`*.test.ts`)、`tests/support/`・`tests/e2e/` | 承認済みの案(ゲート3。2026-11-23。E 10 の置き場) | 7.1 |
| FMOD-P-20 | フィクスチャは EP×状態の関数で Vitest・Playwright が共有し、生成型で `satisfies`。`apiErrors.ts` のビルダー | 承認済みの案(ゲート3。2026-11-23。E 10.2 の実装) | 7.3 |
| FMOD-P-21 | `data-testid` は部品の `testid` props でルート要素に付け、付く位置を部品の中で固定。命名は DS 9・画面仕様 | 承認済みの案(ゲート3。2026-11-23。命名の細則は DS で案) | 3.6 |
| FMOD-P-22 | 画面 → route → ページ → composable → EP の対応表(4.1)と、操作ごとの対応(4.2) | 承認済みの案(ゲート3。2026-11-23。B 1.3・E 5.7・5.8 の展開) | 4章 |
| FMOD-P-23 | アイコンは `shared/theme/icons.ts` だけが `@mdi/js` を import | 承認済みの案(ゲート3。2026-11-23) | 3.1・6章 |
| FMOD-P-24 | ファイル名: `PascalCase.vue`・`useXxx.ts`・`camelCase.ts`・`kebab-case` ディレクトリ | 承認済みの案(ゲート3。2026-11-23) | 2.1 |
| FMOD-P-25 | ルート直下の設定ファイルの一覧(名前のみ)。`@` は `src` の別名 | 承認済みの案(ゲート3。2026-11-23) | 2.4 |
| FMOD-P-26 | ナビは route `meta` で一元管理、ページテンプレート 4 型、DS 4.5・4.8 の状態表示(読み込み中・空・エラー・stale)と危険度別の確認ダイアログの規約(旧 FMOD-K-1)。DS 4 章のその他の部品(4.15 の具体値・4.18〜4.20 ほか)は DS の区分に従う(案) | 承認済みの案(DS 4.5・4.8・5.3・6章のゲート B・C の承認事項の引用。ユーザー確認済み(ゲート3。2026-11-23)) | 3.6・3.7 |
| FMOD-P-27 | `viewState`(`loading`・`empty`・`error`・`notfound`・`stale`・`ready`+更新中・更新時刻・診断・再試行の可否)を `features` の composable が `useViewState`(`admin/composables`。`describeError` を使う)で作り、`templates` はそれだけを props で受ける(R7) | 承認済みの案(ゲート3。2026-11-23) | 3.7 |
| FMOD-P-28 | パンくずは `AppShell` が `useBreadcrumbs` で作って provide し、`PageHeader` が inject する(`PageBreadcrumbs` は `templates`)。`shell` と `templates` の層の向き、`templates` と `components` の同層禁止を保つため | 承認済みの案(ゲート3。2026-11-23) | 3.7 |
| FMOD-P-29 | 外部リンクは route を持たない定義表(`shell/externalLinks.ts`)で持ち、`featureFlag` の評価は `SideNav`・外部リンク領域だけ(ガードでは評価しない)。DS 5.3 との差は E の I-89 | 承認済みの案(ゲート3。2026-11-23) | 3.5・3.7 |
| FMOD-P-30 | ロック状態の写像は `admin/lib/lockStateView.ts`(S2・J2・DLG-1 が共有。E 5.10) | 承認済みの案(ゲート3。2026-11-23) | 3.5 |
| FMOD-P-31 | セルの表示状態 `cellState`(`value`・`unavailable`・`unreadable`・`none`)と、値があるはずの項目の表 `expectedFields.ts`。引く対象の `unavailable`(行または最上位)を引数に取る。`status=null` のジョブはタグ・操作なし(E 5.9。FARC-P-36) | 承認済みの案(ゲート3。2026-11-23。B の AAPI-P-25 は同じゲート3で承認)の修正(PR #10 のレビュー指摘への対応。AAPI-P-42) | 3.5・3.9 |
| FMOD-P-32 | `jobActions.ts` は `rerun_blocked_reason=source_missing` を「出さない」(E 6.7。FARC-P-37) | 承認済みの案(ゲート3。2026-11-23。AAPI-P-41) | 3.9 |
| FMOD-P-33 | 一覧の EP(EP-01・09・11)の画面は、行の `unavailable`(`rowCell`)で取得失敗を判定し、最上位の `unavailable`(`topCell`)は行に属さない項目(EP-11 の `tab_counts.<タブ>`・`document_count`)と単一の応答だけに使う。S1・J1・X1 の行モデルは行ごとに失敗を持つ | 承認済みの案(ゲート3。2026-11-23)の修正(PR #10 のレビュー指摘への対応。2026-11-23。AAPI-P-42・FARC-P-39)。**`-K-` ではない** | 3.5・3.9・5.5 |

### 8.4 未決・実装時確認(FMOD-U)

| ID | 内容 | 決める場所 |
| --- | --- | --- |
| FMOD-U-1 | ESLint `no-restricted-imports`(パターン・否定・`files` ごとの設定)で R1〜R16 を表せるか。足りなければ `eslint-plugin-boundaries`・`dependency-cruiser` | 実装時 |
| FMOD-U-2 | 生成 SDK がパスの値をどうエンコードするか(`job_id`・`source_id`。FARC-U-18)。FMOD-P-4 の手順 (1)〜(3) の確認 | 実装時 |
| FMOD-U-3 | Hey API 0.99 の生成物のファイル構成と、`admin/api/index.ts` で再 export する範囲(FARC-U-4・5) | 実装時 |
| FMOD-U-4 | `AdminDataTable`・`AdminDataTableServer` が `VDataTable`・`VDataTableServer` の差(`@update:options`・`hover`・`aria-sort`・単一ソート。FARC-U-2)を吸収できるか | 実装時 |
| FMOD-U-5 | `ConfirmDialog` が Vuetify の `VDialog` で DS 4.8 のフォーカス規則(閉じ込め・復帰・`persistent`)を満たすか(FARC-U-14) | 実装後(`web-ui-reviewer`) |
| FMOD-U-6 | `ShardMatrix` の列数の算出(`ResizeObserver`)の jsdom でのテスト方法(FARC-U-9)と、列見出しの読み上げ(opensearch 7章) | 実装時 |
| FMOD-U-7 | `shared/` の範囲の見直し(Search View の設計時。FARC-U-17) | Search View の設計 |
| FMOD-U-8 | 実 API のスモークの置き場(`tests/e2e/smoke.spec.ts` か、`tests/integration/<名前>/` の慣習か) | 実装時 |
| FMOD-U-9 | `.`・`..` だけの ID の扱い(ブラウザの URL の正規化。推測)。取得しない扱いでよいか | 実装時 |
| FMOD-U-10 | 動的な `meta.title`(関数。I-83)と `PageBreadcrumbs`・`useBreadcrumbs`・`document.title` の実装の詳細 | 実装時 |
| FMOD-U-11 | ルート遅延読み込みをしない判断(FMOD-P-17)を、実装後のビルドサイズ(Vuetify の tree-shaking 後の JS・CSS)の実測で再判断する | 実装後 |

### 8.5 既存設計との不整合(I-n)

| ID | 内容 | 本書での扱い |
| --- | --- | --- |
| I-100 | 画面仕様(sources 1.3・documents 4章)は `PageHeader`(DS 6.1)と呼ぶが、DS には部品としての節・名前の定義がない(6.1 の「ページ見出し領域」) | `admin/templates/PageHeader` と命名(3.6)。DS への追記は HO-27 |
| I-101 | DS 4.15 は `ShardMatrix`・`ClusterSummary`・`IndexFilter`・凡例・ページ送りバーを 1 つの節に含め、独立した節・部品名の一覧がない | `admin/components/shard-matrix/` にまとめて置く(3.6)。部品名は DS 4.15・opensearch 3章の記述に従う |
| I-102 | 画面仕様(documents 4章)の「注記ブロック」(アイコン+文。`role` なし)は DS 4章に部品の定義がない | `admin/components/note-block/` に置く(3.6)。DS への追記は HO-27 |
| I-103 | DS 4.8 は確認ダイアログを `VDialog` の構成として定義し、部品名がない(admin-view は DLG-1〜5 と呼ぶ) | `ConfirmDialog`・`ConfirmCheck`・`TypeToConfirm` と命名(3.6)。DLG-5 は S2(sources)と J2(jobs)の両方から開くため `dialogs/` に置く(R8) |
| I-104 | (解消済み。作業記録 0017)B 1.3 と E 5.7 は D1 が EP-14 を使うとしていたが、dashboard 画面仕様に cron のタイムゾーン・Dashboards の URL を使う項目がない(外部リンクはサイドバー。dashboard 3.2) | E 5.4・5.7 と B 1.3 が EP-13 のみに直り、F の 3.9・4.1 の記述(D1 は EP-13 だけ)と一致した |

E の I-120(値の読めない `null` の表示)・I-121(`source_missing` の文言)は 3.5・3.9 に反映している(F では再掲しない。ゲート3でユーザー確認済み。2026-11-23)。E の I-88(孤児ロック・取得直後の導線が J2 でなく S2)・I-89(`featureFlag`)は、本書の 3.5・3.7・3.8・5.1・6章に反映している(F では再掲しない。ゲート3でユーザー確認済み。2026-11-23)。

### 8.6 E 12.6「F への引き継ぎ」の割り当て

| E の引き継ぎ(12.6・0013・0015) | 本書での割り当て |
| --- | --- |
| (1) `apps/web/` のディレクトリ構成(生成コード・API ラッパー・key factory と composable・エラー変換表・Router と `meta`・テンプレート 4 型・DS の共通部品・画面ごとのモジュール・テスト・`mockApi`・フィクスチャ) | 2.1(構成)、3.3(生成コード・ラッパー・エラー変換表)、3.4(key factory・composable)、3.5・3.7(Router・`meta`・テンプレート)、3.6(DS の共通部品)、3.9(画面ごと)、7章(テスト・`mockApi`・フィクスチャ) |
| (2) 5.7 の表を「画面 → route → ページ → composable → EP」に展開 | 4.1(9 画面+シェル+404)、4.2(操作) |
| (3) DS 4章の全部品の置き場 | 3.6(全件) |
| (4) 依存ルール(ESLint `no-restricted-imports`) | 6章(R1〜R16)。限界は FMOD-U-1 |
| (5) 定義表の置き場(`navGroups`・`documentTabs`・`dashboardComponents`・URL ↔ API・エラー変換表・フォーム `field` 対応) | 3.5(表) |
| (6) トークンと `defaults` を Search View と共有できる置き場 | 2.3・3.1(`shared/theme`) |
| ルート遅延読み込みの判断(`router.onError`) | FMOD-P-17(遅延読み込みしない) |
| `job_id`・`source_id` のパスエンコードをどの層で保証するか(FARC-U-18) | 3.3(FMOD-P-4。`admin/api` の層。確認は FMOD-U-2) |
| `unavailable` を引く関数(行の `unavailable`・最上位の `unavailable` の 2 系統。行単位で判定) | 3.5(FMOD-P-14・FMOD-P-33) |
| 日時整形の番兵を判定する 1 か所 | 3.5(FMOD-P-15) |
| S4 のフォームモデルのしきい値の丸め注意の状態 | 3.9 の `form/fromSettings.ts`(FMOD-P-16) |

**E の FARC への対応**(本書が置き場を決めたもの): FARC-P-6・7(生成とクライアント)→ 3.3、P-8・9・11・12・25・27(Query)→ 3.4、P-10(ページング)→ 3.5・3.9、P-13・14・15(エラー)→ 3.3・3.8、P-16・28・29(フォーム)→ 3.9、P-17(状態管理)→ 3.2・3.4・3.9、P-18(Router)→ 3.5・3.7・4.1、P-21〜23(テスト・静的解析)→ 6・7章。FARC-U のうち、F が引き継ぐのは U-2→FMOD-U-4、U-4・5→FMOD-U-3、U-9→FMOD-U-6、U-14→FMOD-U-5、U-17→FMOD-U-7、U-18→FMOD-U-2。

### 8.7 E・B・DS・画面仕様への修正依頼

- **E への修正依頼**: なし(I-104 は 0017 で解消済み。E 12.6 には「F 8.6 で全件割り当て済み」が追記済み)。
- **B への修正依頼**: なし(B 1.3 の D1 の行は 0017 で EP-13 のみに直った)。
- **DS・画面仕様への追記候補(HO-27。変更はしない)**: `PageHeader`・注記ブロック・確認ダイアログの部品名(I-100・102・103)、`ShardMatrix` の部品群の名前(I-101)。E の I-80〜89 の追記候補は E に従う。

### 8.8 この文書が決めないこと

- 各部品・composable の内部の実装(Vuetify の props・CSS・アニメーション)。DS・画面仕様に従う。
- Search View のモジュール構成、`search/` の層、同一ビルドにするか(FMOD-U-7)。
- CI・compose・Dockerfile の定義(E 3.5・11.2。infra の前提作業)。
- API の導出ロジック(C)、API 側のモジュール構成(D)。
