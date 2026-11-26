# ui-admin フロントエンドモジュール構成設計書 v0.2

- 版: v0.2(ドラフト。E(`ui-admin-frontend-architecture-v0.2.md`)・B と、実装済みの Admin API の OpenAPI に基づく。ゲート4・5(2026-11-26)の承認を反映済み。実装はスコープ外で、実装時確認事項(FMOD-U)が残る)
- 更新日: 2026-11-26
- 前版: `ui-admin-frontend-module-structure-v0.1.md`(v0.1。2026-11-23。変更しない)
- 位置づけ: Admin View(`apps/web/`)のコード上の**モジュール分割・ディレクトリ・依存ルール・画面とモジュールの対応**を定める。「何を、どのモジュールが担うか」を一目で分かるようにする。技術構成・データ取得の方針・エラー処理の UI 対応・テスト方針は E、見た目・部品の仕様は DS と画面仕様、EP・DTO・エラー code は B と実 OpenAPI が正本で、本書は**参照して置き場を決める**(再掲しない)。**v0.2 だけで実装を始められる**ように、v0.1 の内容を保ったまま書き直している(v0.1 の参照は要らない)。
- 本書は **Admin View のフロントエンド設計 v0.2 の作成タスク(`20261126_create_admin_ui_system_design`)の成果物**で、SD・PD・DS・画面仕様・B・C・D・v0.1 を変更せず、A は冒頭と 9 章(HO の追記・状態更新)を除き変更しない。E・B に直してほしい点は 8.7 に「修正依頼」として挙げる。既存設計との食い違いは `I-n`(8.5)に挙げる。追従改訂が要る点は A の 9章(HO)に集約し、本書は申し送りを持たない。
- 「作業記録 NNNN」は、同タスクの `agent_tasks/20261126_create_admin_ui_system_design/NNNN-*.md`。本書で「確認(2026-11-26)」と書いた事実は、実装済みの Admin API から書き出した OpenAPI(OpenAPI 3.1・12 パス・14 EP。作業記録 0004)と、Hey API・Vite・Nginx の検証(作業記録 0005)で確かめたもの。

## 改訂履歴(v0.1 からの変更点)

v0.1 の承認済み方針(FMOD-P)は中身を保って引き継いだ。変えたのは次の表のもの(ゲート4。2026-11-26。ユーザー承認。執筆中に決めた設計の詳細と軽微な導出はゲート5。2026-11-26 で追認)だけ。v0.1 の改訂履歴(レビュー対応・ゲートごとの区分の変遷)は本文から外した。ID の欠番(FMOD-K-1)は欠番のまま残している。

| 変更 | 内容 | 本書の節 |
| --- | --- | --- |
| 配信方式 | Web UI は `api` ではなく **`web` コンテナ(Nginx)が静的配信**し、`/api/` を `api` へプロキシする(ブラウザから見て同一オリジン。CORS 不要は維持)。FMOD-K-4 を更新(確定(ユーザー指示 2026-11-26。作業記録 0003))。`api` は compose でホストに publish せず、ブラウザ・開発・結合テストは `web` 経由 | 1.1・2.1・2.4 |
| 版・Node | Vue Router 5.5.1、Node 下限 `^22.22.2 \|\| ^24.15.0 \|\| >=26`、jsdom 31、`sass`・`@types/node` を明記、固定範囲の具体化(E 2 章) | 2.4 |
| `admin/api` の責務 | クライアントの設定 `configureApiClient()`(タイムアウト付き fetch・`interceptors`。`baseUrl` は生成物が持つ)、**実行時エラーの正規化**(`interceptors.error` に `toApiError`。FMOD-P-34。FARC-P-44)、**パス値の送信前検証**(`interceptors.request`。FMOD-P-4 の拡張)、生成型は `{Op}Response2` でなくスキーマ型を使う、生成・ビルド設定(FARC-P-45)。いずれも E 5.3 に合わせた | 1.2・3.2・3.3 |
| ルート直下の設定ファイル | `.nvmrc`・`engines`・`.npmrc`(`engine-strict=true`)・`Dockerfile`(web)・`nginx/default.conf` を追加(FMOD-P-35) | 2.1・2.4 |
| 実 OpenAPI との照合による訂正 | 単一応答の最上位 `unavailable` を持つのは EP-02・10・11 だけ(EP-12・13・14 は持たない)。EP-01 の `status=null` の行、行型ごとの `expectedFields`、`documentTabs` の行型とアダプタ、`SourceSettings` が 2 種類、`fieldMap` の追加、`stalled=true` かつ `lease_expires_at=null`、`released=false`、`existing_job` の未知値、O1 は API の並びを使う、EP-12〜14 には query を付けない | 3.3〜3.5・3.8・3.9 |
| DLG-4 の null | J2 の `force_delete`・`rewrite_mode` が null のときは false として送り、「記録なし(なしとして実行)」と表示(FARC-P-46) | 3.8 |
| 画面 → EP の対応 | 実 OpenAPI で照合し、生成 SDK の関数名・Query の名前に直した。EP-05 の 202 直後に S1 の行が「削除中」になるとした v0.1 の記述を訂正(S1 の行は変わらないことがある) | 4章 |
| 主要シナリオ以降 | 5.1・5.3 の訂正、6 章の生成コードの注記、7 章の契約テスト(`errorTable` ↔ OpenAPI)、8 章の確認状況(U の状態、前提タスクへの依存) | 5〜8章 |

**前提タスク**(本書の範囲外の実装作業。本書は完了への依存を該当箇所に書く):

- **A**: Admin API の OpenAPI の型・docstring の修正(`apps/api` のみ)。`ttl_days`・`ttl_seconds` を「任意かつ非 null」にし、`openapi_export.py` の docstring を「コミットする」に合わせる。**型の生成の前が望ましい(必須ではない。前でも `toRequest` が `ttl_*` の null を送らないので進められる。8.9)**。
- **B+C**: `web` コンテナ(Nginx。`apps/web` の Dockerfile・Nginx 設定・compose の `web` サービス)の追加と、`api` 側の追従(EP-13 の `web` 判定を `web` への HTTP 確認に置換、`api` の `ports` を compose から外し結合テストの上書きで publish、README・テストの更新)。**`apps/web` の最初のスキャフォールドの後に着手し、`web` 経由の接続確認と初回リリースの前に完了する(8.9)**。開発は Vite の dev サーバーと `/api` プロキシで始められる。

区分の凡例(A・B・E と同じ):

| 区分 | 意味 |
| --- | --- |
| 確定 | ユーザーが明示的に回答・確定した事項(出典を書く)、または確定として書かれた既承認文書の引用 |
| 承認済みの案 | ユーザーが承認したゲート(ゲート1〜3=v0.1、ゲート4・5=2026-11-26)で承認された案。確定ではない。**v0.2 で新規・変更した判断は「承認済みの案(ゲート4。2026-11-26)」。ゲート4 の承認後に執筆中に決めた設計の詳細と軽微な導出は、ゲート5 で追認された「承認済みの案(ゲート5。2026-11-26)」**。区分欄に承認したゲートを書く |
| 案 | ユーザーが承認していない提案。確定(`-K-`)にしない |
| 未決 | 決めていない。実装時に確認するものを含む |
| 推測 | 根拠が弱い想定 |
| 導出 | 他の記述から導いた事項 |

ID 体系: `FMOD-K-n` / `FMOD-P-n` / `FMOD-U-n`。既存設計との不整合は `I-n`(本書の予約範囲は I-100〜109 と I-130〜139。E は I-80〜89 と I-120〜129、B は I-70〜79、A は I-60〜69、C は I-90〜99、D は I-110〜119)。E の ID は `FARC-*`、A は `BAPI-*`、B は `AAPI-*`、エンドポイントは B の `EP-nn`。DS・画面仕様の節は `DS 4.5`・`sources 2.3` のように書く。

関連文書(いずれも `docs/v0.x/` 配下):

| 略称 | 文書 | 本書との関係 |
| --- | --- | --- |
| E | `system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.2.md`(v0.2) | 技術構成・ビルド・配信(Nginx)・データ取得層・エラー処理・テスト方針の正本。本書は置き場を決める。節番号は v0.1 を保ち(5.3 API クライアント、5.7 画面別の取得、5.8 mutation、5.9 Vue の注意、6 章 エラー、7 章 フォーム)、3.6(`web` と `api` の関係)・12.7(照合の差分一覧)・12.8(前提タスク)が増えた |
| B | `system-design/api/admin/admin-api-v0.1.md`(v0.1) | EP・DTO・code の正本。実装・OpenAPI と食い違う箇所は実装が正(差分は E 12.7) |
| A | `system-design/api/api-base-design-v0.1.md`(v0.1) | URL・エラー形式・OpenAPI。9章が申し送り(HO)の置き場 |
| C・D | `system-design/api/admin/admin-api-architecture-v0.1.md`、`admin-api-module-structure-v0.1.md`(v0.1) | Admin API の内部設計。本書は EP・code の結果だけを使い、内部には依存しない |
| DS | `ui-design/design-system-v0.1.md` | 共通コンポーネント(4章)・シェル(5章)・テンプレート(6章)・`data-testid`(9章) |
| admin-view・画面仕様 | `ui-design/admin-view-v0.1.md`、`ui-design/admin/*.md` | route `meta`(4.2)・画面ごとの部品・状態・`data-testid` |
| v0.1 | `ui-admin-frontend-{architecture,module-structure}-v0.1.md` | 前版。参照は不要(本書が内容を含む) |

---

## 1. 概要

### 1.1 設計の考え方(前提: FMOD-P-26・FMOD-K-2・FMOD-K-3・FMOD-K-4)

- **層で分ける**。下の層は上の層を知らない。データ取得(`api`・`queries`)と見た目(`components`・`templates`)と画面(`features`)を混ぜない(2章・6章)。
- **画面は薄く**する。画面は「どのデータを、どの部品に、どの状態で見せるか」だけを持ち、取得・エラーの変換・検証・URL の読み書きは下の層の共通部品に任せる(E 1.2。対応表を 1 か所に持つ)。
- **生成コードと HTTP は `admin/api` に閉じ込める**。生成型・生成クライアントを直接 import してよい層は `admin/api` だけで、外には公開口(`@/admin/api`)の再 export だけを見せる(3.3・6章 R2)。API の形・実行時エラーの形の変化を `admin/api` で吸収する。
- **DS の共通コンポーネントはすべて決まった場所に置く**(3.6)。画面固有の組み合わせだけを `features` に置く。
- **Search View と共有できる層を分ける**(DS 11)。共有するのはトークン・Vuetify `defaults`・共通の状態表示と、API 共通のエラーの形だけ。Search View は設計しない(境界だけ)。
- **配信**(FMOD-K-4。**v0.1 から更新**): Admin View は `/admin/` 配下の SPA で、**`web` コンテナ(Nginx)が静的に配信**し、`/api/` を `api` コンテナへリバースプロキシする。ブラウザから見て同一オリジンなので CORS は要らない。`apps/web/` が自前の Dockerfile を持つ(Node でビルド → Nginx に `dist/` を載せる。E 3.5)。`api` は静的配信をしない。Nginx の設定の中身は E 3.3(FARC-P-40・41)で、前提タスク B+C の完了後に有効になる。

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
| `admin/queries` | 2 | key factory と `withKey`(生成 Options の key の差し替え)・読み取りの composable・書き込み(mutation)・invalidate の表・ポーリング・Query の既定値 | `admin/api` | Query の結果 |
| `admin/composables` | 2 | 汎用の composable(URL ↔ 条件、要素の幅、debounce、タイトル、`useBreadcrumbs`、`useViewState`) | vue・vue-router・`@/admin/api`(公開口の `describeError`)・`lib` | composable |
| `admin/api` | 1 | 生成コード・クライアントの設定(`configureApiClient`。タイムアウト付き fetch・`interceptors`)・公開口・**実行時エラーの正規化**(error interceptor)・エラー変換表・**パス値の検証**(request interceptor と画面側のガードが共有する純関数) | OpenAPI 生成物、`shared/api`(`admin/` 内の他モジュールは import しない。R17) | 生成の Options・Mutation と型(公開口)、`configureApiClient`、`ApiError`、`describeError`、`isValidPathId` |
| `admin/lib` | 1 | 純粋な関数・型(`unavailable` の参照・セルの表示状態、番兵日時、検証規則、単位・丸め、route 名の定数、`ViewState`・`lockStateView`・inject の key、`existing_job` の判定、OpenSearch の状態値) | — | 値 |
| `shared/ui` | 0 | Search View と共有できる共通部品(`StatusTag`・状態ブロック・アラート・フォーム項目・スナックバー) | props | 部品 |
| `shared/theme` | 0 | トークン(色・variables)・Vuetify `defaults`・`display`・SASS・アイコン | — | `createVuetify` の設定 |
| `shared/api` | 0 | `ApiError` の型・型ガード・A 5.2 のエラー本文の読み取り(生成型に依存しない) | JSON の値 | `ApiError`、本文の判定 |
| `shared/lib` | 0 | 日時・数値の整形 | — | 文字列 |

---

## 2. 構成

### 2.1 ディレクトリ構成(FMOD-P-1・FMOD-P-35)

名前は案(コード・設定ファイルは本タスクで作らない)。`@` は `src` の別名(案)。

```text
apps/web/
├─ index.html                      # <html lang="ja">。外部リソースなし(E 3.1)
├─ package.json / package-lock.json   # engines は Node の下限(2.4)
├─ .nvmrc                          # Node 24 系(24.15.0 以上。推奨。E 2.1)
├─ .npmrc                          # engine-strict=true
├─ Dockerfile                      # web イメージ: Node 24 系(24.15.0 以上)でビルド → Nginx に dist/ を載せる(E 3.5。前提タスク B)
├─ nginx/
│  └─ default.conf                 # /admin/ の配信と /api/ のプロキシ(E 3.3。FARC-P-40・41。前提タスク B)
├─ vite.config.ts                  # base '/admin/'、vuetify プラグイン、dev proxy、Vitest 設定
├─ tsconfig.json / tsconfig.app.json / tsconfig.node.json
├─ eslint.config.js / .prettierrc / .prettierignore     # 依存ルールは 6章。生成コード・`openapi/` は対象外
├─ openapi-ts.config.ts            # Hey API の設定(3.3)
├─ playwright.config.ts            # baseURL は http://localhost:5173/admin/(E 10.2)
├─ openapi/
│  └─ admin-v1.json                # Admin API の OpenAPI の書き出し(コミット。E 5.2)
├─ src/
│  ├─ main.ts                      # import 'vuetify/styles'(2.4)・configureApiClient() の 1 回の呼び出し(E 5.3)・admin/app の起動
│  ├─ shared/                      # ── Search View と共有できる層(層 0)──
│  │  ├─ theme/                    # tokens.ts・defaults.ts・display.ts・icons.ts・settings.scss・global.css
│  │  ├─ ui/                       # StatusTag・statusMaps・StateBlock・PageAlert・FormField・ErrorSummary
│  │  │                            # AppSnackbar・useSnackbar・TopProgress・IdText・TimeText
│  │  ├─ api/                      # apiError.ts(ApiError・isApiError・readErrorBody)
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
│     ├─ queries/                  # keys.ts・withKey.ts・queryClient.ts・polling.ts・placeholder.ts・invalidation.ts
│     │                            # meta.ts・dashboard.ts・sources.ts・jobs.ts・documents.ts・opensearch.ts・mutations/
│     ├─ composables/              # useListParams.ts・useContainerWidth.ts・useDebouncedRef.ts・useDocumentTitle.ts・useBreadcrumbs.ts・useViewState.ts
│     ├─ api/                      # 生成コードと、それを包む手書きの層(3.3)
│     │  ├─ generated/             # Hey API の出力(手で編集しない。コミットする。lint・format の対象外)
│     │  │  ├─ index.ts・client.gen.ts・sdk.gen.ts・types.gen.ts
│     │  │  ├─ @tanstack/vue-query.gen.ts
│     │  │  └─ client/・core/      # 生成クライアントのランタイム
│     │  ├─ client.ts              # configureApiClient(): setConfig(タイムアウト付き fetch)・interceptors 2 つ。baseUrl は設定しない(生成物が持つ)
│     │  ├─ pathParams.ts          # パス値の検証の純関数(isValidPathId。値全体が . か ..・空・制御文字を含む・文字列でない、を拒否)。request interceptor と画面側のガードが共有
│     │  ├─ index.ts               # 公開口: スキーマ型・生成の Options・Mutation・configureApiClient・isValidPathId・ApiError・describeError の再 export
│     │  └─ errors/                # toApiError.ts(error interceptor に登録)・errorTable.ts・describeError.ts
│     └─ lib/                      # unavailable.ts・expectedFields.ts・leaseExpiry.ts・existingJob.ts・clusterValues.ts・routeNames.ts
│                                  # actions.ts・units.ts・lockStateView.ts・viewState.ts・injectionKeys.ts・validation/
└─ tests/
   ├─ support/                     # setup.ts・mount.ts・fetchStub.ts・mockApi.ts・apiErrors.ts・fixtures/
   └─ e2e/                         # *.spec.ts(Playwright)
```

- **実 API の接続確認 `tests/integration/<名前>/` はこの木に含まれない**: **リポジトリ直下**(`apps/web/` の外。既存の `tests/integration/{api,crawler,indexer}/` と同じ階層)に置く(7.1。前提タスク B+C の完了後)。`apps/web` の ESLint・tsconfig の対象外なので、R2・R3 は適用されない(6章)。ツール・言語とその lint は実装時に決める(FMOD-U-8)。
- **ファイル名**: Vue の部品は `PascalCase.vue`、composable は `useXxx.ts`、それ以外は `camelCase.ts`、ディレクトリは `kebab-case`(FMOD-P-24)。
- **単体テストは対象の隣**(`*.test.ts`。7章)。
- **生成コード**(`src/admin/api/generated/`)と `dist/` は lint・format の対象外(E 11.1)。生成コードは**専用のディレクトリに置く**(手書きの `client.ts` と、生成の `client/`・`client.gen.ts` が同じ場所に並ぶと紛らわしく、再生成でも手書きを消さないため。導出)。
- **生成ディレクトリの中身**は、実 OpenAPI から Hey API 0.99.0 で生成した結果(確認 2026-11-26。作業記録 0005): `infiniteQueryOptions: false` の設定で**約 111KB・17 ファイル・約 4,260 行**(`@tanstack/vue-query.gen.ts` は約 286 行)。既定の設定では 114KB・375 行(vue-query)。再生成しても出力は同一(タイムスタンプ・絶対パスなし。**同一性は既定の設定で確認した**)なので、コミットしても spec の更新時以外に差分は出ない。

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
- **生成コードは層 1 の `admin/api` の内側に閉じる**。層 1 より上のモジュールは、生成型を `@/admin/api`(公開口)の再 export としてだけ使う(3.3)。

### 2.3 Search View との境界(FMOD-P-2)

- **共有する**: `shared/theme`(トークン・`defaults`・`display`・SASS・アイコン。DS 11)、`shared/ui`(`StatusTag` と `statusMaps`、状態ブロック、アラート、フォーム項目、スナックバー)、`shared/api`(API 共通のエラーの形。A 5.2)、`shared/lib`。
- **共有しない(Admin 専用)**: シェル(サイドバー)、テンプレート 4 型、データテーブル(行の操作つき)、危険度別の確認ダイアログ、`KeyValueList`(DS 11)、`admin/` 配下すべて。
- Search View の配置・同一ビルドにするか・`search/` の構成は決めない(FARC-U-17。FMOD-U-7)。**`web` コンテナは将来 Search View も配信しうる**(Nginx の配信の枠組みは Admin View 専用ではない)が、その配置は決めない。

### 2.4 ルート直下の設定ファイル(名前と要点だけ。FMOD-P-25・FMOD-P-35)

中身は実装で書く。ここには、他の節・E と整合させる要点だけを書く。

| ファイル | 要点 |
| --- | --- |
| `package.json` | `engines.node` は `^22.22.2 \|\| ^24.15.0 \|\| >=26`(jsdom 31 の要件。推奨は 24。Docker・CI は 24.15.0 以上の 24 系。FARC-P-3)。スクリプトは E 11.1。`sass` は **dependencies**(`vite-plugin-vuetify` の `styles.configFile` を使うと必須。`sass-embedded` は不要)、`@mdi/js` も明記、`@types/node` は `^24`(devDependencies)。固定範囲は E 2 章(Vuetify `4.3.4`・Hey API `0.99.0`・Playwright `1.65.1` は exact、Vite `~8.3.8`・`vue-tsc ~3.3.14`・TypeScript `~6.0.3`・Vue Router `~5.5` ほか) |
| `.nvmrc`・`.npmrc` | Node 24 系(24.15.0 以上)。`engine-strict=true`(下限を満たさない Node での `npm ci` を失敗させる)ので、Docker・CI の Node も **24.15.0 以上の 24 系**にする |
| `Dockerfile`・`nginx/default.conf` | `web` イメージの定義と Nginx 設定。中身は E 3.3・3.5(前提タスク B) |
| `vite.config.ts` | `base: '/admin/'`、`@vitejs/plugin-vue`、`vite-plugin-vuetify`(`styles.configFile`)、dev proxy(`/api` の転送先は、compose で起動した `web` の公開ポート(`http://127.0.0.1:<WEB_HOST_PORT>`)が既定で、dev 専用の環境変数で上書きできる。`api` に直接つながらない。E 3.4。FARC-P-19)、Vitest 設定。`process.env` を読むので `tsconfig.node.json` に `@types/node` と `"types": ["node"]` が要る。`build.target` は既定のまま |
| `tsconfig*.json` | `strict`。**`exactOptionalPropertyTypes` は有効にしない**(生成コードの型検査が通らない。確認 2026-11-26)。生成ディレクトリは型検査の対象に含める(除外するのは lint・format) |
| `eslint.config.js`・`.prettierrc`・`.prettierignore` | 依存ルールは 6章。生成コード(`src/admin/api/generated/`)・`dist/`・`openapi/admin-v1.json`(API の出力をそのままコミットする。E 11.1)は lint・format の対象外 |
| `openapi-ts.config.ts`・`openapi/admin-v1.json` | 生成設定と入力の OpenAPI(3.3。E 5.2) |
| `playwright.config.ts` | `baseURL` は `http://localhost:5173/admin/`(E 10.2) |
| `src/main.ts` | `import 'vuetify/styles'` が**必須**(`vite-plugin-vuetify` はコンポーネント単位の CSS しか入れず、これが無いとリセット CSS・タイポグラフィ・ユーティリティが入らない。確認 2026-11-26。`styles.configFile` の変数もここに効く)。FARC-P-45。加えて **`configureApiClient()`(`@/admin/api`)を admin/app の起動より前に 1 回呼ぶ**(関数は冪等で、2 回目以降は何もしない。interceptor は二重に登録されない。3.3。E 5.3) |

---

## 3. モジュール詳細

### 3.1 `shared/theme`

| ファイル | 内容(正本) |
| --- | --- |
| `tokens.ts` | `theme.themes.light.colors`(DS 2.1 の色名と値。独自の色名 `*-container`・`on-*-container`・`focus`・`ink`・`line-strong` を含む。DS 3.1・3.4)・`variables`(`border-color`・`border-opacity`・`medium-emphasis-opacity`。DS 3.1) |
| `defaults.ts` | Vuetify の `defaults`(DS 3.2 の表) |
| `display.ts` | `display.mobileBreakpoint: 'md'`(DS 3.1・7。実機確認は FARC-U-14) |
| `icons.ts` | 使う `@mdi/js` のアイコンを**ここだけ**で名前付き import して再 export。`mdi-svg` の iconset 設定(DS 3.1。FMOD-P-23) |
| `settings.scss` | `vite-plugin-vuetify` の `styles.configFile`(DS 3.3)。`$body-font-family` など。`sass` が必須(2.4) |
| `global.css` | フォーカスリング・役割名のタイポグラフィのクラス(`text-page-title` など。DS 2.2・2.6)・`prefers-reduced-motion` |

`createVuetify` の組み立ては `admin/app/setupVuetify.ts`(`shared/theme` を読むだけ)。Search View も同じ 3 ファイルを読む。

### 3.2 `shared/ui`・`shared/api`・`shared/lib`(`shared/api` は FMOD-P-3・FMOD-P-34)

| モジュール | 内容 | 根拠 |
| --- | --- | --- |
| `StatusTag.vue`・`statusMaps.ts` | `kind`(`job`・`source`・`health`・`deletion`・`cluster` ほか)と `value` を受け、**1 つのマップ**から色・アイコン・形・文言を引く。未登録の値は中立+開発時に警告(OpenSearch の状態値は API が string で返すため、未知値はここで中立表示になる。3.5 の `clusterValues.ts`)。値の追加は行を足すだけ | DS 4.1 |
| `StateBlock.vue` | 空・エラー(データなし)・見つかりません・読み込み中(スケルトン)の共通ブロック。`role`・`aria-busy`・視覚的に隠した文言を持つ | DS 4.5。E 6.2 |
| `PageAlert.vue` | 左帯つきのページ内・ダイアログ内アラート(`info`・`warning`・`error`。`role` を props で切替) | DS 4.7 |
| `FormField.vue`・`ErrorSummary.vue` | ラベル上・「必須」表示・ヘルプ・検証エラー(`aria-invalid`・`aria-describedby`)、エラー要約(件数つき・項目へのリンク) | DS 4.6 |
| `AppSnackbar.vue`・`useSnackbar.ts` | アプリで 1 つの `VSnackbar`(同時に 1 つ、新しい通知で置き換え)と、呼び出しの composable(モジュール内の `ref`。永続化なし) | DS 4.7。E 4.2・8章 |
| `TopProgress.vue` | カード上端の進行バー(再取得中) | DS 4.5 |
| `IdText.vue`・`TimeText.vue` | 識別子(等幅・折り返し可)、日時(`<time>`。ブラウザのローカル時刻) | DS 4.9 |
| `shared/api/apiError.ts` | `ApiError`(E 5.3 の概形。`kind` は `api`・`network`・`timeout`・`invalid_response`)、`isApiError`(型ガード)、A 5.2 のエラー本文(`{ error: { code, message, retryable, details? } }`)を読む `readErrorBody`(本文が JSON でこの形かを判定する)。**`invalid_response` は `status`(HTTP ステータス)を持つ**(Nginx 由来の 502・503・504・413 を診断で区別し、書き込みの結果不明を判定するため。FARC-P-43)。生成型・`fetch` に依存しない純粋な定義で、Search View も使える。**正規化(投げられた値 → `ApiError`)は `admin/api/errors/toApiError.ts`**(3.3) | E 5.3。A 5.2。FMOD-P-34 |
| `shared/lib/datetime.ts` | `YYYY-MM-DD HH:mm`(秒が要る箇所だけ `:ss`)で `Intl.DateTimeFormat` により整形(ブラウザのローカル時刻。日時ライブラリを足さない) | DS 4.9。E 5.9(FARC-P-24) |
| `shared/lib/number.ts` | 3 桁区切り・「—」の扱い | DS 4.9 |

### 3.3 `admin/api`(生成コード・クライアントの設定・エラー・パス値。FMOD-P-3・FMOD-P-4・FMOD-P-6・FMOD-P-34)

| ファイル | 内容 |
| --- | --- |
| `generated/` | Hey API の出力(型・SDK 関数・Query 用の `{fn}Options`・`{fn}QueryKey`・`{fn}Mutation`)。**`admin/api` の外から import しない**(R2)。置き場は 1 か所に固定し、再生成の差分をレビューする(FARC-P-6)。設定は下の「生成設定」 |
| `client.ts` | **`configureApiClient()`**(E 5.3): 生成クライアント(`client.gen.ts` の `client`)を **1 つだけ**使い、`client.setConfig` に**タイムアウト付き fetch**(下)を渡し、`client.interceptors.request.use`(パス値の検証)と `client.interceptors.error.use`(`toApiError`)を登録する。**`baseUrl` は設定しない**(生成物が spec の `servers[0].url` から `/api/admin/v1` を持つ。E 5.2。同一オリジンで認証情報・CORS の設定も要らない)。`main.ts` が 1 回呼ぶ。**冪等にする**(設定済みかをモジュール内の状態で持ち、2 回目以降は何もしない。interceptor が二重に登録されない。承認済みの案(ゲート5。G5-3。2026-11-26))。**単体テストの setup**(`tests/support/setup.ts`)も同じ関数を呼ぶ(Playwright の E2E は実アプリが `main.ts` から呼ぶので、E2E の setup では呼ばない)。自動再送はしない(再試行は Query だけ)。通知は出さない |
| `pathParams.ts` | パス値の検証の純関数 `isValidPathId(value: unknown)`(下の「パス値の送信前検証」)。request interceptor と、画面側の事前のガードが共有する |
| `index.ts` | **公開口**。(1) 生成型のうち使うもの(**スキーマ名の型**。下の「型の名前」)、(2) 生成の `{fn}Options`・`{fn}Mutation`(**そのまま再 export**。Options を包むラッパーは作らない。エラーの正規化は client の interceptor が行う)、(3) `configureApiClient`・`isValidPathId`、(4) `ApiError`・`isApiError`・`describeError` を再 export する。**SDK 関数(`listSources` など)は再 export しない**(Query・mutation 経由だけ。E 5.3)。`queries` と `tests` は `@/admin/api` だけを import する |
| `errors/toApiError.ts` | **error interceptor に登録する正規化関数**: interceptor が受け取った値(`unknown`。応答があれば応答も)→ `ApiError`(下の表)。投げられる値を常に `ApiError` にする(利用者側の中断 `AbortError` だけは除き、そのまま通す) |
| `errors/errorTable.ts` | **エラー変換表**(E 6.3 の表をデータにしたもの): `code`(と `lock_state` などの `details`)→ 表示先(項目別・ダイアログ内アラート・状態ブロック・成功扱い)・variant・再試行の可否・結果不明。Admin 固有 14 種+共通 6 種を網羅する(B 2.3。E 10.1 のテストの正)。**OpenAPI では `code` は string で列挙がない**(確認 2026-11-26。どの code が返るかは各 EP の `{Op}Errors` の説明文にしか出ない)ため、**手書きの表が正本**で、型生成からは作れない。OpenAPI の説明文と突き合わせる契約テストを 7 章に置く |
| `errors/describeError.ts` | `error`(**`unknown`** で受ける)と文脈(読み取り・書き込み・フォーム・ダイアログの種類)から、**`isApiError` で `ApiError` かを確認し、そうでなければ `invalid_response`(`status` なし)として扱い**(生成型の `ErrorResponse` を信用しない二重の備え。E 5.3)、`errorTable` と `kind` の規則を引いて**表示の記述**(`{ target, variant, retryable, outcomeUnknown, fieldErrors, diagnostic }`)を返す純関数。画面は結果を表示するだけで、`error.error.code` を直接読まない。`kind` の規則: 読み取りの `invalid_response`・`network` は「再試行」ボタンを出すエラーブロック(Query の自動再試行とは別。`retryable` の表示)、書き込みの `invalid_response`・`network`・`timeout` は結果不明(下) |

**クライアントの設定の要点**(E 5.3。承認済みの案(ゲート3・4・5)):

- `throwOnError` はクライアントの既定(`false`)のまま。**生成された `queryFn`・`mutationFn` が内部で `throwOnError: true` を渡して失敗を例外にする**(確認 2026-11-26。0005)。SDK 関数を画面・composable から直接呼ばない。
- **EP-12・13・14 は query を付けない**(下の「EP-12・13・14 に query を付けない」)。

**実行時エラーの正規化(FMOD-P-34。FARC-P-44。正規化層を置くことは承認済みの案(ゲート4。2026-11-26)、`interceptors.error` に登録する方式は承認済みの案(ゲート5。2026-11-26)。E 5.3)**:

- **なぜ要るか**(確認 2026-11-26。作業記録 0005): TanStack Query の `error` の**型は `ErrorResponse | null` だが、実行時の値は型と食い違う**。404 などの JSON エラーはパース済みの `ErrorResponse` オブジェクト、**Nginx が返す HTML(502・503・504・413)は `string`**、**通信断は `TypeError`** で、`Error` インスタンスではない値が投げられる。`error` を `ErrorResponse` と信じて `.error.code` を読むと実行時に壊れる。
- **方針**: `client.interceptors.error.use(…)` に **`toApiError` を 1 つ登録**し、**投げられる値を常に `ApiError` にする**(利用者側の中断 `AbortError` を除く。interceptor が返した値がそのまま投げられる。E 5.3 が確認)。さらに、`queries` 以降は `error` を **`unknown` として扱い**、`isApiError(e: unknown)` で確認し、`ApiError` でなければ `invalid_response` として扱う(`describeError` の入口。二重の備え)。公開口の Options・Mutation を包むラッパー(14 EP を `try/catch` で包む案)は、interceptor 1 つで足りるため採らない。**interceptor の引数の形・実機での挙動の確認は E の FARC-U-22(FMOD-U-12)に従う**。

| interceptor が受け取る値(**`TimeoutError`・`AbortError` の 2 行は設計で未確認**(E の FARC-U-22)。ほかの行は E 5.3 が確認(2026-11-26。作業記録 0005)) | 応答 | `ApiError` |
| --- | --- | --- |
| パース済みの JSON オブジェクトで、`readErrorBody` が A 5.2 の形(`error.code` が string)と判定(4xx・5xx) | あり | `kind='api'`(`status`・`code`・`retryable`・`details`・`outcomeUnknown`。`outcomeUnknown` は `details.outcome_unknown` から) |
| JSON だが `error.code` を持たない | あり | `kind='invalid_response'`(`status`) |
| `string`(Nginx の HTML(502・503・504・413 など)。空の本文は `''`) | あり | `kind='invalid_response'`(`status`) |
| `SyntaxError`(2xx で本文が JSON でない。誤配信の HTML など) | あり(200) | `kind='invalid_response'`(`status` 200) |
| `TypeError`(接続できない・切断) | なし | `kind='network'` |
| `TimeoutError`(クライアントのタイムアウト。下) | なし | `kind='timeout'` |
| `AbortError`(利用者側の中断。Query の破棄・キャンセル) | なし | **`ApiError` にせず、そのまま通す**(結果は使われない) |
| request interceptor の例外(パス値の検証の拒否。下) | なし | 合成した `kind='api'`・`status=400`・`code='invalid_request'`・`retryable=false`(`details` なし。読み取りでは E 6.2 の「見つかりません」と同じ扱い。書き込みでは `details` がない `invalid_request` として想定外。E 6.3) |

- **本文が JSON で `error.code` を持つか**で、Admin API(または `api` の共通のエラー)と、Nginx・プロキシの HTML を区別する(FARC-P-44)。上の表の 1 行目(`kind='api'`)と 2・3 行目(`invalid_response`)の分かれ目が、この判定。
- **HTTP ステータス**は、interceptor が応答を受け取れるときだけ取れる(上の「応答」列)。応答がなければ `invalid_response` に `status` を付けない(`ApiError` の概形は E 5.3)。
- **書き込み(EP-03〜08)の結果不明**(FARC-P-43): 書き込みの `invalid_response`(Nginx の 502・504 を含む。`api` が Crawler を呼んだ後かもしれない。`status` を問わず結果不明とする点は承認済みの案(ゲート5。G5-1。2026-11-26))・`network`・`timeout` は**結果不明**で、`describeError` は `outcomeUnknown=true` を返す。再試行を出さず、確認する導線を出す(起動系 EP-05・06・取消 EP-07・解放 EP-08。FARC-P-15)。**保存系(EP-03・04)は再送が安全な例外**を維持し、「もう一度保存」を出してよい。**読み取り**は、`network`・`retryable=true` の 5xx・`invalid_response`(502・503・504)に限り Query が 1 回だけ再試行し(**`timeout` は再試行しない**。E 5.4。3.4)、なお失敗すれば(`timeout` は最初から)エラーブロック。
- Nginx 由来の 413(1 MiB 超)は、`client_max_body_size` を `api` の上限より少し大きくして `api` の JSON の 400 を出させる(E 3.3)ので、通常は `invalid_response` にならない。Nginx の `error_page` で JSON は返さない(承認済みの案(ゲート4)。FARC-P-43)。

**タイムアウト付き fetch(E 5.3。仮値。承認済みの案(ゲート3)。FARC-U-16)**: `configureApiClient()` が `setConfig({ fetch })` に渡す。**読み取り(GET)45 秒・書き込み 90 秒**(メソッドで切り替える。`api` の最悪の待ち時間より先に切らない値。根拠と Nginx との順序は E 5.3)。

- 自前の `AbortController` と `setTimeout` で中断する。呼び出し側の `signal`(Query が破棄したとき)の中断も内側の `AbortController` に伝える。時間切れは `TimeoutError` として投げて `timeout` に正規化し、利用者側の中断は `AbortError` のまま通す(上の表。両者を区別する)。
- **`AbortSignal.any` は使わない**(対応下限の Safari 16.4 で使えない可能性があるため。推測。未確認。E の FARC-U-22)。
- 実機での確認(タイムアウトと Query のキャンセルの区別、`TypeError` の捕捉、`api` 側の最悪の合計との整合)は E の FARC-U-22 に従う(FMOD-U-12)。

**パス値の送信前検証(FMOD-P-4 の拡張。検証することは承認済みの案(ゲート4。2026-11-26)、request interceptor による実装はゲート5。E 5.3)**: **パスに入れる値すべて**(`source_id`・`job_id` に限らない)を **`admin/api` の層で保証**する。

- **理由**: 生成 SDK はパスの値を `encodeURIComponent` で変換する。`a%b?c#d` → `a%25b%3Fc%23d`、`a/b` → `a%2Fb`、日本語は正しくエンコードされる(確認 2026-11-26。作業記録 0005)。ところが **値全体が `.` なら `/jobs/`(一覧の EP)、`..` なら 1 階層上の URL、空文字なら `/jobs/` に化ける**(ブラウザの URL の正規化。`%2e%2e` は二重にエンコードされ回避にならない)。API は `job_id` の `.`・`..` を 404、`source_id` の `.`・`..` を 400 で拒否するが、SDK が URL を壊して**別の EP を叩く**ため、フロントで送信前に弾く。`undefined` はプレースホルダ(`%7Bjob_id%7D`)が残る。
- **規則**: `isValidPathId(value)` は、次の**どれかに当たる値を拒否**する: **文字列でない**、**空**、**値全体が `.` または `..` に等しい**、**制御文字(U+0000〜U+001F・U+007F)を 1 文字でも含む**。**`.` や `..` を一部に含むだけの値(`a.b`・`my.source`・`..a`・`a..`)は拒否しない**(正当な `source_id` がありうる。URL の正規化で化けるのは値全体が `.`・`..` のときだけ。導出)。それ以外(`%`・`?`・`#`・`/`・空白・日本語)は SDK のエンコードに任せ、API の判断(400・404)を E 6.2 の「見つかりません」で扱う(`source_id` は `[A-Za-z0-9._-]` で先頭は英数字なので、値全体が `.`・`..` なら API でも 400)。
- **二重の保証**: (1) **画面側**: `queries` の composable と `features` のページの composable は、route の `:sourceId`・`:jobId` などを `isValidPathId` で事前に判定し、不正なら**取得せず**(`enabled: false`)、`useViewState` に「見つかりません」(`notfound`)を渡す(FMOD-U-9 の案を引き継ぐ)。(2) **最終防衛**: `configureApiClient()` が登録する **request interceptor が `opts.path` のすべての値を検証**し、不正なら**送信せずに**専用の例外を投げる。この例外は error interceptor を通り、`toApiError` が上の表の**合成した `invalid_request`(400)**にする。mutation の対象 ID(API の応答から取る値を含む)もここを通る。request interceptor に渡る `opts.path` は元の値(`.` など)のまま(E 5.3 が確認)。
- `/` を含む ID は Admin API が 404 `not_found` を返す(B 2.12)ので、E 6.2 のとおり「見つかりません」の扱い。
- **`encodeURIComponent` で変換されない `!`・`'`・`(`・`)`・`*`**: URL のパスで有効な文字なので補わない(推測。Nginx 越しの保持は実機確認していない。`%2F`・`%2E` を含む実リクエストでの保持の実測と合わせて前提タスク B で確認する。E 12.4)。
- 契約テスト(7章): `job_id='a%b?c#d'` などを渡した**実際のリクエスト URL**(生成 SDK を通す)と、値全体が `.`・`..`・空・制御文字を含む値・文字列でない値が、**送信されずに合成の `invalid_request` になる**こと、`a.b`・`..a`・`a..` は**拒否されずそのまま送られる**ことを検証する。

**型の名前(承認済みの案(ゲート4))**: 生成物は、スキーマ名の型(`CancelJobResponse`・`ReleaseLockResponse`・`SourceSettings` など)と、EP 側の型(`{Op}Data`・`{Op}Responses`・`{Op}Errors`・`{Op}Response`)を出す。**スキーマ `CancelJobResponse`・`ReleaseLockResponse` と EP 側の `{Op}Response` が衝突し、EP 側が `CancelJobResponse2`・`ReleaseLockResponse2` という名前になる**(確認 2026-11-26)。そのため、**公開口は `{Op}Response2` を再 export せず、応答・本文の型は常にスキーマ名の型**(`SourceListResponse`・`JobDetailResponse`・`RegisterSourceBody`・`StartCrawlBody` など)を使う。`{Op}Data`・`{Op}Responses`・`{Op}Errors` は `admin/api` の中でだけ使う。

**生成設定(FARC-P-45。承認済みの案(ゲート4))**:

- `openapi-ts.config.ts`: 入力は `openapi/admin-v1.json`、出力は `src/admin/api/generated`、プラグインは `@hey-api/client-fetch`・`@hey-api/typescript`・`@hey-api/sdk`・`@tanstack/vue-query`。**`@tanstack/vue-query` は `infiniteQueryOptions: false`**(`page` を持つ EP-09・11 に `*InfiniteOptions` が自動生成され、中に `@ts-ignore`・`as any` を含むため。MVP は通常のページ送りで使わない)。
- 書き出しは `uv run python -m loreley_api.admin.openapi_export <出力>`(`openapi_export.py` の docstring の修正は前提タスク A)。OpenAPI JSON と生成コードを**コミットし**、CI が再生成して**差分がないこと**を検査する(FARC-P-6。生成が決定的なので成り立つ。E 11.2)。生成コードは lint・format の対象外(生成物は 4 スペース・クォート混在)。
- **生成クライアントの `servers` と `baseUrl`**: OpenAPI の `servers` は `[{url: '/api/admin/v1'}]` 固定で `paths` は相対。Hey API は `servers` から `baseUrl` を作り、`client.gen.ts` に入れる(確認 2026-11-26)。**手書きのコードは `baseUrl` を設定しない**(`servers` が変われば再生成で追従する。E 5.3)。単体テストで `client.getConfig().baseUrl` が `/api/admin/v1` であることを確認する(7.2。導出。setup で絶対 `baseUrl` に上書きするときは、上書き前の値で別に確認する。E 10.1)。
- Node 単体では相対の `baseUrl` で `new Request()` が失敗し、`{error: TypeError}` が黙って返る(確認 2026-11-26)。**jsdom 環境で解決するかは未確認**(E の FARC-U-9。7.1)。解決しなければ、**テストの setup で `client.setConfig({ baseUrl: <絶対 URL> })` を呼ぶ**(`client.ts` にテスト用の形は持たせない)。

**EP-12・13・14 に query を付けない(承認済みの案(ゲート4))**: EP-12(`getCluster`)・EP-13(`getDashboard`)・EP-14(`getMeta`)は query を一切受けず、**未知のクエリは 400 `unknown_field`**(B 8.1・8.2 は「エラーなし」とするが、実装は 400。確認 2026-11-26)。`getClusterOptions()`・`getDashboardOptions()`・`getMetaOptions()` は**引数なしで呼び**、cache-busting 用の `_=` なども足さない。URL にクエリが付かないことをテストで確認する(7.2)。

**生成コードの依存ルール上の扱い(6章への前提)**: 生成型・生成クライアント(`client`)を直接 import してよい層は `admin/api` だけ(`client.ts`・`index.ts` など `admin/api` の中の手書きのコード)。生成ディレクトリは lint の対象外なので、中の `fetch`・`@tanstack/vue-query` の import は R3・R4 の検査に掛からない(生成コードの実装。手書きのコードには適用する)。

### 3.4 `admin/queries`(FMOD-P-5。FARC-P-8・11・27 の置き場)

読み取りも書き込みも、**サーバーとのやりとりはすべてここ**に置く(画面・ダイアログは `queries` の composable だけを呼ぶ)。`queries` が使う `{fn}Options`・`{fn}Mutation` は、`@/admin/api`(公開口)が再 export する生成のもの。失敗は client の error interceptor が `ApiError` にして投げる(3.3)ので、`queries` に正規化の処理は要らない。

| ファイル | 内容 | EP(生成 SDK) |
| --- | --- | --- |
| `queryClient.ts` | `QueryClient` の既定値(E 5.4。`retry` 1(`network`・`retryable=true` の 5xx・**読み取りの `invalid_response`**(Nginx 由来の 502・503・504。FARC-P-43)に限る。`timeout` は再試行しない。判定は `error` を `unknown` として `isApiError` で確認して行う)・`retryDelay` 1 秒・`staleTime` 0・フォーカス・再接続での再取得なし・**マウント時は再取得**・mutation の再試行なし・グローバル通知なし) | — |
| `keys.ts` | **key factory**(E 5.4 の表。`['meta']`・`['dashboard']`・`['sources','list']`・`['sources','detail',sourceId]`・`['sources','edit',sourceId]`・`['jobs','list',params]`・`['jobs','detail',jobId]`・`['documents',sourceId,params]`・`['opensearch','cluster']`)。生成の `{fn}QueryKey` は使わず、`withKey` で生成 Options の key を上書きする(Hey API 0.x の key の形の変更に引きずられない) | — |
| `withKey.ts` | **`withKey(options, key)`**: 生成 Options の key を差し替えて返す 1 つのヘルパー。`{ ...{fn}Options(…), queryKey: keys.… }` をそのまま `useQuery` に渡すと**型検査が通らない**(TS2769。`staleTime` などの型が、生成された key の型に結びつくため。確認 2026-11-26。E 5.4)ので、**key の型を合わせるキャストをここ 1 か所に閉じ込める**(承認済みの案(ゲート5。2026-11-26)。E 5.4)。実行時は、生成された `queryFn` が `{fn}Options` の引数(クロージャ)から URL を作り、key から作らないので、key を差し替えても正しい URL へ送られる(E 5.4)。`@tanstack/vue-query` の型を import してよい(R4) | — |
| `polling.ts` | `refetchInterval`: D1 の 30 秒(スイッチ連動)・J2 の関数(`queued`・`running` のときだけ 10 秒。E 5.5) | — |
| `placeholder.ts` | `placeholderData` の関数(**同じスコープの**ページ・並べ替えの変更だけ前回データを保持。E 5.6) | — |
| `invalidation.ts` | **invalidate の表**(E 5.8)。操作 → prefix の配列を 1 か所に持ち、mutation が呼ぶ | — |
| `meta.ts` | `useMetaQuery`(`staleTime: Infinity`。FARC-P-25)、`useDashboardsUrl`・`useCronTimezone`(失敗は `null` と同じ) | EP-14(`getMeta`) |
| `dashboard.ts` | `useDashboardQuery(autoRefresh)` | EP-13(`getDashboard`) |
| `sources.ts` | `useSourcesListQuery`・`useSourceDetailQuery(id)`・`useSourceEditQuery(id)`(`gcTime: 0`・`staleTime: Infinity`。E 5.8。FARC-P-12) | EP-01(`listSources`)・EP-02(`getSource`。詳細と編集は同じ EP で key が別) |
| `jobs.ts` | `useJobsListQuery(params)`・`useJobDetailQuery(id)`(ポーリング) | EP-09(`listJobs`)・EP-10(`getJob`) |
| `documents.ts` | `useDocumentsQuery(source, params)`(`source` 未選択は `enabled: false`) | EP-11(`listDocuments`) |
| `opensearch.ts` | `useOpenSearchClusterQuery` | EP-12(`getCluster`) |
| `mutations/createSource.ts`・`updateSource.ts` | S3・S4 の保存 | EP-03(`registerSourceMutation`)・EP-04(`updateSourceMutation`) |
| `mutations/startCrawl.ts` | クロールの起動(DLG-1 と DLG-4 の再実行が**共有**) | EP-06(`startCrawlMutation`) |
| `mutations/deleteSource.ts` | ソース削除ジョブの起動(DLG-2 と削除の再実行が共有) | EP-05(`startSourceDeleteMutation`) |
| `mutations/cancelJob.ts`・`releaseLock.ts` | 取消・ロック解放 | EP-07(`cancelJobMutation`)・EP-08(`releaseLockMutation`) |

- 各 composable は `computed(() => withKey({fn}Options({ … }), keys.…))`(E 5.9)で生成された `{fn}Options` を包み、key を key factory で上書きする。引数は**型付きの条件**(URL から導いた `params`。3.5)。
- **EP-12・13・14 の composable は `getClusterOptions()`・`getDashboardOptions()`・`getMetaOptions()` を引数なしで呼ぶ**(query を渡さない。3.3)。`/meta` もクエリなし。
- ID を引数に取る composable(`useSourceDetailQuery`・`useSourceEditQuery`・`useJobDetailQuery`・`useDocumentsQuery`)は、`isValidPathId` が偽なら `enabled: false`(3.3)。
- `queries` は `vue-router`・UI・`admin/components` を import しない(URL を直接読まない。条件は引数で受ける)。
- mutation は「実行 → 成功時に `invalidation.ts` の表で invalidate」までを担い、**成功後の遷移・スナックバー・ダイアログの開閉は呼び出し側**(`dialogs`・`features`)が決める。
- Query の `error` は `unknown` として扱い、`isApiError` で確認してから使う(FARC-P-44。E 5.3)。生成型の `ErrorResponse` を信用して `error.error.code` を直接読まない。`queries` が `ApiError` に読み替えて持つことはしない(通常は error interceptor が既に `ApiError` にして投げている。`ApiError` でなければ `describeError` が `invalid_response` として扱う。3.3)。

### 3.5 定義表・共通ロジックの置き場(E 12.6 の引き継ぎ 5。FMOD-P-12・FMOD-P-13)

「対応を 1 つの表(データ)に持ち、画面で分岐を散らさない」(E 1.2)ための置き場を決める。

| 定義表・ロジック | 置き場 | 内容・規則 |
| --- | --- | --- |
| route 定義(`meta`) | `admin/router/routes.ts` | admin-view 4.2 の表をそのまま。`name` は `admin/lib/routeNames.ts` の定数 |
| `navGroups` | `admin/router/navGroups.ts` | DS 5.3 の定義表(`overview`・`operate`・`inspect`)。新しいグループは 1 行足す |
| route 名の定数 | `admin/lib/routeNames.ts` | features が `routes.ts` を import せずに遷移できるようにする(循環を避ける。R8) |
| 外部リンクの定義表 | `admin/shell/externalLinks.ts` | route を持たない外部リンク項目(MVP は OpenSearch Dashboards 1 件。`id`・表示名・アイコン・URL の取得元(`/meta` の `dashboards_url`)・`featureFlag`)。`SideNav` の外部リンク領域が描き、**`featureFlag` の評価はここだけ**(E 4.2・4.5。I-89。FMOD-P-29) |
| ロック状態の写像 | `admin/lib/lockStateView.ts` | `lock.state` 7 値+取得失敗 → S2 のロック状態カードの 6 種+取得失敗(E 5.10。FARC-P-34)。S2 の `LockStateCard`・J2 の `LockCard`・DLG-1 の拒否表示が共有する(features どうしを import しないため `lib`。FMOD-P-30) |
| `existing_job` の判定 | `admin/lib/existingJob.ts` | 409 `lock_held`・`lock_in_use` の `details.existing_job` から「ジョブを表示」(J2)へ導けるかの判定 `canLinkToJob`: **`status`・`job_type` が `null`、または既知の値でない(未知の文字列)ときは導かない**(EP-10 が 404 になりうる。FARC-P-35。承認済みの案(ゲート4。2026-11-26)で「または未知の値」を追加)。OpenAPI の型は列挙だが、実装は Crawler の文字列をそのまま通すため未知値がありうる(確認 2026-11-26)。既知の値の一覧は生成型の `JobStatus`・`JobType` から `satisfies` で型検査して持つ。DLG-1・DLG-4・DLG-5 が共有(`lib`) |
| `RouteMeta` の型 | `admin/router/meta.d.ts` | E 4.3 の概形(`title` は `string \| (route) => string`。I-83) |
| `dashboardComponents` | `features/dashboard/dashboardComponents.ts` | D1 の 8 コンポーネント(`id`・役割・必須/任意・導線。dashboard 3.2)。タイルはこの表から描く |
| `documentTabs` | `features/documents/documentTabs.ts` | 4 タブ。**URL の `id`(kebab)↔ API の `tab`(snake)**(I-85)・ラベル・列定義・並べ替え可能な列・既定の並び・注記・空状態の文・件数の取得(documents 5章)。**各定義が行の型とアダプタ(型ガード)を持つ**(下の「`documentTabs` の行型」) |
| URL ↔ API の対応(一覧の条件) | `features/{jobs,documents,opensearch}/*Params.ts` | 画面ごとの条件の定義(URL のキー・API のキー・既定値・正規化・`push`/`replace`)を、`composables/useListParams` に渡す。E 5.6 の対応表の実体。`jobsParams.ts` は `sort` を union(`'queued_at' \| '-queued_at'`。OpenAPI では素の string のため FE が型を持つ)、`status` を `JobStatus` と複合値 `active` の union で持つ |
| フォーム `field` 対応 | `features/sources/form/fieldMap.ts` | API の `details.errors[].field`(`ttl_days`・`ttl_seconds`・`ratio_threshold_percent`・`min_delete_count`・`schedule_cron`・`source_id`・`connector_config.root`・`connector_config.include_patterns[i]` …)→ 入力欄・行。**`ttl_days`・`ttl_seconds` の排他・必須の違反は `field` が両方とも `ttl_days` 固定**なので TTL 欄(モードによらず)に写す。**添字なしの配列エラー**(`connector_config.include_patterns`・`exclude_patterns` の 100 件超)は該当の一覧の下、**`connector_config` 自身のエラーは上部アラート**。表にない `field` も上部アラート(E 6.4) |
| `unavailable` を引く関数 | `admin/lib/unavailable.ts` | 下の「`unavailable` の参照」 |
| 値があるはずの項目の表 | `admin/lib/expectedFields.ts` | 下の「`unavailable` の参照」の `expected` |
| OpenSearch の状態値 | `admin/lib/clusterValues.ts` | `cluster.status`・`indices[].status`・`shards[].role`・`shards[].state` は OpenAPI で素の string(列挙なし。確認 2026-11-26)。FE が union とガード(`toClusterStatus` など)を**ここ 1 か所**に定義し、**未知の値は中立表示**(`StatusTag` の未登録の扱い。`indexFilter` では未知の状態値は除外)。値の一覧は B 7.1・opensearch 画面仕様に従う |
| 番兵の日時・期限 | `admin/lib/leaseExpiry.ts` | 下の「番兵の日時」 |
| 失敗理由・警告・削除結果のコードの日本語表記 | `features/jobs/catalogs/`(`failureReasons.ts`・`warningCatalog.ts`・`deletionStatus.ts`) | jobs 2.5・2.7・2.9 の表。**未知のコードは一般的な文言**(B 5.2)。**`warnings[]` の要素は OpenAPI で `{[k: string]: unknown}`**(`code` が型に出ない)ため、`warningCatalog.ts` に型ガード(`typeof code === 'string'`)を持ち、満たさない要素は一般的な文言にする(承認済みの案(ゲート5。2026-11-26)) |
| 画面の検証規則 | `admin/lib/validation/`(`rules.ts`・`patterns.ts`) | 項目 → 規則の表と純関数(E 7.1)。パターンの最大 100 件・1,024 バイトは仮値として 1 か所の定数(`limits.ts`) |
| 単位変換・丸め | `admin/lib/units.ts` | 日 ↔ 秒の表示、しきい値の桁判定と丸め(E 7.3・7.7)。**小数桁の判定に `String(n)` を使わない**(極小値は指数表記になり桁数を誤る)。**`Number(n.toFixed(2)) !== n` なら小数第 3 位以下を持つ**とする(E 7.7。承認済みの案(ゲート5。2026-11-26))。**丸めに `toFixed(2)` をそのまま使わない**(2 進の誤差で `(2.675).toFixed(2)` は `'2.67'`、`(1.005).toFixed(2)` は `'1.00'` になる)ので、丸めは十進で行い、境界値(`2.675`・`1.005` など)を単体テストで確認する |
| 操作の出し分けの型 | `admin/lib/actions.ts` | `ActionSpec`(`id`・`label`・`visible`・`disabledReason`・`level`)。`PageActions` が描き、画面ごとの表(`sourceActions.ts`・`jobActions.ts`)が返す(DS 4.13) |

**`documentTabs` の行型(承認済みの案(ゲート4。2026-11-26)。X1)**: EP-11 の `items` は、判別子(`type` などの共通の識別キー)を持たない **4 つの型の `anyOf`**(`SkippedDocument`・`ExtractFailedDocument`・`OversizeDocument`・`SummaryPendingDocument`)で、生成型は 4 型の union になる(確認 2026-11-26)。そのため:

- `documentTabs` の各定義は、**そのタブの行の型**と**アダプタ**(応答の `items` をその行型の配列にする型ガード)を持つ。アダプタは、応答の `tab` が自分のタブであることと、各行が**他の 3 型にないキー**を持つことで判定する(`skipped` は `existence`、`extract_failed` は `last_seen_at`、`oversize` は `detected_by`、`summary_pending` は `indexed_at`。実 OpenAPI のスキーマで確認 2026-11-26)。判定に合わない行・タブは想定外の応答(診断つきのエラーブロック)として扱う(導出)。
- `DocumentsTable` は**タブごとの行型**を受ける(行型を総称にした部品。列定義 `columns` も行型ごと。型の付け方は実装時)。ページ(`DocumentsPage`)が `tab` で定義を選び、`rows`・`columns` を渡す。タブの追加(AF-29)は、定義(行型・アダプタ・列)を足すだけで済む。
- 行ごとの `unavailable`・`expectedFields` も行型ごとに引く(下の `expected`)。

**`unavailable` の参照(`admin/lib/unavailable.ts`。FMOD-P-14・FMOD-P-33)**:

- **行の `unavailable`(一覧の EP。EP-01・09・11。FMOD-P-33)**: `rowUnavailableReason(row, path)` は、各 `items[i]` の `unavailable`(常に存在)を**行内の相対パス**(EP-01: `last_crawl`・`last_crawl.stalled`・`last_completed_at`・`delete_job`・`delete_job.stalled`・`document_count`、EP-09: `stalled`、EP-11: `existence`)で引き、理由コードまたは `undefined` を返す。**取得できなかったか否かは、その行の `unavailable` のキーだけで判定する**(他の行の失敗に影響されない)。
- **最上位の `unavailable`**: `topUnavailableReason(response, path)` は、最上位の `unavailable` を応答の項目の**正式なパス**で引く。**対象の EP は EP-02・EP-10・EP-11 だけ**(承認済みの案(ゲート4。2026-11-26)。v0.1 は EP-12・13・14 も対象としていたが、実装・OpenAPI では `ClusterResponse`・`DashboardResponse`・`MetaResponse` に `unavailable` が**ない**。確認 2026-11-26): EP-02 は `index.document_count`・`lock`・`last_crawl.stalled` など、EP-10 は `stalled`・`lease_expires_at`・`latest_for_source`・`rerunnable`・`deletion.current` など、EP-11 は**行に属さない項目だけ**(`tab_counts.<タブ>`・`document_count`)。EP-01・09 の最上位は常に `{}` で引かない。
- **`unavailable` を持たない EP(EP-12・13・14)**: D1(EP-13)は `unavailable` を引かない(取得できないコンポーネントは `components[].state=undetermined` と `reason` で表す)。O1(EP-12)も引かない(部分失敗はなく、どれかの読み取りが失敗すれば全体が 503。B 7.1)。値の `null`(`indices[].status`・`document_count` など)は「—」で表示し、`cellState` は使わない。シェルの EP-14 も同様(失敗は `dashboards_url=null`・`cron_timezone=null` と同じ扱い)。
- 旧規則の `isRowUnavailable`(一覧でキーがあり行が `null` なら取得できません)は**廃止**した(行ごとに失敗を区別できるため。AAPI-P-42)。
- `cellState(unavailable, path, value, { expected })`: セルの表示状態を返す(E 5.9 の (a)・(b)。FMOD-P-31)。`unavailable` は**引く対象の 1 つの `unavailable` オブジェクト**で、呼び出しは薄い 2 つのラッパー `rowCell(row, path, value, opts)`(行の `unavailable`)と `topCell(response, path, value, opts)`(最上位)を通す。`value` があれば `value`。`null` でその `unavailable` にキーがあれば `unavailable`(「—」+「取得できません」)。キーがなく `null` のとき、`expected=true`(値があるはずの項目)なら `unreadable`(「—」+視覚的に隠した「読み取れません」)、`expected=false`(`started_at`・未実行の `last_crawl` など)なら `none`(「—」+「なし」。`last_crawl` は「未実行」)。`unavailable` の見える文言の有無は画面仕様に従う(表のセルは視覚的に隠した「取得できません」、S2 のカードは見える文言。E 5.9)。
- **`expected` の項目の表(`admin/lib/expectedFields.ts`。FMOD-P-31)**は、**EP・応答の型・行の型(EP-11 は `tab`)ごと**に持つ(承認済みの案(ゲート4。2026-11-26)): `JobBrief`(`status`・`job_type`・`trigger`・`queued_at`)、`registration`(件数・`partial`・`phase`)、**EP-01 の行(`status`。`status=null` は読めない値として扱う)**、**EP-02 の設定項目(`connector_type`・`status`・`updated_at` など。null 許容)**、**EP-11 の 4 つの行型**(下)。EP-11 の行は、B が null と書く項目以外も null になりうる: 実 OpenAPI では `SkippedDocument` の `existence`、`ExtractFailedDocument`・`SummaryPendingDocument` の `document_id` が非 null で、それ以外は null 許容(確認 2026-11-26)。**行型ごとのどの項目を「値があるはず」とするかは B 6 章の項目表と documents 6 章の列から導いて実装時に確定する**(FMOD-U-13)。
- 画面は `unavailable` を直接読まず、これらの関数だけを使う(行の関数と最上位の関数を取り違えないよう、一覧の行には `rowCell`、単一の応答・EP-11 の最上位には `topCell` を使う)。理由コードは画面では区別しない(E 6.2。`malformed` だけ S4 で扱いが違う)。パスの文字列は定数にまとめ、B の変更に追従する場所を 1 か所にする。

**番兵の日時・期限(`admin/lib/leaseExpiry.ts`。FMOD-P-15)**:

- 409 の `details.existing_job.lease_expires_at` は、Crawler が日時として読めないときだけ `0001-01-01T00:00:00.000Z` を返す(B 2.11・I-73)。`formatLeaseExpiry(value, { expired })` が番兵を判定し、**「期限切れ」の値**を返す(日時として整形しない)。
- **`stalled=true`(リース切れ)かつ `lease_expires_at=null`** のときは「**期限を確認できません(期限切れ)**」を返す(`expired: true` を渡す。承認済みの案(ゲート4。2026-11-26))。EP-10 の `lease_expires_at` は、ロック文書がない・ロックが別のジョブのもの・期限が読めないときも `null` になりうる(`stalled=true` の経路は実機で未検証=推測を含む。AAPI-U-9)。`expired: false` の `null` は「期限なし(実行待ち)」で別。`expired` は、J2 では `stalled=true`、S2 のロック状態カードでは `lock.state=lease_expired`(E 5.10)から呼び出し側が渡す。
- `lease_expires_at` を表示する箇所(DLG-1 の `lock_held`・DLG-5 の `lock_in_use`・S2 のロック状態カード・J2 の概要)は、すべて `formatLeaseExpiry` を通す。一般の日時整形は `shared/lib/datetime.ts`。S2 の `lock.job.lease_expires_at` は読めなければ `null` で、番兵は出ない(B 3.2。EP-02・10 の `lease_expires_at` も同じ)。

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

| ダイアログ | 場所 | 開く画面(admin-view 4.1) | mutation(`queries/mutations`。生成の名前) | 水準(admin-view 6章) | `data-testid` |
| --- | --- | --- | --- | --- | --- |
| DLG-1 クロール起動 | `dialogs/crawl-start/` | S1・S2 | `startCrawl`(EP-06。`startCrawlMutation`) | 要確認(標準/警告つき) | `dlg-crawl-start` |
| DLG-2 データソース削除 | `dialogs/source-delete/SourceDeleteDialog.vue` | S1・S2 | `deleteSource`(EP-05。`startSourceDeleteMutation`) | 要入力確認 | `dlg-source-delete` |
| 削除の再実行 | `dialogs/source-delete/SourceDeleteRerunDialog.vue` | S1・S2・J2 | `deleteSource`(EP-05) | 要確認・標準 | `dlg-source-delete-rerun` |
| DLG-3 取消 | `dialogs/job-cancel/` | J1・J2 | `cancelJob`(EP-07。`cancelJobMutation`) | 要確認・標準 | `dlg-job-cancel` |
| DLG-4 再実行 | `dialogs/job-rerun/` | J2 | `startCrawl`(EP-06。J2 の `source_id`・`force_delete`・`rewrite_mode` を渡す。下の null の扱い) | 指定による | `dlg-job-rerun` |
| DLG-5 ロック解放 | `dialogs/lock-release/`(S2 の孤児ロック版と J2 のリース切れ版を `variant` で切替) | S2・J2 | `releaseLock`(EP-08。`releaseLockMutation`) | 要確認・警告つき | `dlg-lock-release` |

- 共通の状態機械は `dialogs/useOperationDialog.ts`: 開閉・実行中(二重送信防止・入力の無効化)・失敗(`describeError` の結果を**ダイアログ内アラート**に。消えない)・成功(閉じる+`useSnackbar`+呼び出し側の `onSuccess`)。E 7.4・6.3 の流れの実装。
- 拒否・失敗の組み立て(`lock_held` の variant・既存ジョブ・「指定は反映されていない」・`lock_state` による warning/error、結果不明)は `dialogs/crawl-start/refusal.ts` など、ダイアログごとの純関数にする(admin-view 7.7。E 6.3・FARC-P-35)。ロック状態の写像は `admin/lib/lockStateView.ts` を共有する。**`existing_job` の `status`(または `job_type`)が `null` または未知の値のとき「ジョブを表示」を出さず、S2 のロック状態カードへ導く**(`admin/lib/existingJob.ts` の `canLinkToJob`。I-88。E 6.3)。
- **DLG-4 の `force_delete`・`rewrite_mode` が null のとき(FARC-P-46。承認済みの案(ゲート4。2026-11-26))**: J2 の応答(EP-10)の `force_delete`・`rewrite_mode` は `boolean | null` だが、EP-06 の本文は null を受けず(400 `invalid_request`。`StartCrawlBody` は非 null の真偽値)、破壊的な指定(`force_delete=true`)を推測で付けてはならない。そこで **null は「指定なし(false)」として送り**、DLG-4 には**読み取り専用で「記録なし(なしとして実行)」と表示**する。値があるときは従来どおり、J2 の値を読み取り専用で提示してそのまま渡す(`requested` と同じ値が `options_applied` で返る)。
- **DLG-5 の `released=false`(J-E6。承認済みの案(ゲート4。2026-11-26))**: EP-08 は、ロック文書がない `stalled` のジョブでは 200 で `released=false`・`failed_job_id=null` を返し、ジョブは `running` のまま残る(実機未検証=推測を含む)。`released=false` のときは**成功のスナックバーを出さない**。**ダイアログは閉じず**、内側に **info アラート**「解放するロックがありませんでした」を出して実行ボタンを「閉じる」に置き換え、状態を確認できるよう `['sources']`・`['jobs']` を invalidate する(E 6.3。表示は導出で、文言は画面仕様に委ねて HO)。再送で `released=false` になりうる(B 9.2.3)ことと同じ扱い。
- ダイアログは**対象と成功時の動作を props・イベントで受ける**(遷移は呼び出し側。DLG-4 の成功は新しいジョブの J2 へ。#32)。
- 書き込みの結果不明(`invalid_response`・`network`・`timeout`・`crawler_response_lost`)は、`describeError` の `outcomeUnknown` で、再試行を出さず確認の導線(J1・S2・J2)を出す(3.3。FARC-P-43)。

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

- D1 は EP-14 を直接使わない(Dashboards のリンクはシェル。I-104 は解消済み)。
- **D1 は `unavailable` を引かない**(EP-13 の応答に `unavailable` がない。3.5)。取得できないコンポーネントは `components[].state=undetermined` で表す。
- `web` タイルの判定は API が行い(前提タスク B+C の完了後は `web` への HTTP 確認)、FE は `state`・`reason` を表示するだけで変更がない。

#### S1〜S4 `features/sources/`

| 要素 | 内容 |
| --- | --- |
| `pages/SourcesListPage.vue`(S1) | `ListPage`+`SourcesTable`。主操作「データソースを登録」。行の操作から `dialogs`(DLG-1・DLG-2・削除の再実行)を開く |
| `pages/SourceDetailPage.vue`(S2) | `DetailPage`+4 つのカード(`SourceSettingsCard`・`LockStateCard`(`lockStateView` の写像。E 5.10)・`LastJobCard`・`IndexCard`)。操作は `sourceActions.ts` の表。**`status=null`(EP-02 も null 許容)のときは S1 と同じく「削除中」の判定も操作も出さない**(E 5.7。承認済みの案(ゲート5。2026-11-26)) |
| `pages/SourceCreatePage.vue`(S3)・`SourceEditPage.vue`(S4) | `FormPage`+`SourceForm`(**共有**)。S4 は現在値を取得できなければフォームを出さない |
| `components/` | `SourcesTable.vue`(S1。クライアント側のページ・並べ替え。`AdminDataTable`)・`SourceRowActions.vue`・`SourceSettingsCard.vue`・`LockStateCard.vue`・`LastJobCard.vue`・`IndexCard.vue`・`SourceForm.vue`・`SourceFormAlerts.vue`(読めない項目・丸め・削除中・上部アラート) |
| `composables/` | `useSourcesListPage`(EP-01・EP-14。表の行モデル)、`useSourceDetailPage`(EP-02・EP-14)、`useSourceForm`(下) |
| `models/sourceRow.ts` | 一覧の行の表示用変換(`last_crawl` と `delete_job` からタグ・補足文。行の `unavailable` を `rowCell` で引く。source-a の未実行と source-b の読み取り失敗を区別する)。**`status=null`(保存値が読めない。EP-01 の `status`・`connector_type` は null 許容。確認 2026-11-26)の行は「削除中」と判定せず**、状態は「—」+視覚的に隠した「読み取れません」にする(FARC-P-36)。**`last_completed_at`・`connector_type` は S1 では使わない**(使う画面仕様がない。要件にない追加をしない。B 1.4 が S1 の項目とする点は AF-U-9 が未決。承認済みの案(ゲート5。2026-11-26)) |
| `sourceActions.ts` | 状態 → 操作の表(DS 4.13・sources 1.8): 削除中は起動・編集・削除を出さない、削除ジョブが失敗なら「削除を再実行」、ロック状態に応じた「ロックを解放…」の入口。**`status=null` の行(S2 も同じ)は、「削除中」の判定も、操作(クロール起動・編集・削除など)も出さない**(状態が読めないため。ジョブ記録の `status=null` と同じ扱い。承認済みの案(ゲート4。2026-11-26)。EP-02 の `status` も null 許容なので S2 も S1 と同じ扱いにする(E 5.7。S2 の扱いは承認済みの案(ゲート5。2026-11-26))。詳細への遷移は操作ではないので残す(導出)) |
| `form/` | S3・S4 のフォーム(下) |

- **EP-05(削除)を受け付けた直後の S1 の行は、「削除中」にならないことがある**(承認済みの案(ゲート4。2026-11-26)。**v0.1 の「202 直後に S1 の行が『削除中』になる」は誤り**。確認 2026-11-26): 受付直後は設定の `status` が `active` のままで、`deleting` は削除ジョブの開始後。直後の S1 は `delete_job=null`・`status=active` のままで、これは正常。S2 のロック状態カード(EP-02 の `lock.state`)は即時に `held_delete` になる。画面は「行が変わる」ことを前提にせず、スナックバー(`job_id`)と invalidate による再取得で足りる(4.2)。
- **登録直後の EP-01 には新規ソースが見えないことがある**(EP-01 は検索ベースで反映が遅れうる。EP-02 は ID 指定で即時。最大遅延は未測定。S-E5。この注記は承認済みの案(ゲート5。2026-11-26))。S3 の成功は S2 へ移動する(E 5.8)ので影響は小さいが、S1 に戻ったときに無いことがあるのは想定内。実装時に確認する。

**`features/sources/form/`(S3・S4 共有。FMOD-P-16)**:

| ファイル | 内容 |
| --- | --- |
| `connectors/fileSystem.ts` | `file_system` の取得設定 5 項目の**項目定義の表**(項目名・型・必須・既定・部品・ラベル・説明文・検証・`data-testid`。sources 2.3.1 と同じ形)。Connector の種別を足すときは、種別ごとにこの形のファイルを足す(admin-view 8.3.1) |
| `sourceFormModel.ts` | フォームの値の型(`connector_config` の 5 項目・TTL のモード(日・秒)と値・しきい値・最小件数・`schedule_cron`・S3 では `source_id`・`connector_type`)と初期値(必須は空欄。既定を補わない) |
| `fromSettings.ts` | **EP-02 の応答(`SourceDetailResponse`。null 許容の型)** → フォームの値。**TTL のモード**は応答の `ttl_days` の有無で決める(`null` なら秒)。**しきい値の丸め注意**: 応答の値が小数第 2 位を超えるとき、丸めた値(四捨五入が案)を入れ、`roundedNotice`(元の値・丸めた値)を返す(E 7.7)。**読めない項目**(`unavailable.<項目名>=malformed`)は空欄・必須にし、`connector_config` が読めないときは「フォームを出さない」判定を返す(E 7.6) |
| `toRequest.ts` | フォームの値 → EP-03 の `RegisterSourceBody`・EP-04 の `UpdateSourceBody`(E 7.5): 文字列を検証してから数値化、`ttl_days` か `ttl_seconds` の一方、S4 は `source_id`・`connector_type` を含めない、`connector_config` は 5 項目を常に全部、`schedule_cron` の空は `null`。**`ttl_days`・`ttl_seconds` は null を送らず、使わない方のキーを省く**(前提タスク A の完了前は、生成型が `ttl_*` を `number \| null` とするため型は通るが、実行時は明示的な null を 400 `type` で拒否する。完了後は型でも非 null になる。どちらでも出力は同じで、`toRequest` の単体テストが null の不在を検証する。E 7.5。承認済みの案(ゲート4)) |
| `rules.ts` | 項目 → 検証規則(`admin/lib/validation` を使う) |
| `fieldMap.ts`・`serverErrors.ts` | サーバーの `details.errors` を入力欄・行・上部アラートに振り分ける(3.5。`config_invalid` の `detail` は完全一致の対応表で照合、照合不能は上部アラート。E 6.4)。**本文の違反は 2 段階で返る**(形 → 範囲・桁・排他の順に、最初の 1 群だけ。送信後に別の違反が出うる。画面側の検証が同じ規則を持つので通常は出ない)。**`invalid_request` で `details.errors` がないときは想定外**(本文が読めない・Content-Type 違い・1 MiB 超など。フォーム上部のアラートに診断として `code` と HTTP ステータス) |
| `composables/useSourceForm.ts` | フォームの状態(値・クライアント検証・サーバーエラー・送信中)。保存は `createSource`・`updateSource`。成功は S2 へ移動+スナックバー(sources 2.5)。`describeError` の結果をフォームの 3 つの表示先に分ける |

- **`SourceSettings` が 2 種類ある**(確認 2026-11-26): EP-02 の応答 `SourceDetailResponse` は保存値が読めないときに備えて各項目が null 許容、EP-03・04 の応答 `SourceSettings`(200・201)は厳格な型で、B 2.11 の「共通」の記述とは異なる。`fromSettings.ts` は前者(EP-02)だけを受け、EP-03・04 の応答(後者)は保存後の遷移先(`source_id`)にだけ使う。

#### J1・J2 `features/jobs/`

| 要素 | 内容 |
| --- | --- |
| `pages/JobsListPage.vue`(J1) | `ListPage`+`FilterBar`(データソース・状態)+`JobsTable`(`AdminDataTableServer`)。取消は `dialogs/job-cancel` |
| `pages/JobDetailPage.vue`(J2) | `DetailPage`+カード(`JobSummaryCard`・`FailureAlert`・`WarningList`・`RegistrationCard`(`StatList`。件数・`partial`・`phase` が `null` なら「—」。`cellState`)・`DeletionCard`・`LockCard`)。操作は `jobActions.ts` |
| `composables/useJobsListPage.ts` | `jobsParams.ts` による URL の条件・`useJobsListQuery`・EP-01 の選択肢 |
| `composables/useJobDetailPage.ts` | `useJobDetailQuery`(10 秒のポーリング)・最終更新・「見つかりません」の判定(`isValidPathId` が偽、または 404) |
| `jobsParams.ts` | J1 の条件(URL `source`↔API `source_id`・`status`・`page`・`size`↔`items_per_page`・`sort`)の定義(E 5.6)。`sort` は union(3.5)。**API の `status=failed` にリース切れは含まれない**(リース切れは保存上 `running` のため、「失敗(リース切れ)」の行は `active` でしか出ない。画面で補わない。確認 2026-11-26) |
| `jobActions.ts` | **J2 の操作の出し分けの表**(jobs 2.3 の表)。取消: `cancellable=true` のときだけ。再実行: `rerunnable=true` なら「再実行」、`rerun_blocked_reason` が `superseded`・`stalled` なら**無効+理由**(「新しいジョブがあるため」「ロックを解放すると再実行できます」)、`not_failed`・`not_crawl`・`source_deleting` は出さない(DS 4.13。削除中は補足)。**`source_missing`(データソースの設定がない=削除済み。AAPI-P-41)も出さない**(削除済みのソースを再実行しない。専用文言は画面仕様に足す(HO-30)。E 6.7。FMOD-P-32)。**`status=null` のジョブには操作を出さない**。**`stalled`・`rerunnable`・`latest_for_source` が `null`(`rerunnable=null` は設定の読み取り失敗を含む)なら再実行・取消を出さず、理由を補足に**(E 1.2・6.7)。ロック解放は `stalled=true` のとき。ソース削除ジョブは失敗のときだけ「削除を再実行」 |
| `catalogs/` | 失敗理由・警告・削除結果の日本語表記(3.5。`warnings[]` の型ガードを含む) |
| `components/` | 上のカード・`JobsTable.vue`・`JobStatusCell.vue`(`stalled` でタグを切替。**`status=null` のジョブにはタグを出さず「—」**(読み上げは「読み取れません」)。取消・再実行も出さない。E 5.9・FMOD-P-31) |

- **J2 の `LockCard`・概要のリース期限**: `stalled=true` かつ `lease_expires_at=null` は「期限を確認できません(期限切れ)」(`formatLeaseExpiry(…, { expired: true })`。3.5)。
- **J2 の `DeletionCard`**: `deletion.current_state` が `unavailable`・`not_found` のとき、`deletion.fetched_at` を現在値の「取得時刻」として**出さない**(実装は `queued` 以外で、読み取りに失敗したときも「読もうとした時刻」を入れる。確認 2026-11-26。承認済みの案(ゲート4))。`deletion.current` の取得失敗は最上位 `unavailable` のキー(`topCell`)。

#### X1 `features/documents/`

| 要素 | 内容 |
| --- | --- |
| `pages/DocumentsPage.vue` | `ListPage`+データソース選択(`FilterBar`)+`CountTabs`+注記+`AdminDataTableServer`。タブごとに独立した状態(エラーはパネルだけ)。`tab` で `documentTabs` の定義を選び、`DocumentsTable` に行型つきの `rows`・`columns` を渡す |
| `composables/useDocumentsPage.ts` | `documentsParams.ts`(`source`・`tab`・`page`・`size`・`sort`)・`useDocumentsQuery`・`useSourcesListQuery`(選択肢。削除中は選べない)・タブ件数(**応答の `tab_counts`**。データソースが同じ間だけ前回の値を残す。E 5.6)・`existence` の扱い・アダプタによる行の絞り込み(3.5) |
| `documentTabs.ts`・`columns.ts` | タブ定義(行型・アダプタを含む)と列定義(3.5)。列は優先順位つきで、カード幅の閾値は画面ごと(DS 4.3) |
| `components/` | `SourceSelect.vue`・`DocumentsTable.vue`(行型ごとの列定義から描く)・`NoSourceState.vue`(未選択・登録 0 件) |

#### O1 `features/opensearch/`

| 要素 | 内容 |
| --- | --- |
| `pages/OpenSearchPage.vue` | `DashboardPage` テンプレート+1 カード「クラスタ状態」(`ClusterSummary`・`IndexFilter`・`ShardMatrix`) |
| `composables/useOpenSearchPage.ts` | `useOpenSearchClusterQuery`(**query なし**)・`opensearchParams.ts`(`q`・`state`。**`replace`**。`page` は URL に入れない)・絞り込み・`useContainerWidth` による 1 ページの列数 |
| `models/indexFilter.ts` | 絞り込みの純関数(名前=部分一致・大文字小文字無視・空白だけは条件なし、状態=OR、3 つ選択=条件なし、未知の状態値は除外。opensearch 3.5。状態値は `admin/lib/clusterValues.ts`) |
| `models/matrixModel.ts` | 行=ノード(+`node=null` の未割り当ての行)・列=インデックスのモデル。**行・列の並び(状態の悪い順→名前)は API の応答の並びをそのまま使い、`indices[]` にないインデックスの補完もしない**(API が並びと補完の両方を保証済みで、二重実装を避ける。確認 2026-11-26。承認済みの案(ゲート5。2026-11-26))。凡例の対象を決める |
| (部品の `columnsPerPage.ts`) | 1 ページの列数 `max(1, floor((W − H) ÷ 112))`(DS 4.15。`components/shard-matrix/`) |

- O1 は `unavailable` を引かない(3.5)。`cluster.status`・`indices[].status`・`shards[].role`・`state` は string で、`clusterValues.ts` のガードを通して未知値は中立表示にする。`truncated=true` の注記は E 6.7。

---

## 4. 画面 → route → ページ → composable → EP の対応表

### 4.1 画面ごとの対応(FMOD-P-22)

B 1.3 の画面×EP 対応表と、実装済みの Admin API の OpenAPI の `paths` を突き合わせた(9 画面+シェルで一致。確認 2026-11-26。作業記録 0004)。EP の欄の括弧内は生成 SDK の関数名で、読み取りは `{fn}Options`(Query)、書き込みは `{fn}Mutation` が使える(4.3)。key・更新・失敗時の表示は E 5.4・5.5・5.7、`data-testid` は各画面仕様に従う。

| 画面 | route(`name`・path。admin-view 4.2) | ページ | 画面の composable | queries(composable と、E 5.4 の key) | EP(生成 SDK) | 更新 | 状態の `testid` の接頭辞 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | `dashboard`・`/` | `DashboardPage.vue` | `useDashboardPage` | `useDashboardQuery`(`['dashboard']`) | EP-13(`getDashboard`) | 30 秒+手動 | `d1-` |
| S1 | `sources`・`/sources` | `SourcesListPage.vue` | `useSourcesListPage` | `useSourcesListQuery`(`['sources','list']`)、`useMetaQuery`(`['meta']`) | EP-01(`listSources`)、EP-14(`getMeta`) | 手動 | `s1-` |
| S2 | `source-detail`・`/sources/:sourceId` | `SourceDetailPage.vue` | `useSourceDetailPage` | `useSourceDetailQuery`(`['sources','detail',sourceId]`)、`useMetaQuery` | EP-02(`getSource`)、EP-14(`getMeta`) | 開いたとき・操作後 | `s2-` |
| S3 | `source-new`・`/sources/new` | `SourceCreatePage.vue` | `useSourceForm` | `useMetaQuery`、`createSource`(EP-03 の mutation) | EP-14(`getMeta`)、EP-03(`registerSource`) | — | `s3-`・`source-form-` |
| S4 | `source-edit`・`/sources/:sourceId/edit` | `SourceEditPage.vue` | `useSourceForm` | `useSourceEditQuery`(`['sources','edit',sourceId]`)、`useMetaQuery`、`updateSource`(EP-04 の mutation) | EP-02(`getSource`)、EP-14(`getMeta`)、EP-04(`updateSource`) | 開くたび(編集中は再取得しない) | `s4-`・`source-form-` |
| J1 | `jobs`・`/jobs` | `JobsListPage.vue` | `useJobsListPage` | `useJobsListQuery`(`['jobs','list',params]`)、`useSourcesListQuery`(`['sources','list']`) | EP-09(`listJobs`)、EP-01(`listSources`) | 手動 | `j1-` |
| J2 | `job-detail`・`/jobs/:jobId` | `JobDetailPage.vue` | `useJobDetailPage` | `useJobDetailQuery`(`['jobs','detail',jobId]`) | EP-10(`getJob`) | 10 秒(実行待ち・実行中) | `j2-` |
| X1 | `documents`・`/documents` | `DocumentsPage.vue` | `useDocumentsPage` | `useDocumentsQuery`(`['documents',sourceId,params]`)、`useSourcesListQuery`(`['sources','list']`) | EP-11(`listDocuments`)、EP-01(`listSources`) | 手動 | `x1-` |
| O1 | `opensearch`・`/opensearch` | `OpenSearchPage.vue` | `useOpenSearchPage` | `useOpenSearchClusterQuery`(`['opensearch','cluster']`) | EP-12(`getCluster`) | 手動 | `o1-` |
| シェル | (全画面) | `shell/AppShell.vue` | — | `useMetaQuery`(`useDashboardsUrl`。`['meta']`) | EP-14(`getMeta`) | 再読み込みまで | `nav-` |
| (404) | `not-found`・`/:pathMatch(.*)*` | `admin/router/NotFoundPage.vue`(`StateBlock` の最小ページ) | — | — | — | — | — |

- 「更新」列の「手動」は、定期更新とフォーカス・再接続による再取得をしない意で、**画面を開く・戻るときの再取得は行う**(E 5.4・5.5)。
- ページの `.vue` は `features/<名前>/pages/`(3.9)。すべての route は同期 import(単一チャンク。FMOD-P-17)。
- 404 の route は、新しい画面を作らず `ListPage` のエラーブロックを使う(admin-view 4.2)。`admin/router/NotFoundPage.vue` に置く。**Nginx は `/admin/` 配下の未知のパス(`assets/` 以外)に `index.html`(200)を返す**ので、未知の URL は SPA が起動し、この 404 の route が描く(E 3.2・3.3)。
- **EP-12(O1)・EP-13(D1)・EP-14(シェル・S1〜S4)は query を受けず、`getClusterOptions()` などを引数なしで呼ぶ**(3.3)。D1・O1 は `unavailable` も持たない(3.5)。
- `source`・`job` の ID を route から受ける画面(S2・S4・J2・X1)は、`isValidPathId`(3.3)が偽なら取得せず「見つかりません」にする。

### 4.2 操作(ダイアログ・保存)ごとの対応

E 5.8 の表を、置き場に対応づけた。

| 操作 | ダイアログ/画面 | mutation(生成の名前) | EP | 成功後 | invalidate(`invalidation.ts`) |
| --- | --- | --- | --- | --- | --- |
| クロール起動 | DLG-1(S1・S2) | `startCrawl`(`startCrawlMutation`) | EP-06 | スナックバー+「ジョブを表示」 | `['sources']`・`['jobs']` |
| 再実行 | DLG-4(J2) | `startCrawl`(`startCrawlMutation`。J2 の null の `force_delete`・`rewrite_mode` は false で送る。FARC-P-46) | EP-06 | 新しいジョブの J2 へ移動 | 同上 |
| データソース削除・削除の再実行 | DLG-2・再実行ダイアログ(S1・S2・J2) | `deleteSource`(`startSourceDeleteMutation`) | EP-05 | スナックバー(`job_id`)。**S1 の行が「削除中」になるとは限らない**(受付直後は設定の `status` が `active` のまま。削除ジョブの開始後に `deleting`。S2 のロック状態カードは即時に `held_delete`。3.9) | `['sources']`・`['jobs']` |
| 取消 | DLG-3(J1・J2) | `cancelJob`(`cancelJobMutation`) | EP-07 | スナックバー(200・202・409 `job_already_finished` を成功扱い) | `['jobs']`・`['sources']` |
| ロック解放 | DLG-5(S2・J2) | `releaseLock`(`releaseLockMutation`) | EP-08 | 200 かつ `released=true` ならスナックバー。**`released=false` は成功文言にせず、スナックバーも使わない**(ダイアログ内の info アラート「解放するロックがありませんでした」。3.8) | `['sources']`・`['jobs']` |
| 登録 | S3 | `createSource`(`registerSourceMutation`) | EP-03 | S2 へ移動+スナックバー(200 の冪等応答も同じ) | `['sources']` |
| 保存 | S4 | `updateSource`(`updateSourceMutation`) | EP-04 | S2 へ移動+スナックバー | `['sources']` |

- 書き込み(EP-03〜08)の `invalid_response`(Nginx の 502・504 を含む)・`network`・`timeout`・504 `crawler_response_lost` は**結果不明**(3.3。FARC-P-43)。EP-03・04 は再送が安全なので「もう一度保存」を出してよい。
- 起動系・取消・解放の再試行は出さず、一覧・J2・S2 で確認する導線を出す(E 6.5)。

### 4.3 EP の番号と生成 SDK・Query の名前

実 OpenAPI(`servers=[{url:'/api/admin/v1'}]`。`paths` は相対)の `operationId` と、Hey API 0.99.0 の生成物の名前(確認 2026-11-26。作業記録 0004・0005)。生成名は `operationId`(snake_case)の camelCase。読み取り(GET)は `{fn}Options`・`{fn}QueryKey`(`queries` は key を上書きするので `{fn}QueryKey` は使わない。3.4)、書き込み(POST・PUT・DELETE)は `{fn}Mutation`。応答・本文の型は**スキーマ名**を使う(3.3)。

| EP | メソッド・パス(`/api/admin/v1` からの相対) | `operationId` | 生成 SDK・Query の名前 | 応答(HTTP ステータス)のスキーマ | 本文 | query | `unavailable` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EP-01 | `GET /sources` | `list_sources` | `listSources` | `SourceListResponse`(200) | — | なし | 行ごと(最上位は常に `{}`) |
| EP-02 | `GET /sources/{source_id}` | `get_source` | `getSource` | `SourceDetailResponse`(200) | — | なし | 最上位 |
| EP-03 | `POST /sources` | `register_source` | `registerSource` | `SourceSettings`(200・201) | `RegisterSourceBody`(必須) | — | なし |
| EP-04 | `PUT /sources/{source_id}` | `update_source` | `updateSource` | `SourceSettings`(200) | `UpdateSourceBody`(必須) | — | なし |
| EP-05 | `POST /sources/{source_id}/delete-jobs` | `start_source_delete` | `startSourceDelete` | `JobAccepted`(202) | なし | — | なし |
| EP-06 | `POST /sources/{source_id}/crawl-jobs` | `start_crawl` | `startCrawl` | `JobAccepted`(202) | `StartCrawlBody`(任意。画面は常に両方を明示) | — | なし |
| EP-07 | `POST /jobs/{job_id}/cancel` | `cancel_job` | `cancelJob` | `CancelJobResponse`(200・202) | なし | — | なし |
| EP-08 | `DELETE /sources/{source_id}/lock` | `release_lock` | `releaseLock` | `ReleaseLockResponse`(200) | なし | — | なし |
| EP-09 | `GET /jobs` | `list_jobs` | `listJobs` | `JobListResponse`(200) | — | `page`・`items_per_page`・`sort`・`source_id`・`status` | 行ごと(最上位は常に `{}`) |
| EP-10 | `GET /jobs/{job_id}` | `get_job` | `getJob` | `JobDetailResponse`(200) | — | なし | 最上位 |
| EP-11 | `GET /sources/{source_id}/documents` | `list_documents` | `listDocuments` | `DocumentListResponse`(200) | — | `tab`・`page`・`items_per_page`・`sort` | 行ごと+最上位(`tab_counts.<タブ>`・`document_count`) |
| EP-12 | `GET /opensearch/cluster` | `get_cluster` | `getCluster` | `ClusterResponse`(200) | — | **なし** | **なし** |
| EP-13 | `GET /dashboard` | `get_dashboard` | `getDashboard` | `DashboardResponse`(200) | — | **なし** | **なし** |
| EP-14 | `GET /meta` | `get_meta` | `getMeta` | `MetaResponse`(200) | — | **なし** | **なし** |

- 失敗の応答は、どの EP も `ErrorResponse`(`{ error: { code, message, retryable, details? } }`)。`code` は string で、EP ごとに返りうる code は B 2.3・各 EP の節に従う(`errorTable`。3.3)。
- 日時は `format` なしの素の string(UTC・ミリ秒・`Z`)。整形は `shared/lib/datetime.ts`(`responseTransformer` は使わない)。
- 書き込みの本文は、EP-03・04 は `Content-Type: application/json` を必ず付ける(B 2.12。ないと 400)。EP-06 の本文は任意だが、画面は常に JSON 本文を付ける(E 7.5)。

---

## 5. 主要シナリオの流れ

(`→` は呼び出し。EP・code の中身は B と実 OpenAPI、方針は E を参照。)

### 5.1 S1 からのクロール起動と 409 `lock_held`(FARC-P-14・FARC-P-43)

1. `SourcesListPage` が `useSourcesListPage` → `useSourcesListQuery`(EP-01)で一覧を表示。行の「クロール起動」で `CrawlStartDialog`(DLG-1)を開く(`dlg-crawl-start`)。
2. ダイアログで強制削除・再書き込みを指定(`ConfirmDialog` の水準と帯の色は `dialogLevel.ts`)。実行 → `useOperationDialog` が `startCrawl`(EP-06。`force_delete`・`rewrite_mode` を明示)を呼ぶ。
3. **202**: ダイアログを閉じ、`useSnackbar` で「受け付けました(ジョブ ID)」+「ジョブを表示」(J2 へ)。`invalidation.ts` の表で `['sources']`・`['jobs']` を invalidate。S1 の一覧が再取得される。
4. **409 `lock_held`**: 生成クライアントが受け取ったエラー(パース済みの JSON)を、error interceptor に登録した `toApiError` が `ApiError`(`kind='api'`)にして投げ、`describeError`(`errorTable`)が「ダイアログ内アラート」と variant を返す(E 6.3。FARC-P-35・44)。
   - `lease_expired`(ジョブ記録あり)なら warning+「ジョブ詳細でロックを解放」(J2 へ)。`orphan` なら warning+「ロック状態を確認」(**S2 のロック状態カード**。孤児ロックの解放の入口は S2 だけ)。`just_acquired`(取得から 60 秒以内)・`unknown` は「ジョブを表示」を出さず、待って確認する案内(S2 へのリンク)。`held_crawl`・`held_delete`(ジョブ記録あり)は error+「ジョブを表示」(`existing_job`)。
   - **`existing_job.status`(または `job_type`)が `null`、または既知の値でない(未知の文字列)ときは J2 へ導かない**(EP-10 が 404 になりうる。`canLinkToJob`。admin-view 7.7 との差は I-88。ゲート3でユーザー確認済み(2026-11-23)。「または未知の値」はゲート4(2026-11-26)で追加)。
   - `options_applied=false` なので「指定は反映されていない」を太字で出す。`refusal.ts` が文面を組み立て、`existing_job.lease_expires_at` は `formatLeaseExpiry` を通す。ダイアログは開いたまま、実行ボタンは「閉じる」に置き換わる。
   - 同じ EP-06 の 409 には `source_deleting`・`maintenance_enabled` もある(OpenAPI の説明。確認 2026-11-26)。表示先は `errorTable` に従う(E 6.3)。
5. **結果不明**(FARC-P-43。承認済みの案(ゲート4。2026-11-26)。対象を EP-03〜08 とした訂正は承認済みの案(ゲート5。G5-2。2026-11-26)。書き込みの `invalid_response` を `status` を問わず結果不明とする点は承認済みの案(ゲート5。G5-1。2026-11-26)): **書き込み(EP-03〜08)の失敗のうち、504 `crawler_response_lost`(JSON)、`invalid_response`(Nginx が返す HTML の 502・504 など。`status` を持つ)、`network`、クライアントの `timeout` は、結果が分からない**。`api` が Crawler を呼んだ後に切れた可能性があるため、`describeError` は `outcomeUnknown=true` を返し、ダイアログは**再試行を出さず**、一覧(S1・J1)・S2・J2 で確認する導線を出す。文言は画面仕様・E 6.5 に従う。
   - **保存系(EP-03・04)の 504 は例外で、再送が安全**(B 9.2.4・9.2.5。登録の再送は冪等で 200。E 6.5)。「もう一度保存」を出してよい(5.3)。
   - **読み取り**の失敗は結果不明ではない。**`timeout` は再試行せずエラーブロック**。`network`・`retryable=true` の 5xx・`invalid_response`(Nginx 由来の 502・503・504)は、Query が **1 回だけ**再試行し、なお失敗すればエラーブロック(E 5.4)。
6. **削除(EP-05。DLG-2)の場合**: 202 の直後、**S1 の行は「削除中」にならないことがある**(受付直後は設定の `status` が `active` のまま。削除ジョブの開始後に `deleting`)。S2 のロック状態カード(EP-02 の `lock.state`)は即時に `held_delete`。S1 は `delete_job=null` のままで正常なので、「行が変わる」ことを前提にせず、スナックバー(`job_id`)と invalidate による再取得で足りる(3.9。S-E1。v0.1 の「S1 の行が『削除中』になる」は誤りだった)。

### 5.2 D1 の 30 秒ポーリングと取得失敗

1. `useDashboardPage` が `autoRefresh`(`ref`。既定オン)を持ち、`useDashboardQuery(autoRefresh)` が `polling.ts` の `refetchInterval: 30000`(オンのときだけ)・`refetchIntervalInBackground: false` で EP-13(`getDashboard`。**query は付けない**)を取得。
2. 成功のたびに `dataUpdatedAt` が「最終取得成功」の日時になる(クライアント保持)。タイルは `dashboardComponents` の順に `components[]`(8 件)から描き、`SummaryBand` が件数を出す。**EP-13 は `unavailable` を持たない**。取得できないコンポーネントは `components[].state=undetermined` と `reason` で表し、FE は `state`・`reason` を表示するだけ(`web` タイルの判定は API が行う。前提タスク B+C の完了後は `web` への HTTP 確認だが、FE は変わらない)。
3. 取得に失敗(`network`・`timeout`・`invalid_response`(Nginx 由来の HTML の 502・503・504 など)・5xx。EP-13 自体は 200 を返す限り失敗しない): **`timeout` は再試行しない**。`network`・`retryable=true` の 5xx・`invalid_response`(502・503・504)は Query が 1 回だけ再試行する(E 5.4)。再試行してもなお失敗したとき(と `timeout`)は、初回は `StateBlock`(`d1-state-error`)。2 回目以降は `isRefetchError` → `dashboardViewModel` が前回「正常」「異常」のタイルを判定不能に降格し「前回の状態」を添え、`PageAlert`(stale。`d1-state-stale`)を出す。通知(スナックバー)は出さない。成功すれば通常の表示に戻る。
4. スイッチをオフにすると `refetchInterval` が `false` になり、「自動更新は停止中」の文を出す。手動の「更新」は `refetch()`。

### 5.3 S3 の登録と `config_invalid` の項目別表示・上部アラート

1. `SourceCreatePage` → `useSourceForm`。入力はフォーカスが外れたとき・送信時に `rules.ts` で検証。エラーがあれば `ErrorSummary`(件数つき・項目へのリンク)を出して送信しない(DS 4.6)。
2. 送信: `toRequest.ts` が文字列を検証してから数値化し、`ttl_days` **または** `ttl_seconds`(**使わない方のキーは省き、null を送らない**。前提タスク A の前後で同じ)・`ratio_threshold_percent`・`min_delete_count`・`connector_config`(5 項目)を組む → `createSource`(EP-03。`Content-Type: application/json`)。
3. **201・200**(冪等): S2 へ移動+スナックバー、`['sources']` を invalidate。登録直後に S1 へ戻ると新規ソースが見えないことがある(EP-01 は検索ベースで反映が遅れうる。S-E5。最大遅延は未測定)が、S3 の成功は S2 へ移動するので影響は小さい。
4. **400 `invalid_request`・`config_invalid`**: `serverErrors.ts` が `details.errors[]` を `fieldMap` で振り分け、`reason` を文言にして出す。入力内容は残す。
   - `field` が `connector_config.include_patterns[2]` のような**添字つき**なら、該当の行の下(`config_invalid` の `detail` は完全一致の対応表で画面の文言に)。
   - **添字なしの配列エラー**(`connector_config.include_patterns`・`exclude_patterns`。100 件超)は、該当の**一覧の下**。
   - **`connector_config` 単体**(`field="connector_config"`。プレフィックスなし。S-E3)は、フォーム**上部のアラート**。
   - `ttl_days`・`ttl_seconds` の排他・必須の違反は、`field` が両方とも `ttl_days` 固定のため、TTL 欄(モードによらず)に写す(S-D5)。
   - `errors` が空、照合できない `detail`、表にない `field` は、フォーム上部のアラート。
   - **本文の違反は 2 段階で返る**(形 → 範囲・桁・排他の順に、最初の 1 群だけ。S-D4)。送信後に、直した後で別の違反が出うる。画面側の検証が同じ規則を持つので、通常は出ない。
   - **`invalid_request` で `details.errors` がない**のは想定外(本文が読めない・Content-Type 違い・1 MiB 超など。S-E4): フォーム上部のアラートに診断として `code` と HTTP ステータスを出す。
5. **409 `source_already_exists`**: 識別子の項目の下(`details.status=deleting` なら補足)。**503**(`crawler_unavailable`・`crawler_unreachable`): フォーム上部の消えないアラート。**結果不明**(504 `crawler_response_lost`・`invalid_response`(Nginx の HTML の 502・504)・`network`・`timeout`): フォーム上部の消えないアラートに「S2 で確認する」と「**もう一度保存**」を出す(**保存系は再送が安全**。5.1。E 6.5)。

### 5.4 J2 の取消と再実行(EP-06 を呼ぶ)

1. `JobDetailPage` → `useJobDetailPage` → `useJobDetailQuery`(EP-10)。実行待ち・実行中は `polling.ts` が 10 秒ごとに再取得(終端で停止)。`job_id` が `isValidPathId` を満たさなければ取得せず「見つかりません」(3.3)。
2. `jobActions.ts` が応答(`cancellable`・`rerunnable`・`rerun_blocked_reason`・`stalled`・`latest_for_source`)から操作を返す。**`status=null` のジョブには操作そのものを出さない**。`null` のフラグ(`stalled`・`rerunnable`・`latest_for_source`)は「不可」で、取消・再実行を出さず、補足に「確認できません」。`cancellable=true` のときだけ「取消」。再実行は `rerunnable=true` なら「再実行」(primary)、`superseded`・`stalled` は**無効+理由**、`not_failed`・`not_crawl`・`source_deleting`・`source_missing`(AAPI-P-41)は出さない。`PageActions` が描く(jobs 2.3)。
3. **取消**: `JobCancelDialog`(DLG-3)→ `cancelJob`(EP-07)。200・202 はスナックバー。**409 `job_already_finished` は成功扱い**(ダイアログを閉じ「すでに終了しています(状態: …)」)。202 の後も終端までポーリングが続く。結果不明(5.1 の 5)は確認の導線。
4. **再実行**: 専用の EP はない(B 4.1)。`JobRerunDialog`(DLG-4)が J2 の応答の `source_id`・`force_delete`・`rewrite_mode` を**読み取り専用で提示**し、確認チェックの後、`startCrawl`(EP-06。同じ値を渡す)を呼ぶ。**`force_delete`・`rewrite_mode` が `null` のとき(FARC-P-46)は false として送り、「記録なし(なしとして実行)」と表示する**(破壊的な指定を推測で付けない)。成功は**新しいジョブの J2 へ移動**(#32)。409 `lock_held` なら 5.1 と同じ表示。
5. リース切れ(`stalled=true`)は「ロックを解放…」(DLG-5 → `releaseLock`(EP-08))が主操作。J2 の `LockCard`・概要のリース期限は、`lease_expires_at=null` なら「期限を確認できません(期限切れ)」(`formatLeaseExpiry(…, { expired: true })`。3.5)。EP-08 の 200 で **`released=false`**(解放するロックがなかった)のときは成功のスナックバーを出さず、ダイアログ内の info アラート「解放するロックがありませんでした」を出す(3.8。J-E6。実機未検証=推測を含む)。`lock_in_use` の `lock_state=unknown` は理由を断定しない文言。

### 5.5 X1 のタブ切替

1. `DocumentsPage` → `useDocumentsPage`。URL の `source`・`tab`・`page`・`size`・`sort` を `documentsParams` で正規化(不正値は既定値にして `replace`)。
2. `source` 未選択、または `isValidPathId` を満たさないなら `useDocumentsQuery` は `enabled: false`(「データソースを選んでください」/「見つかりません」)。選択肢は `useSourcesListQuery`(EP-01。削除中は選べない)。
3. タブの切替は `router.push` で `tab` を変え、1 ページ目に戻る(`documentTabs` の kebab の `id` を URL に、snake の `tab` を API に)。`useDocumentsQuery`(EP-11 `listDocuments`。query は `tab`・`page`・`items_per_page`・`sort`)が取得。前回データは**同じデータソース・同じタブ**のページ・並べ替えの変更のときだけ保持(`placeholder.ts`)。
4. **行の型の絞り込み**: ページが `tab` で `documentTabs` の定義を選び、その**アダプタ**が応答の `items`(判別子のない 4 型の `anyOf`)を、そのタブの行型の配列にする(応答の `tab` が自分のタブで、各行が他の 3 型にないキーを持つか。3.5)。合わなければ想定外の応答として診断つきのエラーブロック。
5. 応答の `tab_counts` を `CountTabs` の件数に使う(`null`・最上位 `unavailable` の `tab_counts.<タブ>` は「—」。引くのは `topCell`)。スキップのタブは各行の `existence`(`unknown` は「確認できません」。その行の `unavailable` の `existence`。一括検索(1 回の `ids` クエリ)の失敗は全行。行ごとに成否が分かれることはない。引くのは `rowCell`)。
6. エラーはパネルだけ(`x1-state-error`)。タブ名・データソースの選択は操作できる。更新は手動の「更新」のみ(`refetch()`)。

---

## 6. 依存ルール

機械検査は **ESLint の `no-restricted-imports`**(flat config の `files` ごとの設定)を第一候補とする(E 11.1。FMOD-P-18)。パターンで書けない規則は FMOD-U-1。**検査の対象は、生成ディレクトリ(`src/admin/api/generated/`)と `dist/` を除く `apps/web/` のすべてのソース**(E 11.1)。**リポジトリ直下の `tests/integration/<名前>/`(`apps/web/` の外。7.1)は `apps/web` の ESLint の対象外で、R2・R3 は適用しない**(ツール・言語とその lint は実装時に決める。FMOD-U-8)。**`apps/web/tests/**`・`*.test.ts` に適用するのは R2 と、R3 のうち `fetch`・`XMLHttpRequest` の呼び出しと `@hey-api/*` の import の禁止だけ**(生成コードと HTTP を直接使わない。fixtures の型は公開口 `@/admin/api` から。7.1)。`fetch` の**差し替え**(`fetchStub.ts`。呼び出しではない)と、モックのパス(`**/api/admin/v1/**`)は許す(承認済みの案(ゲート5。2026-11-26))。他の規則は対象外。

| # | 規則 | 理由 |
| --- | --- | --- |
| R1 | `shared/` は `admin/`・`vue-router`・`@tanstack/vue-query`・生成コードを import しない | Search View と共有するため(2.3) |
| R2 | `admin/api/generated/` を import してよいのは `admin/api/` の中だけ。外は `@/admin/api`(公開口)だけ | 生成物の形の変更を `admin/api/` に閉じる(Hey API 0.x。E 5.2) |
| R3 | `fetch`・`XMLHttpRequest`・`@hey-api/*`・文字列 `'/api/admin/v1'` は `admin/api/` と `shared/api/` の中だけ | HTTP の入口を 1 か所にする(E 5.3) |
| R4 | `@tanstack/vue-query` を import してよいのは `admin/queries/` と `admin/app/setupQuery.ts` だけ(例外: **型の import(`import type`)は `admin/composables/useViewState.ts` でも可**。入力を構造的な型で受ける形にしてもよい)。`admin/api/` の手書きのコード(`client.ts` など。3.3)も import しない(Options を包まず、型を構造的に受ける必要もない) | 画面が Query の API を直接使わない |
| R5 | `admin/lib/` は `vue`・`vue-router`・`vuetify`・`.vue`・`queries` を import しない(純粋。ただし `import type { InjectionKey } from 'vue'` は可)。**型の import(`import type`)は `@/admin/api`(公開口)から可**(`existingJob.ts` の `JobStatus`・`JobType`、`expectedFields.ts`・`clusterValues.ts` の型など)。`generated/` は直接 import しない(R2) | 単体テストしやすく、サーバー・UI から独立 |
| R6 | `admin/queries/` は `vue-router`・`.vue`・`vuetify`・`components`・`templates`・`dialogs`・`shell`・`features`・`router`・`app` を import しない | データ取得を UI から分ける |
| R7 | `admin/components/`・`admin/templates/` は `queries`・`admin/api`(値の import)・`vue-router`・`features`・`dialogs`・`shell` を import しない(`admin/api` は `import type` のみ可)。`templates` が必要とする状態は **`viewState`(`admin/lib/viewState.ts` の型)を props で受け**、`error.code` を判定しない。パンくずは `admin/lib/injectionKeys.ts` の key で inject する(`shell` を import しない)。`composables`・`lib`・`shared` は可 | 見た目の部品はデータ取得を知らない(DS 11)。`templates` が `shell`(層 4)・`admin/api`(値)を import しない理由 |
| R8 | `admin/features/<A>/` は他の `features/<B>/` を import しない。`admin/router/`(`routeNames` は `admin/lib/` にあるので不要)・`admin/app/` も import しない。共有したいものは `components`・`dialogs`・`queries`・`lib` に移す | features どうしの結合を避ける |
| R9 | `admin/dialogs/` は `features`・`shell`・`router`・`app` を import しない。`admin/queries/mutations/` と `@/admin/api`(公開口。`describeError` など)を使ってよい | 画面から独立した操作の部品 |
| R10 | `admin/shell/` は `features`・`dialogs`・`app` を import しない。`queries/meta`・`composables`(`useBreadcrumbs`)・`vue-router` は可。`featureFlag` の評価は `shell`(`SideNav`・外部リンク領域)だけで行う | I-89 |
| R11 | `admin/router/` は `features` のページ・`templates`(404)・`lib` を import する。`queries`・`shell`・`app` は import しない(ガードは認証・`featureFlag` を持たない。MVP は遷移後の処理だけ) | |
| R12 | `@mdi/js` を import してよいのは `shared/theme/icons.ts` だけ(他はそこから)。`@mdi/font` は禁止 | アイコンを 1 か所で管理し、tree-shaking とポリシー確認(FARC-U-3)を 1 か所にする |
| R13 | `vuetify` の部品を import してよいのは `shared/ui`・`shared/theme`・`admin/components`・`templates`・`shell`・`dialogs`・`features` の `.vue` だけ(`api`・`queries`・`lib`・`composables` は不可)。`createVuetify` を呼ぶのは `admin/app/setupVuetify.ts` だけ | Vuetify の設定の入口を 1 か所にする(DS 3) |
| R14 | `localStorage`・`sessionStorage` を使わない(ユーザー設定を持たない) | E 8章 |
| R15 | `admin/app/` を import するのは `main.ts` だけ | 最上位 |
| R16 | `admin/composables/` は `queries`・`components`・`templates`・`dialogs`・`shell`・`features`・`router`・`app` を import しない。`vue`・`vue-router`・`@/admin/api`(公開口。`useViewState` が `describeError` を使う)・`lib` は可 | 汎用の composable を層 2 に保つ |
| R17 | `admin/api/` は `admin/` 内の他のモジュール(`lib`・`queries`・`composables` など)を import しない。import してよいのは `shared/api` と自分の `generated/` だけ(承認済みの案(ゲート5。G5-3。2026-11-26)) | `lib` は型を公開口から import する(R5)ので、逆向きを許すと循環する。層 1 の最下部に保つ |

- **層の向き**(2.2)は R1〜R17 の組み合わせで表す。同じ層どうし(`dialogs` と `shell`、`components` と `templates`、`queries` と `composables`)の import は、上の規則に書いたもの以外は**禁止**とする(案)。
- **生成コードの扱い**(承認済みの案(ゲート4。2026-11-26)。FARC-P-45):
  - `src/admin/api/generated/` は lint・format の対象外なので、**中の `fetch`・`@tanstack/vue-query`・`@hey-api/*` の import は R3・R4 の検査に掛からない**(生成物の実装。手書きのコードには適用する)。
  - 除外されるのは**生成ファイル自身の検査**だけで、**R2 は import する側に掛かる**ので除外の影響を受けない(生成ディレクトリの外から `generated/` を import すると R2 で落ちる)。
  - `admin/api/` の手書きのコード(`client.ts`・`index.ts` など)は検査の対象で、`generated/` を import してよいが(R2)、`@tanstack/vue-query` は import しない(R4。エラーの正規化は client の interceptor で行い、Options を包まないので不要。3.3)。
- **`src/main.ts` の `import 'vuetify/styles'` は R13 の対象外**: R13 は Vuetify の**部品(コンポーネント・composable)**の import を制限する規則で、`vuetify/styles` は CSS の副作用 import であり部品ではない。必須(`vite-plugin-vuetify` はコンポーネント単位の CSS しか入れない。2.4)で、`main.ts` だけに置く。`main.ts` は `admin/app/` の import(R15)・`vuetify/styles` の import・`@/admin/api` の `configureApiClient` の呼び出し(2.4。E 5.3)だけをする。
- **`admin/lib` が型を `@/admin/api` から import する**のは、R5 の「型の import(`import type`)は公開口から可」のとおり。公開口は、`lib` が使う型(`JobStatus`・`JobType` など。スキーマ名の型)を再 export する(3.3)。
- 規則はパターンの否定(`!`)で書けるか、`import type` だけを許す例外(R4・R5・R7)を `no-restricted-imports` で表せるか、`features` ごとの override が冗長にならないかを実装時に確認する(FMOD-U-1)。足りなければ `eslint-plugin-boundaries` か `dependency-cruiser` を足す(E 11.1)。
- **規則を破りやすい場所**(実装時にレビューで見る): `features` からの `vue-query` 直接利用(R4)、`components` からの `useRoute`(R7)、`api` の `generated` の直接 import(R2)、公開口が返さない `{Op}Response2` の型の利用(3.3)、Query の `error` を `ErrorResponse` と信じて `.error.code` を読むこと(FARC-P-44。`isApiError`・`describeError` を通す。lint では検出しにくい)、`configureApiClient()` の冪等性を壊すこと(呼ぶたびに interceptor を登録する書き方。3.3。7.2 の単体テストで見る)、EP-12・13・14 への query の付与(3.3。lint では検出しにくい。7.2 のテストで見る)、`lease_expires_at` を `formatLeaseExpiry` を通さず整形すること(3.5。lint では検出しにくい)。

---

## 7. テスト構成

E 10 の方針の置き場。テストコード・設定ファイルは作らない(FARC-P-38)。

### 7.1 配置(FMOD-P-19)

```text
# `src/`・`tests/support/`・`tests/e2e/` は `apps/web/` の中。`tests/integration/` だけはリポジトリ直下
src/**/<対象>.test.ts          # Vitest。対象の隣に置く(純粋ロジック・composable・部品)
src/**/<対象>.contract.test.ts # Vitest。OpenAPI・実際に送られる URL との契約テスト。対象の隣(名前は案)
tests/support/
  setup.ts                     # Vitest の setup(単体テストだけ。E2E では呼ばない): `configureApiClient()` の呼び出し(本番と同じ設定。E 5.3。冪等)、ResizeObserver のモック、TZ=Asia/Tokyo(`test.server.deps.inline: ['vuetify']` は vite.config.ts。E 10.1)
  mount.ts                     # createVuetify()+VLayout+Router+QueryClient(retry:false)で包む共通ヘルパー
  fetchStub.ts                 # Vitest 用: fetch を差し替え、生成クライアントを実際に通す(MSW は使わない)。受けた Request(URL・メソッド・本文)を記録する
  mockApi.ts                   # Playwright 用: page.route('**/api/admin/v1/**')。未モックの /api/ への要求は失敗させる(E 10.2)
  apiErrors.ts                 # A 5.2 の形のエラー応答(JSON)と、Nginx 由来の HTML のエラー応答・通信断を作るビルダー(型付き)
  fixtures/                    # EP ごとの応答。生成した型で `satisfies`(meta.ts・dashboard.ts・sources.ts・jobs.ts・documents.ts・opensearch.ts)
tests/e2e/
  *.spec.ts                    # Playwright(API モック)。画面ごと+shell(ガード・SPA 内 404)
tests/integration/<名前>/      # リポジトリ直下(`apps/web/` の外)。実 API(`web` 経由)の接続確認(読み取りのみ)。前提タスク B+C の完了後。下の「実 API の接続確認」
```

- `apps/web/tests/` は `@/admin/api`(公開口)の**型だけ**を import し、`generated/` を直接 import しない(R2 を `apps/web/tests/` にも適用する。fixtures の型付けのため)。公開口は `{Op}Response2` を再 export しない(3.3)ので、fixtures は**スキーマ名の型**(`JobDetailResponse` など)で `satisfies` する。
- `apps/web/` 直下の `playwright.config.ts` が `tests/e2e/` を指す。`baseURL` は `http://localhost:5173/admin/`(末尾スラッシュ。E 10.2)。`tests/e2e/` は API モックのテストだけで、実 API のスモークは置かない(下)。
- **jsdom と `fetch` の差し替え**(確認 2026-11-26。作業記録 0005 の 3a): Node 単体では、生成クライアントの相対 `baseUrl`(`/api/admin/v1`)で `new Request()` が `Invalid URL` になり、`{error: TypeError}` が**黙って返る**。そのため Vitest は jsdom 環境(E 10.1。jsdom 31)で `fetch` を差し替えてテストする。**jsdom 環境で相対 `baseUrl` の `Request` が解決されるかは未確認**(E の FARC-U-9。FMOD-U-6・U-12 と合わせて実装時に確認する。`fetch` の差し替え先は、`configureApiClient()` が `setConfig` で渡すタイムアウト付き fetch の内側で呼ばれるもの)。**解決しなければ、`tests/support/setup.ts` で `client.setConfig({ baseUrl: <絶対 URL。例 http://localhost/api/admin/v1> })` を呼ぶ**(`client.ts` にテスト用の形は持たせない。`baseUrl` が `/api/admin/v1` であることの確認(3.3)は、上書き前の値で別に行う。E 10.1)。
- **実 API の接続確認(前提タスク B+C の完了後に有効)**: `web` 経由で実 API に接続する確認は、既存の結合テスト(リポジトリ直下の `tests/integration/{api,crawler,indexer}/`)の慣習に倣い、**リポジトリ直下の `tests/integration/<名前>/`(`apps/web/` の外)** に置く(FMOD-U-8 の候補 (b)。0004 で「現実的」とした。名前・ツールは実装時に決める)。既存の結合テストと同じく、固定のホストポート(**9200・8000・8001・8080**。`web` の公開ポートは `WEB_HOST_PORT`)と compose のプロジェクト名を共有するので**同時に動かさない**(排他ロックと共通ファイルは `scripts/lib/` の流儀に揃える)。内容の案(読み取りのみ。E 10.2): D1・S1・O1 が `web` 経由で開く、`/admin/sources` の再読み込みが SPA を返す、`/admin/assets/` の欠落ファイルが 404、`/api/admin/v1/…` の未知のパスが JSON の 404、`%2F`・`%2E` を含む `job_id` が `web`(Nginx)を素通しされること(E 12.4 の FARC-U-21。FMOD-P-4 の確認)。期待値の案(文書レビューの指摘。実機では未確認): `GET /api/admin/v1/jobs/a%2Fb` → 404 `not_found`、`GET /api/admin/v1/jobs/%2E` → 404 `job_not_found`。変更操作は含めない。

### 7.2 モジュール別のテストの種類

| 対象 | 種類 | 内容 |
| --- | --- | --- |
| `admin/api/errors/errorTable`・`describeError` | Vitest(単体) | **B 2.3 の全 `code`(Admin 固有 14 種+共通 6 種)を表から網羅**(code を足すとテストが落ちる。E 10.1)。`lock_state` ごとの variant。書き込み(EP-03〜08)の `invalid_response`・`network`・`timeout`・`crawler_response_lost` で `outcomeUnknown=true`(EP-03・04 は再送可)、読み取りは「再試行」ボタンを出す |
| **`errorTable` ↔ OpenAPI の `description`**(`admin/api/errors/errorTable.contract.test.ts`) | Vitest(契約。承認済みの案(ゲート4。2026-11-26)) | コミット済みの `openapi/admin-v1.json` を読み、全 EP の `responses` の説明文(`… error.code: a, b` の書式)から code を集めて、(1) **OpenAPI に出る code が全部 `errorTable` にある**、(2) **`errorTable` の Admin 固有 14 種が OpenAPI のどれかの説明文に出る**ことを検証する。OpenAPI で `code` は string で列挙がなく、**code は各 EP の説明文にしか出ない**ため、表(手書き)と説明文(API の実装由来)のずれをここで検出する。OpenAPI の説明文に出る code は Admin 固有 14 種+共通の `invalid_request`・`unavailable` の計 16 種で、共通のうち `not_found`・`method_not_allowed`・`http_error`・`internal_error` は OpenAPI に宣言がない(確認 2026-11-26)ので、A 5.2・B 2.3 から作った表の側だけで網羅する。JSON は CI の「再生成して差分ゼロ」(E 11.2)で実装と一致が保たれるので、実行時に API を呼ばない。説明文の書式が変わるとテストが落ちる(それで検出してよい) |
| `admin/api/errors/toApiError` | Vitest(単体) | 3.3 の「interceptor が受け取る値」の表の全行: パース済みの JSON(A 5.2 の形)→ `kind='api'`(`outcomeUnknown` は `details.outcome_unknown` から)、`string`(HTML)→ `invalid_response`(`status` つき)、`TypeError` → `network`、タイムアウト → `timeout`、`Error` でない値・`error.code` を持たない JSON → `invalid_response`。`fetchStub` で JSON のエラー・HTML の 502・504・通信断を返したとき、生成 SDK を通した実際の失敗が、error interceptor 経由で `ApiError` として投げられること。Query の `AbortError`(キャンセル)は `ApiError` にならずそのまま通り、タイムアウト(`TimeoutError`)は `timeout` になる(区別。E 5.3)。**`isApiError` でないものを `describeError` に渡すと `invalid_response`** |
| **`admin/api/pathParams`**(`pathParams.contract.test.ts`)・`client` | Vitest(契約。承認済みの案(ゲート4)) | **パス値の検証**: `fetchStub` で**実際に送られる URL**を捕捉して(生成 SDK を通す)、`job_id='a%b?c#d'` → `/jobs/a%25b%3Fc%23d`、`a/b` → `%2F`、日本語が正しくエンコードされることを検証する。値全体が `.`・`..`・空文字・制御文字を含む値・文字列でない値は、**パスに入れる値のどれ**(`source_id`・`job_id`)でも**リクエストを送らず**拒否され、合成した `invalid_request`(400)になること(送ると `/jobs/`・1 階層上など別の EP に化けるため)。`a.b`・`my.source`・`..a`・`a..` は拒否されず、そのまま送られること。`isValidPathId` の純関数としての網羅。`client`(`configureApiClient()`): `client.getConfig().baseUrl` が `/api/admin/v1`・タイムアウト(偽のタイマー。読み 45 秒・書き 90 秒)・利用者の中断(`AbortError`)とタイムアウトの区別・`ApiError` への正規化・**2 回呼んでも interceptor が二重に登録されない**(冪等) |
| `admin/queries/*` | Vitest | key factory、`polling.ts`(D1 のオン・オフ、J2 の状態ごとの間隔)、`placeholder.ts`(同スコープだけ)、`invalidation.ts` の表、`enabled: false`(`isValidPathId` が偽・`source` 未選択)、**EP-12・13・14 のリクエスト URL に query が付かない**(`fetchStub` で `?` の不在を確認) |
| `admin/lib/unavailable`・`expectedFields`・`leaseExpiry`・`existingJob`・`clusterValues`・`lockStateView`・`viewState`・`units`・`validation` | Vitest(純粋) | 正式パス(最上位)と行内の相対パス(行の `unavailable`)・`cellState` の 4 状態(行・最上位のそれぞれ)・**source-a の未実行(キーなし)と source-b の読み取り失敗(キーあり)の区別・全行失敗(全行に同じキー)・1 行だけの失敗(他の行に影響しない)**・`expectedFields` の行型ごとの表・番兵と `stalled=true` かつ `lease_expires_at=null`(`expired: true`)・`canLinkToJob`(`status`・`job_type` の null・未知の値)・OpenSearch の状態値の未知値(中立)・ロック状態 7 値+取得失敗の写像(E 5.10)・`viewState` の写像(E 6.2)・日 ↔ 秒・丸め(`String(n)` に頼らない桁判定 `Number(n.toFixed(2)) !== n`・十進での丸めの境界値 `2.675`・`1.005`)・9 桁・パターンのバイト数 |
| `admin/composables/useListParams`・`useBreadcrumbs`・`useViewState` | Vitest | URL ↔ 条件、不正値の正規化(`replace`)、条件を変えたら 1 ページ目に戻る、`push`/`replace`。パンくずの親の解決(`params` の引き継ぎ)。`viewState` の組み立て(404 の「見つかりません」・stale・`describeError` の結果) |
| `features/*/models`・`*Actions.ts`・`*Params.ts` | Vitest(純粋) | `dashboardViewModel`(降格)、`indexFilter`・`matrixModel`(API の並びを保つ。補完しない)、`jobActions`・`sourceActions`(状態 → 操作の全組合せ。`status=null` は操作なし)、`documentTabs` の kebab ↔ snake と**行型のアダプタ**(4 型を他の型にないキーで判別、合わない行・タブは想定外)、`sourceRow`(`status=null` の行は「削除中」にしない)、`fromSettings`(TTL モード・丸め・`malformed`) |
| **`features/sources/form/toRequest`** | Vitest(純粋。承認済みの案(ゲート4)) | **`ttl_days` と `ttl_seconds` の使わない方が、キーごと存在しない**こと(`'ttl_seconds' in body` が偽。`JSON.stringify` した結果に `null` の `ttl_*` が現れない)。日・秒の両モード。前提タスク A の前(生成型が `ttl_*` を `number \| null` とするため型は通る)でも後でも同じ出力であること。S4 は `source_id`・`connector_type` を含めない。`connector_config` は 5 項目を常に全部 |
| `features/sources/form/fieldMap`・`serverErrors` | Vitest(純粋) | `ttl_days` 固定の排他・必須 → TTL 欄、添字つき・添字なしの配列エラー、`connector_config` 単体 → 上部アラート、照合できない `detail`・表にない `field` → 上部アラート、`invalid_request` で `details.errors` なし → 診断つきの上部アラート |
| `features/jobs/catalogs`・`dialogs` の純関数 | Vitest(純粋) | `warningCatalog` の型ガード(`code` が string でない要素は一般的な文言)、`refusal.ts`(`lock_held` の variant・`canLinkToJob`)、DLG-4 の `force_delete`・`rewrite_mode` の null → false、`released=false` の文言 |
| `shared/ui`・`admin/components` | Vitest(コンポーネント) | props と状態の出し分け(`StatusTag` の未登録警告、`ConfirmDialog` の実行ボタンの有効/無効と理由、`PatternListInput` の追加・削除・Enter、`ShardMatrix` の列数)。レイアウト・コンテナクエリ・フォーカスの実挙動は E2E と実機 |
| `admin/dialogs` | Vitest+E2E | 状態機械(`useOperationDialog`)、拒否の組み立て(`refusal.ts`)。フォーカスの閉じ込め・復帰は E2E |
| `features/*` のページ | E2E(Playwright。API モック) | 画面のフロー(5章の各シナリオ)、状態(読み込み中・空・エラー・stale・見つかりません)、URL の同期、ポーリング(時計の操作。FARC-U-8)、書き込みの結果不明(HTML の 502・504・通信断で再試行を出さない・保存系は「もう一度保存」) |
| `admin/router`・`shell` | E2E | ガード・遷移後のフォーカス・タイトル・SPA 内 404・サイドバーの出し分け(840px の境) |
| 実 API の接続確認(`web` 経由) | 結合(リポジトリ直下の `tests/integration/<名前>/`。前提タスク B+C の完了後) | 7.1 の末尾。読み取りのみ |
| 依存ルール | lint | 6章(ESLint) |

### 7.3 モックとフィクスチャの規約(E 10.2。FMOD-P-20)

- フィクスチャは **EP ごと・状態ごと**(正常・空・部分失敗(`unavailable`。行単位: 全行失敗・1 行だけの失敗・未実行の行と失敗の行が混在)・`null` のフラグ・値の読めない `null`(`status=null` のジョブ・S1 の `status=null` の行)・`source_missing`・番兵日時・`stalled=true` かつ `lease_expires_at=null`・`existing_job` の `status` が null または未知の値・`force_delete`・`rewrite_mode` が null のジョブ・`released=false`・読めない設定項目・保存値のしきい値が小数第 3 位以下・EP-11 の 4 つの行型)の関数として `tests/support/fixtures/` に集め、Vitest と Playwright で**共有**する。すべて生成した型(スキーマ名の型)で `satisfies` する(B の変更が型エラーになる)。EP-02 の応答(`SourceDetailResponse`)と EP-03・04 の応答(`SourceSettings`)は別の型(3.9)。
- エラー応答は `apiErrors.ts` のビルダーで作る。JSON のエラーは A 5.2 の形(`code`・`retryable`・`details`)。**Nginx 由来の失敗**は、`text/html` の 502・503・504・413 の応答と、通信断(`route.abort()`・`fetch` の `TypeError`)を返すビルダーで作る(`invalid_response`・`network` の再現)。
- `mockApi.ts` は「パス+メソッド → 応答(固定または関数)」の宣言を受け、`**/api/admin/v1/**` に束ねる。ポーリング・再取得のテストのため、応答の差し替え(呼び出し回数ごと)ができる。**未モックの `/api/` への要求はテストを失敗させ**、開発プロキシの先に流さない(E 10.2)。
- **契約テスト**(7.2)は、フィクスチャでなく**コミット済みの OpenAPI JSON と、実際に送られる URL**を正とする(モックで固定した応答では、API の変更もパスの化けも検出できないため)。

---

## 8. 確認状況

### 8.1 確認した事実(2026-11-26)

- **読んだ文書**: 作業記録 0003〜0007、v0.1 の本書(5〜8 章)、E v0.2(全章を本書と照合済み(2026-11-26。8.7。作業記録 0011 の文書レビューで確認)。E 4.1 には `configureApiClient()` の呼び出しを追記済み。節番号は 0006 の 4.1 の対応表に従った)、実 OpenAPI。
- **実 OpenAPI の再読**(本書の執筆時): 書き出した JSON(sha256 `ce60fc1a…bf51`。作業記録 0004 と一致。14 EP・12 パス)で、(1) 各 EP の `responses` の説明文が `… error.code: a, b` の書式で、Admin 固有 14 種+`invalid_request`・`unavailable` の計 16 種が出て、`not_found`・`method_not_allowed`・`http_error`・`internal_error` は宣言がない。(2) `ErrorBody.code` は string で列挙なし。(3) EP-11 の `items` は判別子のない 4 型の `anyOf` で、各型の `required` は 3.5 のとおり(`SkippedDocument.existence`、`ExtractFailedDocument`・`SummaryPendingDocument` の `document_id` が非 null)。(4) `RegisterSourceBody`・`UpdateSourceBody` の `ttl_days`・`ttl_seconds` は `integer \| null`(既定 null)。
- **技術検証**(作業記録 0005。リポジトリ外の使い捨て。**本書の作成時には再実行していない**): Hey API 0.99.0 の生成(`infiniteQueryOptions: false` で 17 ファイル・約 111KB。既定は 114KB。出力が決定的なことは既定の設定で確認。`{Op}Response2` の衝突)、生成 `queryFn`・`mutationFn` が `throwOnError: true` で `ErrorResponse`・`string`・`TypeError` を投げうること、パス値のエンコード(`encodeURIComponent`。`.`・`..`・空文字は URL が化ける)、`exactOptionalPropertyTypes` で生成コードの型検査が落ちること、Node 単体の相対 `baseUrl` の失敗、Vite 8 + Vuetify 4.3.4 のビルド(`vuetify/styles`・`sass`・`@types/node`)、Nginx 設定の実機確認(Node 24・`nginx:alpine`)。
- **版・照合**(作業記録 0004。再確認していない): 依存の版と Node 要件(E 2 章)、既存設計と実 OpenAPI の差分(S-/J-/X- の ID)。
- **リポジトリの状態**: `apps/web/` は存在しない(新規)。リポジトリ直下に `tests/integration/{api,crawler,indexer}/` と `scripts/run-{api,crawler,indexer}-integration-test.sh`・`scripts/lib/it-common.sh`(排他ロックの共通ファイル)がある。現行の compose は `api` を `127.0.0.1:${API_HOST_PORT:-8080}:8080` で publish している(前提タスク B+C で外れる。作業記録 0004 の X-C2・0007 の 2 章)。
- **訂正**(I-130): 作業記録 0004 の X-BD1 は EP-11 の行で「`skipped` の `existence` のみ非 null」としたが、実 OpenAPI を読むと `ExtractFailedDocument`・`SummaryPendingDocument` の `document_id` も非 null。本書は**実 OpenAPI を正**とした(3.5)。

**確認していないこと**: 8.4 の FMOD-U 全件。ほかに、(1) Nginx 越しの `%2F`・`%2E` の保持(前提タスク B の実機確認。E 12.4)、(2) jsdom 環境での相対 `baseUrl` の解決(7.1)、(3) `stalled=true` の経路・EP-08 の `released=false`(実機未検証。AAPI-U-9)、(4) `TimeoutError`・`AbortError` が error interceptor に届くこと(3.3 の表の 2 行。設計で未確認。FMOD-U-12)。

### 8.2 確定(FMOD-K)

確定にしたのは、ユーザーの明示回答・指示と、確定として書かれた既承認文書の引用だけ。

| ID | 内容 | 出典 |
| --- | --- | --- |
| FMOD-K-1 | (欠番。確定ではなく承認済みの案(DS のゲート B・C の承認事項の引用)のため FMOD-P-26 に移した) | — |
| FMOD-K-2 | UI は Vuetify 4.3.4(exact pin)・TypeScript 6.x・`@mdi/js`・自前ナビで作る | DS 10.1(承認済み(ゲート B))。E の FARC-K-1。「コード・設定ファイルは作らない」は確定にせず E の FARC-P-38(案を含む)に従う |
| FMOD-K-3 | 要素の特定はロール・ラベル基準で、必要な箇所だけ `data-testid`。命名は DS 9章・画面仕様 | DS 0.1 の前提 6(承認済み)。E の FARC-K-9。名前の細則は案 |
| FMOD-K-4 | **(v0.2 で更新)** Web UI は `web` コンテナ(Nginx)が静的配信し、`/api/` を `api` へプロキシする(ブラウザから見て同一オリジン。CORS 不要)。Search View は設計しない(配置の境界だけ) | **確定(ユーザー指示 2026-11-26。作業記録 0003)**。v0.1 の「`api` が静的配信する」(BAPI-K-2。ユーザー回答 2026-11-22。前提タスク `create_admin_system_design` の 0001 Q2)を上書きする。E の FARC-K-4 |

### 8.3 案・承認済みの案(FMOD-P)

v0.1 の FMOD-P-1〜33 は中身を保って引き継いだ(ゲート3。2026-11-23 の承認)。**v0.2 で変更・追加したものは、区分欄に「承認済みの案(ゲート4。2026-11-26)」と書いた。ゲート4 の後に決めた設計の詳細・軽微な導出は「承認済みの案(ゲート5。2026-11-26)」(G5-1・G5-2)**。区分欄の「承認済みの案」は、E・A・B の承認済みの案を実装に落としたもの。

| ID | 内容 | 区分 | 章 |
| --- | --- | --- | --- |
| FMOD-P-1 | `apps/web/` の構成: `src/shared/`(共有層)・`src/admin/`(Admin 専用。層 1〜7)・`tests/`、ルート直下の設定ファイル(v0.2 で `.nvmrc`・`.npmrc`・`Dockerfile`・`nginx/default.conf` を追加。FMOD-P-35) | 承認済みの案(ゲート3。2026-11-23。ディレクトリ `apps/web/` は承認済みの案(ゲート2。BAPI-P-11)) | 2.1・2.2 |
| FMOD-P-2 | Search View と共有する範囲=`shared/{theme,ui,api,lib}`。Admin 専用=シェル・テンプレート・データテーブル・確認ダイアログ・`KeyValueList` | 承認済みの案(ゲート3。2026-11-23。DS 11 の方針に沿う) | 2.3 |
| FMOD-P-3 | `shared/api` に `ApiError`(**v0.2: `invalid_response` が `status` を持つ**)、`admin/api` に生成コード・クライアント・エラー表。正規化(`toApiError`。error interceptor に登録)は `admin/api/errors/`(FMOD-P-34) | 承認済みの案(ゲート3。2026-11-23。E 5.3 の置き場)。`status` と正規化の置き場は承認済みの案(ゲート4。2026-11-26) | 3.2・3.3 |
| FMOD-P-4 | **パスエンコード(FARC-U-18 への案)**: `admin/api` の層で `pathParams.ts` に集約して保証し、契約テストで検証。**v0.2 で拡張: パス値の送信前検証(値全体が `.`・`..`、空、制御文字を含む、文字列でない値を拒否。パスに入れる値すべて。`a.b` などは拒否しない)。画面側は route の ID が不正なら取得せず「見つかりません」、最終防衛は request interceptor(送信せず、合成した `invalid_request`(400)にする。E 5.3)** | 承認済みの案(ゲート3。2026-11-23)。**拡張は承認済みの案(ゲート4。2026-11-26)。request interceptor で検証する方式は承認済みの案(ゲート5。2026-11-26)** | 3.3・3.4 |
| FMOD-P-5 | `admin/queries`: 読み取りも書き込みもここ。key factory・`polling.ts`・`placeholder.ts`・`invalidation.ts`・`mutations/`。**v0.2: 公開口が再 export する生成の Options・Mutation を `withKey` で key を差し替えて使う(正規化は client の interceptor)。`error` は `unknown` として扱う。EP-12・13・14 は引数なしで呼び query を付けない** | 承認済みの案(ゲート3。2026-11-23。E 5.4・5.5・5.8 の置き場)。v0.2 の追記は承認済みの案(ゲート4。2026-11-26)。ただし `withKey` による key の差し替えは承認済みの案(ゲート5。2026-11-26) | 3.4 |
| FMOD-P-6 | エラー変換表 `errors/errorTable.ts` と `describeError.ts`(Admin 固有 14 種+共通 6 種を網羅)。**v0.2: 手書きの表が正本で、OpenAPI の説明文との契約テストを置く(code は OpenAPI で string)** | 承認済みの案(ゲート3。2026-11-23。E 6.3 の置き場)。契約テストは承認済みの案(ゲート4。2026-11-26) | 3.3・7.2 |
| FMOD-P-7 | DS 4章の部品の置き場の規則(DS に仕様がある部品は `admin/components` か `shared/ui`)と、全件の置き場の表 | 承認済みの案(ゲート3。2026-11-23) | 3.6 |
| FMOD-P-8 | テンプレート 4 型・`PageHeader`・`PageActions`。状態は `viewState` を props で受ける(FMOD-P-27) | 承認済みの案(ゲート3。2026-11-23) | 3.7 |
| FMOD-P-9 | シェルの構成(`AppShell`・`SideNav`・`MobileAppBar`・`SkipLink`・`ExternalLinks`・`externalLinks.ts`)。パンくずの provide は `AppShell` | 承認済みの案(ゲート3。2026-11-23) | 3.7 |
| FMOD-P-10 | 複数画面から開く操作ダイアログは `admin/dialogs/`(`useOperationDialog`・拒否の組み立ての純関数)。**v0.2: `existing_job` の未知値、DLG-4 の null(FARC-P-46)、DLG-5 の `released=false`** | 承認済みの案(ゲート3。2026-11-23)。v0.2 の追記は承認済みの案(ゲート4。2026-11-26) | 3.8 |
| FMOD-P-11 | `features/<名前>/` の内部構成(`pages`・`components`・`composables`・`models`・定義表)と各画面のファイル。**v0.2: S1 の `status=null`・`last_completed_at` を使わない・J2 の `deletion.fetched_at`・O1 は API の並びを使う** | 承認済みの案(ゲート3。2026-11-23)。v0.2 の追記は承認済みの案(ゲート4。2026-11-26)。ただし `last_completed_at`・`connector_type` を使わない・O1 が API の並びを使う・S2 の `status=null` は承認済みの案(ゲート5。2026-11-26) | 3.9 |
| FMOD-P-12 | 定義表の置き場(`navGroups`・`documentTabs`・`dashboardComponents`・条件の定義・`fieldMap`・catalogs・検証・単位・操作表)。**v0.2: `documentTabs` の各定義が行の型とアダプタを持つ。`clusterValues.ts`・`existingJob.ts` を追加** | 承認済みの案(ゲート3。2026-11-23)。v0.2 の追記は承認済みの案(ゲート4。2026-11-26) | 3.5 |
| FMOD-P-13 | 一覧の条件は `composables/useListParams` と画面ごとの `*Params.ts` で URL ↔ API を対応づける | 承認済みの案(ゲート3。2026-11-23。E 5.6 の実装) | 3.5・3.9 |
| FMOD-P-14 | `admin/lib/unavailable.ts`: 行の `unavailable` を引く関数(`rowUnavailableReason`・`rowCell`)と最上位を引く関数(`topUnavailableReason`・`topCell`)、`cellState`。**行単位で判定**し、旧規則の `isRowUnavailable` は廃止。値の読めない `null` は `cellState` で別に扱う。**v0.2 の訂正: 最上位の `unavailable` を持つのは EP-02・10・11 だけ(EP-12・13・14 は持たない。D1・O1 は引かない)** | 承認済みの案(ゲート3。2026-11-23)の修正(PR #10 のレビュー指摘への対応。AAPI-P-42。E 5.9・FARC-P-27・36・39 の置き場)。**訂正は承認済みの案(ゲート4。2026-11-26)** | 3.5 |
| FMOD-P-15 | `admin/lib/leaseExpiry.ts`: 番兵日時を判定し「期限切れ」にする 1 か所。`lease_expires_at` の表示はすべてここを通す。**v0.2: `stalled=true` かつ `lease_expires_at=null` は「期限を確認できません(期限切れ)」** | 承認済みの案(ゲート3。2026-11-23。E 5.9・FARC-P-24 の置き場)。追記は承認済みの案(ゲート4。2026-11-26) | 3.5 |
| FMOD-P-16 | S3・S4 共有のフォーム(`form/`): `connectors/fileSystem.ts`・`fromSettings`・`toRequest`・`rules`・`fieldMap`・`serverErrors`。TTL モード・しきい値の丸め注意・`malformed` の判定を `fromSettings` に持たせる。**v0.2: `toRequest` は `ttl_*` の null を送らない。`SourceSettings` が 2 種類。`fieldMap` の添字なし配列・`connector_config` 単体・TTL 欄への写像** | 承認済みの案(ゲート3。2026-11-23。E 7.5〜7.7・FARC-P-16・28・29 の置き場)。v0.2 の追記は承認済みの案(ゲート4。2026-11-26) | 3.9 |
| FMOD-P-17 | ルートは**遅延読み込みしない**(MVP。同期 import の単一チャンク)。根拠: 9 画面で規模が小さく、再配備後の開いたままのタブの旧アセット取得失敗(E 3.3)と構成の複雑さを避けられる。ただし**ビルドサイズの実測前の判断**で、実装後に測って再判断する(FMOD-U-11)。使うことにした場合は `router.onError` を足す(E 3.3・FARC-P-18) | 承認済みの案(ゲート3。2026-11-23。E 12.6 の「遅延読み込みの判断」への回答) | 4.1 |
| FMOD-P-18 | 依存ルール R1〜R17(ESLint `no-restricted-imports` を第一候補。`apps/web/tests/` に適用するのは R2 と、R3 のうち `fetch`・`XMLHttpRequest` の呼び出しと `@hey-api/*` の import の禁止だけ。R2・R3 は `tests/integration/<名前>/` に適用しない)。**v0.2: 生成ディレクトリは検査の対象外である旨の注記(R2 は import する側に掛かる)、`vuetify/styles` は R13 の対象外。R17(`admin/api` は `admin/` 内の他モジュールを import しない)の追加。R9・R16 は `admin/api` の公開口経由に統一** | 承認済みの案(ゲート3。2026-11-23)。注記は承認済みの案(ゲート4。2026-11-26)。`tests/` への R3 の適用範囲は承認済みの案(ゲート5。2026-11-26)。R17 の追加と R9・R16 の公開口への統一は承認済みの案(ゲート5。G5-3。2026-11-26) | 6章 |
| FMOD-P-19 | テストの配置: 単体は対象の隣(`*.test.ts`)、`tests/support/`・`tests/e2e/`。**v0.2: 契約テストは対象の隣(`*.contract.test.ts`)、実 API の接続確認はリポジトリ直下(`apps/web/` の外)の `tests/integration/<名前>/`(FMOD-U-8)** | 承認済みの案(ゲート3。2026-11-23。E 10 の置き場)。追記は承認済みの案(ゲート4。2026-11-26) | 7.1 |
| FMOD-P-20 | フィクスチャは EP×状態の関数で Vitest・Playwright が共有し、生成型で `satisfies`。`apiErrors.ts` のビルダー。**v0.2: Nginx 由来の HTML・通信断のビルダー、新しい状態のフィクスチャ** | 承認済みの案(ゲート3。2026-11-23。E 10.2 の実装)。追記は承認済みの案(ゲート4。2026-11-26) | 7.3 |
| FMOD-P-21 | `data-testid` は部品の `testid` props でルート要素に付け、付く位置を部品の中で固定。命名は DS 9・画面仕様 | 承認済みの案(ゲート3。2026-11-23。命名の細則は DS で案) | 3.6 |
| FMOD-P-22 | 画面 → route → ページ → composable → EP の対応表(4.1)と、操作ごとの対応(4.2)。**v0.2: 実 OpenAPI で照合し、生成 SDK の関数名・Query の名前に直した(4.3 を追加)** | 承認済みの案(ゲート3。2026-11-23。B 1.3・E 5.7・5.8 の展開)。照合は承認済みの案(ゲート4。2026-11-26) | 4章 |
| FMOD-P-23 | アイコンは `shared/theme/icons.ts` だけが `@mdi/js` を import | 承認済みの案(ゲート3。2026-11-23) | 3.1・6章 |
| FMOD-P-24 | ファイル名: `PascalCase.vue`・`useXxx.ts`・`camelCase.ts`・`kebab-case` ディレクトリ | 承認済みの案(ゲート3。2026-11-23) | 2.1 |
| FMOD-P-25 | ルート直下の設定ファイルの一覧(名前のみ)。`@` は `src` の別名 | 承認済みの案(ゲート3。2026-11-23) | 2.4 |
| FMOD-P-26 | ナビは route `meta` で一元管理、ページテンプレート 4 型、DS 4.5・4.8 の状態表示(読み込み中・空・エラー・stale)と危険度別の確認ダイアログの規約(旧 FMOD-K-1)。DS 4 章のその他の部品(4.15 の具体値・4.18〜4.20 ほか)は DS の区分に従う(案) | 承認済みの案(DS 4.5・4.8・5.3・6章のゲート B・C の承認事項の引用。ユーザー確認済み(ゲート3。2026-11-23)) | 3.6・3.7 |
| FMOD-P-27 | `viewState`(`loading`・`empty`・`error`・`notfound`・`stale`・`ready`+更新中・更新時刻・診断・再試行の可否)を `features` の composable が `useViewState`(`admin/composables`。`describeError` を使う)で作り、`templates` はそれだけを props で受ける(R7) | 承認済みの案(ゲート3。2026-11-23) | 3.7 |
| FMOD-P-28 | パンくずは `AppShell` が `useBreadcrumbs` で作って provide し、`PageHeader` が inject する(`PageBreadcrumbs` は `templates`)。`shell` と `templates` の層の向き、`templates` と `components` の同層禁止を保つため | 承認済みの案(ゲート3。2026-11-23) | 3.7 |
| FMOD-P-29 | 外部リンクは route を持たない定義表(`shell/externalLinks.ts`)で持ち、`featureFlag` の評価は `SideNav`・外部リンク領域だけ(ガードでは評価しない)。DS 5.3 との差は E の I-89 | 承認済みの案(ゲート3。2026-11-23) | 3.5・3.7 |
| FMOD-P-30 | ロック状態の写像は `admin/lib/lockStateView.ts`(S2・J2・DLG-1 が共有。E 5.10) | 承認済みの案(ゲート3。2026-11-23) | 3.5 |
| FMOD-P-31 | セルの表示状態 `cellState`(`value`・`unavailable`・`unreadable`・`none`)と、値があるはずの項目の表 `expectedFields.ts`。引く対象の `unavailable`(行または最上位)を引数に取る。`status=null` のジョブはタグ・操作なし(E 5.9。FARC-P-36)。**v0.2 の訂正: `expectedFields` は応答の型・行の型ごとに持つ(EP-01 の行の `status=null`、EP-02 の null 許容の設定項目、EP-11 の 4 行型)。`status=null` の S1 の行は「削除中」判定も操作も出さない(S2 も同じ。E 5.7)** | 承認済みの案(ゲート3。2026-11-23。B の AAPI-P-25 は同じゲート3で承認)の修正(PR #10 のレビュー指摘への対応。AAPI-P-42)。**訂正は承認済みの案(ゲート4。2026-11-26)。S2 の `status=null` の扱いは承認済みの案(ゲート5。2026-11-26)** | 3.5・3.9 |
| FMOD-P-32 | `jobActions.ts` は `rerun_blocked_reason=source_missing` を「出さない」(E 6.7。FARC-P-37) | 承認済みの案(ゲート3。2026-11-23。AAPI-P-41) | 3.9 |
| FMOD-P-33 | 一覧の EP(EP-01・09・11)の画面は、行の `unavailable`(`rowCell`)で取得失敗を判定し、最上位の `unavailable`(`topCell`)は行に属さない項目(EP-11 の `tab_counts.<タブ>`・`document_count`)と単一の応答(EP-02・10)だけに使う。S1・J1・X1 の行モデルは行ごとに失敗を持つ。**v0.2 の訂正: 単一の応答で最上位の `unavailable` を持つのは EP-02・10(・11)だけ** | 承認済みの案(ゲート3。2026-11-23)の修正(PR #10 のレビュー指摘への対応。2026-11-23。AAPI-P-42・FARC-P-39)。**`-K-` ではない**。訂正は承認済みの案(ゲート4。2026-11-26) | 3.5・3.9・5.5 |
| **FMOD-P-34** | `admin/api` に**実行時エラーの正規化**(`errors/toApiError.ts`。FARC-P-44。生成クライアントが投げる値は型と食い違い、`ErrorResponse` のほか Nginx の HTML(`string`)・`TypeError` などになる)と**パス値の検証**(FMOD-P-4 の拡張)を置く。**入口は `configureApiClient()`(`client.ts`。冪等)が設定する client の `interceptors.error`(`toApiError`)・`interceptors.request`(パス値の検証。不正なら合成した `invalid_request`(400))とタイムアウト付き fetch(自前の `AbortController`。`AbortSignal.any` は使わない)で、Options を包むラッパーは作らない。`baseUrl` は設定しない(生成物が持つ)。`describeError` は `unknown` を `isApiError` で確認し、`ApiError` でなければ `invalid_response` として扱う。`shared/api` の `ApiError.invalid_response` は `status` を持つ。生成型は `{Op}Response2` でなくスキーマ名の型を使う。EP-12・13・14 は引数なしで呼び query を付けない。`withKey` は `admin/queries`(FMOD-P-5)** | 承認済みの案(ゲート4。2026-11-26。正規化層とパス値検証を置くこと。FARC-P-43・44・45)。**入口の方式**(`configureApiClient()`・`interceptors.error`・`interceptors.request`・`baseUrl` を設定しない・自前の `AbortController` 付き fetch・`AbortSignal.any` を使わない)は承認済みの案(ゲート5。2026-11-26。G5-1。E 5.3)。実機確認の残りは FARC-U-22(実装時)。`configureApiClient()` の冪等化は承認済みの案(ゲート5。G5-3。2026-11-26) | 3.2・3.3・3.4 |
| **FMOD-P-35** | ルート直下の設定ファイルの一覧に `.nvmrc`・`.npmrc`(`engine-strict=true`)・`engines`・`Dockerfile`(`web` イメージ)・`nginx/default.conf` を追加する(名前と要点のみ。中身は E 3.3・3.5 と実装時) | 承認済みの案(ゲート4。2026-11-26。FARC-P-3・20・40・41) | 2.1・2.4 |

### 8.4 未決・実装時確認(FMOD-U)

解消した ID は削除せず、状態欄に根拠を書く(欠番にしない)。

| ID | 内容 | 状態(v0.2) | 決める場所 |
| --- | --- | --- | --- |
| FMOD-U-1 | ESLint `no-restricted-imports`(パターン・否定・`files` ごとの設定・`import type` だけを許す例外)で R1〜R17 を表せるか。足りなければ `eslint-plugin-boundaries`・`dependency-cruiser` | 未決(維持) | 実装時 |
| FMOD-U-2 | 生成 SDK がパスの値をどうエンコードするか(`job_id`・`source_id`。FARC-U-18)。FMOD-P-4 の手順 (1)〜(3) の確認 | **解消(v0.2)**: 作業記録 0005 の 3(P2-a)で確認。`encodeURIComponent` で、`.`・`..`・空文字は URL が化けるため、FMOD-P-4 を送信前検証に拡張した。Nginx 越しの `%2F`・`%2E` の保持は E 12.4 の FARC-U-21 | — |
| FMOD-U-3 | Hey API 0.99 の生成物のファイル構成と、`admin/api/index.ts` で再 export する範囲(FARC-U-4・5) | **解消(v0.2)**: 作業記録 0005 の 1(P2-a)で、17 ファイル・公開名・`{Op}Response2` の衝突を確認し、3.3 に反映した | — |
| FMOD-U-4 | `AdminDataTable`・`AdminDataTableServer` が `VDataTable`・`VDataTableServer` の差(`@update:options`・`hover`・`aria-sort`・単一ソート。FARC-U-2)を吸収できるか | 未決(維持。`VDataTableServer` は 0005 で未検証) | 実装時 |
| FMOD-U-5 | `ConfirmDialog` が Vuetify の `VDialog` で DS 4.8 のフォーカス規則(閉じ込め・復帰・`persistent`)を満たすか(FARC-U-14) | 未決(維持) | 実装後(`web-ui-reviewer`) |
| FMOD-U-6 | `ShardMatrix` の列数の算出(`ResizeObserver`)の jsdom でのテスト方法(FARC-U-9)と、列見出しの読み上げ(opensearch 7章) | 未決(維持。jsdom 31 を採用したが、Vuetify 4.3.4 の部品が jsdom で動くかは FARC-U-9。相対 `baseUrl` の解決は FMOD-U-12) | 実装時 |
| FMOD-U-7 | `shared/` の範囲の見直し(Search View の設計時。FARC-U-17) | 未決(維持) | Search View の設計 |
| FMOD-U-8 | 実 API の接続確認の置き場(`tests/e2e/smoke.spec.ts` か、`tests/integration/<名前>/` の慣習か) | **候補 (b)「`tests/integration/<名前>/`」が現実的**(0004。`tests/integration/api/` などが実在する。7.1)。名前・ツール(Playwright か HTTP クライアントか)は未決。前提タスク B+C の完了後 | 実装時 |
| FMOD-U-9 | `.`・`..` だけの ID の扱い(ブラウザの URL の正規化。推測)。取得しない扱いでよいか | 未決(維持)。SDK が `.`・`..` を別の EP に化かすことは確認済み(0005)で、取得しない扱い(3.3・3.4)で書いた。route の `:jobId` が `.`・`..` のときにブラウザ・Vue Router が URL をどう正規化するかは未確認(推測) | 実装時 |
| FMOD-U-10 | 動的な `meta.title`(関数。I-83)と `PageBreadcrumbs`・`useBreadcrumbs`・`document.title` の実装の詳細 | 未決(維持) | 実装時 |
| FMOD-U-11 | ルート遅延読み込みをしない判断(FMOD-P-17)を、実装後のビルドサイズ(Vuetify の tree-shaking 後の JS・CSS)の実測で再判断する | 未決(維持。0005 に今回の SPA 相当の実測がある(JS 420KB・CSS 311KB。未圧縮)が、本物の画面ではない) | 実装後 |
| **FMOD-U-12** | **(新規)** `configureApiClient()` の**実機確認**。方式は E 5.3 で決まっている(`interceptors.error` に `toApiError`、`interceptors.request` でパス値の検証、タイムアウト付き fetch)ので、**確認の内容は E の FARC-U-22 に従う**: interceptor が受け取る値と応答(HTTP ステータス)、request interceptor の例外が error interceptor を通ること、タイムアウト(`TimeoutError`)と Query のキャンセル(`AbortError`)の区別、`fetch` の失敗(`TypeError`)の捕捉、`AbortSignal.any` を使わない実装の確認。F 側に固有の確認は、`fetch` の差し替え(7.1)。jsdom 環境での相対 `baseUrl` は E の FARC-U-9 に従い、解決しなければ setup で絶対 `baseUrl` を `client.setConfig` する(`client.ts` にテスト用の形は持たせない。7.1)。**`TimeoutError`・`AbortError` が error interceptor に届くかは設計で未確認**(3.3 の表)。実機確認の結果、方式が変わるなら 3.3 を直す | 実装時確認(v0.2。方式は E 5.3 で `interceptors.error`・`interceptors.request` に決定。解消ではなく、E の FARC-U-22 の実機確認に従う) | 実装時 |
| **FMOD-U-13** | **(新規)** EP-11 の行型(`SkippedDocument`・`ExtractFailedDocument`・`OversizeDocument`・`SummaryPendingDocument`)ごとに、**どの項目を `expectedFields` の「値があるはず」とするか**を確定する(B 6 章の項目表と documents 6 章の列から導く。実 OpenAPI で非 null なのは `SkippedDocument.existence`、`ExtractFailedDocument`・`SummaryPendingDocument` の `document_id`) | 未決(新規。v0.2) | 実装時 |

### 8.5 既存設計との不整合(I-n)

本書の予約範囲は I-100〜109 と I-130〜139。E の 12.5(I-120〜129)・12.7 の差分一覧と同じ事実を指す場合がある。本書は**モジュール構成に関わるもの**だけを挙げる。B・A・DS・画面仕様は変更せず、追従改訂は HO(A 9章に追加)に集約する。

| ID | 内容 | 本書での扱い |
| --- | --- | --- |
| I-100 | 画面仕様(sources 1.3・documents 4章)は `PageHeader`(DS 6.1)と呼ぶが、DS には部品としての節・名前の定義がない(6.1 の「ページ見出し領域」) | `admin/templates/PageHeader` と命名(3.6)。DS への追記は HO-27 |
| I-101 | DS 4.15 は `ShardMatrix`・`ClusterSummary`・`IndexFilter`・凡例・ページ送りバーを 1 つの節に含め、独立した節・部品名の一覧がない | `admin/components/shard-matrix/` にまとめて置く(3.6)。部品名は DS 4.15・opensearch 3章の記述に従う |
| I-102 | 画面仕様(documents 4章)の「注記ブロック」(アイコン+文。`role` なし)は DS 4章に部品の定義がない | `admin/components/note-block/` に置く(3.6)。DS への追記は HO-27 |
| I-103 | DS 4.8 は確認ダイアログを `VDialog` の構成として定義し、部品名がない(admin-view は DLG-1〜5 と呼ぶ) | `ConfirmDialog`・`ConfirmCheck`・`TypeToConfirm` と命名(3.6)。DLG-5 は S2(sources)と J2(jobs)の両方から開くため `dialogs/` に置く(R8) |
| I-104 | (解消済み。前提タスク `create_admin_system_design` の作業記録 0017)B 1.3 と E 5.7 は D1 が EP-14 を使うとしていたが、dashboard 画面仕様に cron のタイムゾーン・Dashboards の URL を使う項目がない(外部リンクはサイドバー。dashboard 3.2) | E 5.4・5.7 と B 1.3 が EP-13 のみに直り、3.9・4.1 の記述(D1 は EP-13 だけ)と一致した |
| I-130 | 作業記録 0004 の X-BD1 は EP-11 の行で「`skipped` の `existence` のみ非 null」としたが、実 OpenAPI では `ExtractFailedDocument`・`SummaryPendingDocument` の `document_id` も非 null(8.1) | **実 OpenAPI を正**とした(3.5)。どの項目を「値があるはず」とするかは FMOD-U-13 |
| I-131 | B 2.11 は `SourceSettings` を EP-02〜04 で共通とするが、実装・OpenAPI では 2 種類(EP-02 の `SourceDetailResponse` は各項目が null 許容、EP-03・04 の `SourceSettings` は厳格) | `fromSettings.ts` は EP-02 の型だけを受ける(3.9)。HO(A 9章に追加) |
| I-132 | v0.1 の E・F は EP-12・13・14 にも最上位の `unavailable` を想定し(0004 の J-E1。B 2.2 への申し送りは HO)、B 8.1・8.2 は EP-12・13・14 のクエリを「エラーなし」とするが、実装・OpenAPI では `unavailable` を持つのは EP-02・10・11 だけで、EP-12・13・14 は未知のクエリを 400 `unknown_field` で拒否する | D1・O1・シェルは `unavailable` を引かず、EP-12・13・14 に query を付けない(3.3・3.5)。HO |
| I-133 | B 2.12 は本文の違反を「すべて返す」とするが、実装は 2 段階(形 → 範囲・桁・排他)で最初の 1 群だけを返す。`ttl_days`・`ttl_seconds` の排他・必須の `field` は両方 `ttl_days` 固定(B 2.4 への申し送りは HO。0004 の S-D4・S-D5) | `fieldMap`・`serverErrors` が TTL 欄に写し、送信後に別の違反が出うる前提にした(3.9。5.3)。HO |
| I-134 | A 2.1・2.2(BAPI-K-2・BAPI-P-2・BAPI-U-1・G3-16・HO-2・HO-36・HO-37)と B 8.1 の `web` の判定・B 10.2 は、`api` が静的配信する前提(`web` を `WEB_DIST_DIR/index.html` の有無で判定)。ユーザー指示(作業記録 0003)で `web` コンテナ(Nginx)が配信する | FMOD-K-4 を更新(8.2)。D1 の `web` タイルは FE の変更なし(3.9)。追従は HO と前提タスク B+C(8.9) |
| I-135 | J1 の状態フィルタ「失敗」: API の `status=failed` にリース切れは含まれない(リース切れは保存上 `running`。「失敗(リース切れ)」の行は `active` でしか出ない。確認 2026-11-26。0004 の J-E7 が画面仕様 jobs 1.5 への追記候補とした) | 画面で補わない(3.9)。画面仕様への追記は HO |
| I-136 | B 1.4 は S1 が `last_completed_at`・`connector_type`(EP-01)を使うとするが、画面仕様に使う項目がない(AF-U-9 が未決。S-E6) | S1 では使わない(要件にない追加をしない。3.9) |
| I-137 | E v0.1・B は `deletion.fetched_at` を取得時刻として扱うが、実装は `queued` 以外で読み取りに失敗したときも「読もうとした時刻」を入れる(J-E10)。EP-10 の `deletion` は `job_type` が読めないときも null になる(J-B3) | 取得失敗時は `fetched_at` を取得時刻として出さない(3.9)。HO |
| I-138 | `openapi_export.py` の docstring は「リポジトリにコミットしない」とするが、FARC-P-6 は OpenAPI JSON と生成コードをコミットする(X-ED2) | 前提タスク A で docstring を直す。本書は「コミットする」(3.3) |

E の I-120(値の読めない `null` の表示)・I-121(`source_missing` の文言)は 3.5・3.9 に反映している(F では再掲しない。ゲート3でユーザー確認済み。2026-11-23)。E の I-88(孤児ロック・取得直後の導線が J2 でなく S2)・I-89(`featureFlag`)は、本書の 3.5・3.7・3.8・5.1・6章に反映している(F では再掲しない。ゲート3でユーザー確認済み。2026-11-23)。E の I-122〜129(v0.2)は E 12.5 に従う。I-139 は予備。

### 8.6 E 12.6「F への引き継ぎ」の割り当て

| E の引き継ぎ(12.6) | 本書での割り当て |
| --- | --- |
| (1) `apps/web/` のディレクトリ構成(生成コード・API ラッパー・key factory と composable・エラー変換表・Router と `meta`・テンプレート 4 型・DS の共通部品・画面ごとのモジュール・テスト・`mockApi`・フィクスチャ) | 2.1(構成)、3.3(生成コード・ラッパー・エラー変換表・正規化・パス値)、3.4(key factory・composable)、3.5・3.7(Router・`meta`・テンプレート)、3.6(DS の共通部品)、3.9(画面ごと)、7章(テスト・`mockApi`・フィクスチャ) |
| (2) 5.7 の表を「画面 → route → ページ → composable → EP」に展開 | 4.1(9 画面+シェル+404)、4.2(操作)、4.3(EP と生成 SDK の名前) |
| (3) DS 4章の全部品の置き場 | 3.6(全件) |
| (4) 依存ルール(ESLint `no-restricted-imports`) | 6章(R1〜R17。生成コードの扱いの注記)。限界は FMOD-U-1 |
| (5) 定義表の置き場(`navGroups`・`documentTabs`・`dashboardComponents`・URL ↔ API・エラー変換表・フォーム `field` 対応) | 3.5(表) |
| (6) トークンと `defaults` を Search View と共有できる置き場 | 2.3・3.1(`shared/theme`) |
| ルート遅延読み込みの判断(`router.onError`) | FMOD-P-17(遅延読み込みしない) |
| `job_id`・`source_id` のパスエンコードをどの層で保証するか(FARC-U-18) | 3.3(FMOD-P-4・FMOD-P-34。`admin/api` の層。確認済みは FMOD-U-2) |
| `unavailable` を引く関数(行の `unavailable`・最上位の `unavailable` の 2 系統。行単位で判定) | 3.5(FMOD-P-14・FMOD-P-33)。最上位の対象は EP-02・10・11 |
| 日時整形の番兵を判定する 1 か所 | 3.5(FMOD-P-15) |
| S4 のフォームモデルのしきい値の丸め注意の状態 | 3.9 の `form/fromSettings.ts`(FMOD-P-16) |
| (v0.2 で増えたもの)実行時エラーの正規化・ステータスの取得(FARC-P-43・44) | 3.3(FMOD-P-34)。方式は E 5.3(`interceptors.error`)。実機確認は FMOD-U-12(E の FARC-U-22) |
| (v0.2 で増えたもの)生成・ビルド設定(FARC-P-45) | 2.4・3.3(生成設定) |
| (v0.2 で増えたもの)DLG-4 の null(FARC-P-46) | 3.8・4.2・5.4 |
| (v0.2 で増えたもの)`web` の Dockerfile・Nginx 設定(FARC-P-20・40・41) | 2.1・2.4 に置き場だけ(中身は E 3.3・3.5。前提タスク B) |

**E の FARC への対応**(本書が置き場を決めたもの): FARC-P-6・7(生成とクライアント)→ 3.3、P-8・9・11・12・25・27(Query)→ 3.4、P-10(ページング)→ 3.5・3.9、P-13・14・15(エラー)→ 3.3・3.8、P-16・28・29(フォーム)→ 3.9、P-17(状態管理)→ 3.2・3.4・3.9、P-18(Router)→ 3.5・3.7・4.1、P-21〜23(テスト・静的解析)→ 6・7章、**P-43・44(Nginx 由来の失敗・正規化)→ 3.3・5.1、P-45(生成・ビルド設定)→ 2.4・3.3、P-46(DLG-4 の null)→ 3.8**。FARC-U のうち、F が引き継ぐのは U-2→FMOD-U-4、U-4・5→FMOD-U-3(解消)、U-9→FMOD-U-6(相対 `baseUrl` は FMOD-U-12)、U-14→FMOD-U-5、U-17→FMOD-U-7、U-18→FMOD-U-2(解消)。

### 8.7 E・B・DS・画面仕様への修正依頼

- **E への修正依頼**: なし。`configureApiClient()` の冪等化は E 4.1・5.3・10.1 に反映済み(確認 2026-11-26)。**E v0.2 の全章と照合済み**(2026-11-26。作業記録 0011 の文書レビューで、契約テスト(`errorTable` ↔ OpenAPI)の置き場(E 10.1)・実 API の接続確認の置き場 `tests/integration/<名前>/`(E 10.2)・lint・format の除外のパス(E 11.1)・FARC-U-22 の一致を確認)。5〜7 章で食い違っていた 3 点(E 5.3)は E に合わせて解消した: (1) 正規化の入口(E は `interceptors.error` に `toApiError` を 1 つ登録。Options・Mutation を包む方式は廃した)、(2) パス値の検証の入口(E は `interceptors.request` が `opts.path` のすべての値を検証し、不正なら合成した 400 `invalid_request`。`isValidPathId` は画面側のガードの純関数として残した)、(3) `baseUrl`(E は設定しない。生成物が `servers` から持つ)。生成物の置き場 `src/admin/api/generated/` は E 5.2 と一致を確認した。**E 4.1 は `configureApiClient()` の呼び出しを追記済み**(確認 2026-11-26)。`web` の Dockerfile・Nginx 設定の置き場(E 3.3・3.5)は、`apps/web/Dockerfile`・`apps/web/nginx/default.conf` で本書の 2.1・2.4 と一致を確認した。
- **B への修正依頼**: なし(B は改訂しない)。実装・OpenAPI との差分(I-131〜133・137 と、B 1.4 の S1 の項目、B 6 章の EP-11 の null 許容、B 7.1 の OpenSearch の状態値、B 8.1・10.2 の `web` の判定)は、HO(A 9章に追加)で申し送る。
- **DS・画面仕様への追記候補**(変更はしない。HO): `PageHeader`・注記ブロック・確認ダイアログの部品名(I-100・102・103。HO-27)、`ShardMatrix` の部品群の名前(I-101)、jobs 1.5 の J1 の状態フィルタ(I-135)、`source_missing` の専用文言(HO-30)、DLG-4 の「記録なし(なしとして実行)」と DLG-5 の「解放するロックがありませんでした」の文言(3.8)。E の I-80〜89・I-122〜129 の追記候補は E に従う。

### 8.8 この文書が決めないこと

- 各部品・composable の内部の実装(Vuetify の props・CSS・アニメーション)。DS・画面仕様に従う。
- Search View のモジュール構成、`search/` の層、同一ビルドにするか(FMOD-U-7)。
- Nginx 設定の最終値(タイムアウト・本文上限・ヘッダ)・`web` の Dockerfile・compose の定義(E 3.3・3.5・11.2。前提タスク B+C の作業)。
- `api` 側の `web` プローブの置換・`api` の公開範囲の変更・結合テストの追従(前提タスク C。API の実装)。
- `tests/integration/<名前>/` のツールと実装(FMOD-U-8)。CI の定義(E 11.2。infra の前提作業)。
- API の導出ロジック(C)、API 側のモジュール構成(D)。

### 8.9 前提タスクへの依存(新設)

前提タスクの内容は冒頭の「前提タスク」のとおり。何が終わるまで何ができないかを示す。

| 作業 | 前提 | 説明 |
| --- | --- | --- |
| フロントの最初のスキャフォールド(`apps/web` の `package.json`・`vite build` が通る最小の構成) | なし | B+C の `web` イメージのビルド(Node 24 系(24.15.0 以上)でビルド → Nginx。E 3.5)は、`package.json` と `vite build` が通ることを前提にする。**B+C は、フロントの最初のスキャフォールドの後に着手できる**(`apps/web` の実装の完了は待たない) |
| 型生成(`gen:api`。`src/admin/api/generated/`)と、それに依存する実装 | **前提タスク A の完了後が望ましい**(必須ではない) | A の前に生成すると `ttl_days`・`ttl_seconds` が `number \| null` になるが、`toRequest` は null を送らない(3.9)ので、A の前でも進められる。A の前に生成したときは、`toRequest` の単体テスト(7.2)で補い、A の後に再生成して差分をレビューする。`openapi_export.py` の docstring の修正も A |
| 開発サーバー(Vite の dev + `/api` プロキシ)での開発 | A・B+C のどちらも不要 | 転送先は dev 専用の環境変数で上書きできる(2.4)。B+C の前は、転送先を現行の compose の `api` の公開ポート(`http://127.0.0.1:8080`)に上書きして着手できる。B+C の後の既定の転送先は `web` の公開ポート(`WEB_HOST_PORT`) |
| D1 の `web` タイルの表示 | B+C の完了後に正しくなる | 現行の API は `web` を `WEB_DIST_DIR/index.html` の有無で判定するため、`web` が別コンテナになる前提では、B+C の前は `web=abnormal` に見える(作業記録 0004 の X-C1。コードの読解)。FE の変更は要らない(3.9) |
| `web` 経由の接続確認(`tests/integration/<名前>/`。7.1) | **前提タスク B+C の完了後** | `web` コンテナ・compose の `web` サービス・`api` の publish の外しと結合テストの上書きが要る |
| `%2F`・`%2E` を含む `job_id` の Nginx 越しの保持(FARC-U-21) | 前提タスク B | Nginx の実機で確認(0005 では未実施) |
| 初回リリース | **前提タスク B+C の完了**(A は望ましい) | `web` 経由の配信と D1 の `web` タイルが B+C に依存する。A は型の修正で、初回リリースを止めない。開発・単体テスト・API モックの E2E は、B+C の前に進められる |

順序の目安: スキャフォールド →(B+C に着手できる)→ (A の完了後が望ましい)型生成 → 実装・単体テスト・E2E(API モック) → (B+C の完了後)`web` 経由の接続確認 → 初回リリース。
