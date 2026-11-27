# 0002 作業プラン

作成日: 2026-11-27 / 工程: プラン作成(planner の報告を保存。**ユーザー承認待ち**)
前提: `0000-requirements-definition.md`、`0001-confirmed-requirements.md`(Q1〜Q3 の回答を含む)

## 1. 目的とゴール

Admin View の MVP(AF-1〜AF-20)を、9画面(D1・S1〜S4・J1・J2・X1・O1)、共通シェル、SPA 内の 404、ダイアログ DLG-1〜5 と削除の再実行で実装する。設計 E v0.2(`ui-admin-frontend-architecture-v0.2.md`)と F v0.2(`ui-admin-frontend-module-structure-v0.2.md`)の構成・依存ルール・テスト方針・品質ゲートに従い、実 Admin API と連携して動く状態にする。

受け入れ基準: 0000 の完了条件 16 項目をすべて満たす(対応表は 11 章)。

## 2. 確定事項・前提

### 確定事項(0001 から)
- Q1: 実機確認と UI レビューは**専用の compose 環境**で行い、全操作を許可する。プロジェクト名を分け、テスト用 `CRAWLER_DOCUMENTS_DIR` を使い、最後に後始末する。他のコンテナは止めない。
- Q2: 実装時確認事項の結果と設計との差異は**作業記録だけ**に書く。設計書は改訂しない。更新するのは `apps/web/README.md` と、古くなる運用文書(`deploy/compose/README.md` など)のみ。
- Q3: アイコンは `@mdi/js` + `vuetify/iconsets/mdi-svg`。
- `gen:api` は 2 段: `uv run python -m loreley_api.admin.openapi_export apps/web/openapi/admin-v1.json` → `openapi-ts`(Hey API 0.99.0、`infiniteQueryOptions: false`)→ `src/admin/api/generated/`。OpenAPI JSON と生成コードはコミット対象。
- 「再生成で差分ゼロ」はローカル npm スクリプト(`gen:api` 後に `git diff --exit-code` と `git status --porcelain` が空)で検査。CI は作らない。
- `tests/integration/<名前>/`(web 経由の実 API スモーク)は作らない。手動の実機確認を作業記録に残す。
- Vitest は jsdom 31。Playwright は Chromium のみ、`page.route` の API モック、未モックの `/api/` は失敗。フィクスチャは共有し生成型で `satisfies`。
- 依存ルール R1〜R17 は ESLint `no-restricted-imports`。表せなければ `eslint-plugin-boundaries` か `dependency-cruiser`(FMOD-U-1)。
- dev サーバーの `/api` 転送先は既定 `http://127.0.0.1:8090`(`LORELEY_DEV_API_TARGET` で上書き。`apps/web/vite.config.ts:11` 実装済み)。
- ライブラリの版は E 2.1 の固定方針。設計にないライブラリは足さない。
- コミット・PR はユーザーの指示があるまで行わない。

### 本プランで置く仮定
- **比較基準 SHA**: フェーズ 1 開始時に `git rev-parse HEAD` を記録(想定 `8a20d67`)。コミットしないため差分は累積する。各フェーズの作業記録に「追加・変更ファイル一覧」を書き、レビュー範囲はその一覧で示す。
- **Node**: ローカルは 24.15.0 以上の 24 系(`.nvmrc`)。範囲外なら nvm か `docker run node:24` で検証。Playwright はホストの Node で動かす。
- **Playwright `webServer`**: `npm run dev`(`http://localhost:5173/admin/`、`reuseExistingServer: true`)。`vite preview` 案は CI スコープ外のため採らない。
- **画面の順序**: E 12.8「スキャフォールド → 型生成 → 実装・単体・E2E → web 経由確認」。テンプレート検証を兼ねて読み取り専用の D1・O1 → S1/S2 と操作 → S3/S4 → J1/J2 と操作 → X1。
- **テスト**: 画面ごとのテストはその画面のフェーズで書く。横断 E2E と網羅点検はフェーズ 9。
- **ルート**: すべて同期 import(FMOD-P-17)。サイズは実装後に測り FMOD-U-11 として記録。
- **`data-testid`**: DS 9 と画面仕様の名前のみ。新規に作らない。
- **X1「要約未生成」タブ**: 実データでは出ないのでモック(Vitest・E2E)で検証。
- **AF-20(Dashboards 外部リンク)**: 実機では scratchpad に置いた compose 上書きファイルで `LORELEY_API_DASHBOARDS_URL` を与える(`deploy/compose/compose.yaml` は変更しない)。

## 3. 影響範囲

| 区分 | パス | 内容 |
| --- | --- | --- |
| 依存・スクリプト | `apps/web/package.json:9-29`、`package-lock.json` | E 2.1 の依存追加(`@tanstack/vue-query`・`@hey-api/openapi-ts` 0.99.0 exact・Vitest・jsdom 31・`@vue/test-utils`・`@playwright/test` 1.65.1 exact・ESLint 系・Prettier)。スクリプトは E 11.1(`lint`・`format`・`format:check`・`test`・`test:e2e`・`gen:api`)と差分ゼロ検査(例 `gen:api:check`) |
| 設定 | `vite.config.ts`(Vitest 追加)、`tsconfig*.json`、新規 `eslint.config.js`・`.prettierrc`・`.prettierignore`・`openapi-ts.config.ts`・`playwright.config.ts`、`.gitignore` | F 2.4 |
| 生成物 | 新規 `apps/web/openapi/admin-v1.json`、`src/admin/api/generated/**` | 手編集しない |
| ソース | `src/main.ts`(作り直し)、`src/admin/app/App.vue`、`src/admin/router/index.ts`(作り直し。`PlaceholderPage.vue` 削除)、`src/shared/theme/settings.scss`、新規 `src/shared/**`・`src/admin/**`(F 2.1) | |
| テスト | 新規 `src/**/*.test.ts`・`*.contract.test.ts`、`apps/web/tests/support/**`・`tests/e2e/**` | |
| Docker | `apps/web/Dockerfile:35-36` の `COPY` | ビルドに要るファイルが増えたら追記 |
| Nginx | `apps/web/nginx/default.conf` | 原則変更しない。不具合時のみユーザー確認のうえ修正 |
| 文書 | `apps/web/README.md`(全面更新)、`deploy/compose/README.md`(古い記述のみ) | 設計書は変更しない(Q2) |
| 対象外 | `apps/api`・`apps/crawler`・`apps/indexer`・`deploy/compose/compose.yaml`・`docs/**` | 不具合は 9 章のユーザー確認点として扱う |

## 4. 実装フェーズ

共通ルール: 実装は `code-implementer`、レビューは別エージェント。作業記録はフェーズ終了時に 1 本(メインエージェントが書く。変更ファイル一覧・検証コマンドと結果・実装時確認事項の結果・設計との差異・未対応事項を含む)。`STATUS.md` も同時更新。検証コマンドは `apps/web/` で実行。

### フェーズ 1: ツールチェーン・型生成・テスト基盤の土台
- **目的**: 全フェーズが依存する依存関係・生成・静的解析・テスト環境を作り、方式に関わる未確認事項(FARC-U-9・25、FMOD-U-1)を最初に潰す。
- **作業**:
  1. E 2.1 の版で依存追加。`npm ci` の peer・engines・deprecated 警告と `npm audit` を確認(FARC-U-25)。
  2. `openapi-ts.config.ts`、`gen:api` 2 段スクリプト、差分ゼロ検査スクリプト。`openapi/admin-v1.json` と `generated/` を生成。
  3. `eslint.config.js`(flat config。`eslint-plugin-vue`・`typescript-eslint`・Prettier 衝突無効化)。R1〜R17 の `no-restricted-imports`。`tests/**`・`*.test.ts` には R2・R3 の一部のみ(F 6 章)。`.prettierrc`・`.prettierignore`(`generated/`・`dist/`・`openapi/admin-v1.json` 除外)。
  4. Vitest(jsdom、`test.server.deps.inline: ['vuetify']`)、`tests/support/setup.ts` 骨格(`ResizeObserver` モック、TZ=`Asia/Tokyo`)、`mount.ts`(createVuetify + VLayout + Router + QueryClient(`retry: false`))。
  5. **方式確認スパイク**(結果を作業記録へ。スパイクのテストは本実装に置換か削除): jsdom で `VDataTableServer`・`VDialog`・`VNavigationDrawer` がマウントできるか(FARC-U-9)/ 相対 `baseUrl` の `Request` が jsdom で解決されるか(FARC-U-9、FMOD-U-12)/ R1〜R17 が `no-restricted-imports` で表せるか(違反を書いて lint が落ちることを確認。FMOD-U-1)。
  6. Playwright 設定(`baseURL=http://localhost:5173/admin/`、`timezoneId=Asia/Tokyo`、Chromium のみ)と起動確認スモーク spec。
  7. 生成物などを型検査対象に含めて Docker ビルドが壊れないか確認、必要なら `Dockerfile` の `COPY` 更新。
- **成果物**: 設定一式、`openapi/admin-v1.json`、`generated/`、`tests/support/` 骨格。
- **検証**:
  ```sh
  npm ci && npm audit
  npm run gen:api && git diff --exit-code && test -z "$(git status --porcelain apps/web/openapi apps/web/src/admin/api/generated)"
  npm run gen:api:check
  npm run typecheck
  npm run lint            # 依存ルール違反サンプルで落ちることも確認
  npm run format:check
  npm run test
  npm run build
  npx playwright install chromium && npm run test:e2e
  docker build -t loreley-web-check apps/web   # リポジトリルートで実行
  ```
  (最初のコミット前は新規ファイルとして出るため、2 回目の生成で差分が出ないことを確かめる)
- **エージェント**: `code-implementer`
- **レビュー**: `code-reviewer`(設定・依存ルール・生成スクリプト)と `test-reviewer`(テスト基盤)を並列
- **完了条件**: 検証が全て成功。FARC-U-9・25、FMOD-U-1 の結果を記録。方式が変わる場合はユーザー回答済み。
- **ユーザー確認点**: jsdom で Vuetify が動かず Browser Mode へ変更(FARC-U-9)/ `no-restricted-imports` で表せず `eslint-plugin-boundaries` か `dependency-cruiser` 追加(FMOD-U-1)/ `npm audit` で E 2.1 と違う版が必要。

### フェーズ 2: データ取得層と純粋ロジック(層 0〜2 の非 UI)
- **依存**: フェーズ 1
- **目的**: API の入口・エラー正規化・Query 層・純関数を作り、契約テストで生成コードと実 API の一致を担保する。
- **作業**:
  - `shared/api/apiError.ts`、`shared/lib/{datetime,number}.ts`
  - `admin/api`: `client.ts`(冪等な `configureApiClient`。自前 `AbortController` によるタイムアウト付き fetch、本文受信完了まで対象。`AbortSignal.any` は使わない。interceptor は 2 つ)、`pathParams.ts`、`errors/{toApiError,errorTable,describeError}.ts`、`index.ts`(`{Op}Response2` は再 export しない)
  - `admin/queries`: `keys.ts`・`withKey.ts`・`queryClient.ts`・`polling.ts`・`placeholder.ts`・`invalidation.ts`、EP ごとの読み取り composable(meta・dashboard・sources・jobs・documents・opensearch)、`mutations/`(EP-03〜08)
  - `admin/lib`: `unavailable`・`expectedFields`・`leaseExpiry`・`existingJob`・`clusterValues`・`routeNames`・`actions`・`units`・`lockStateView`・`viewState`・`injectionKeys`・`validation/`
  - `admin/composables`: `useListParams`・`useDebouncedRef`・`useDocumentTitle`・`useViewState`
  - テスト支援: `tests/support/fetchStub.ts`・`apiErrors.ts`・`fixtures/`(EP・状態ごと。F 7.3)・`mockApi.ts`
  - テスト: E 10.1 / F 7.2 の該当行。エラー変換表の全 20 code、`toApiError` の全行(`AbortError`/`TimeoutError` 区別)、**契約テスト** `errorTable.contract.test.ts`・`pathParams.contract.test.ts`、`configureApiClient` の冪等性と `baseUrl`、EP-12・13・14 に query が付かないこと、本文受信停止で時間切れ、key factory・polling・invalidation・`enabled: false`、lib 純関数(丸め境界値・9 桁・`cellState`・lockState 7 値 + 取得失敗の写像)
  - 実装時確認: FARC-U-22 (1)〜(6)、FMOD-U-12、FMOD-U-9(`.`・`..` の ID。ブラウザ正規化は E2E で後追い)、FMOD-U-13、FARC-U-26 (4)
- **検証**: `npm run typecheck && npm run lint && npm run format:check && npm run test`
- **エージェント**: `code-implementer`
- **レビュー**: `code-reviewer`(破壊的操作の mutation と「結果不明」判定を含むため省略しない)と `test-reviewer` を並列
- **完了条件**: テスト全成功。FARC-U-22、FMOD-U-12・13 の結果を記録。
- **ユーザー確認点**: `withKey` をやめ独自 Options へ切替(FARC-U-22 (6))/ `TimeoutError`・`AbortError` の扱いが E 5.3 と食い違う。

### フェーズ 3: テーマ・共通 UI・シェル・ルーティング・アプリ組み立て
- **依存**: フェーズ 2
- **目的**: DS 準拠の土台、テンプレート 4 型、シェル、全 route を用意。
- **作業**:
  - `shared/theme`: `tokens.ts`・`defaults.ts`・`display.ts`・`icons.ts`・`settings.scss`・`global.css`(DS 2・3)
  - `shared/ui`: `StatusTag`+`statusMaps`、`StateBlock`・`PageAlert`・`FormField`・`ErrorSummary`・`AppSnackbar`・`useSnackbar`・`TopProgress`・`IdText`・`TimeText`
  - 複数画面共通の `admin/components`: `data-table/`・`key-value-list/`・`confirm-dialog/`(`ConfirmDialog`・`ConfirmCheck`・`TypeToConfirm`・`dialogLevel`)・`stat-list/`・`warning-list/`・`filter-bar/`・`note-block/`(画面固有部品は各画面フェーズ)
  - `admin/templates`(`ListPage`・`DetailPage`・`FormPage`・`DashboardPage`・`PageHeader`・`PageBreadcrumbs`・`PageActions`)
  - `useBreadcrumbs`・`useContainerWidth`
  - `admin/shell`(`AppShell`・`SideNav`・`MobileAppBar`・`SkipLink`・`ExternalLinks`・`externalLinks.ts`)
  - `admin/dialogs/useOperationDialog.ts`
  - `admin/router`(`routes.ts` に admin-view 4.2 の全 route を最小スタブページで置き、各画面フェーズで差替え。`navGroups`・`guards`(afterEach のタイトル更新とフォーカス移動)・`scroll`・`meta.d.ts`・`NotFoundPage.vue`)
  - `admin/app`(`setupVuetify`・`setupQuery`・`setupRouter`・`App.vue`)、`main.ts`(E 4.1 の順)。`PlaceholderPage.vue` 削除
  - テスト: `StatusTag` 未登録警告、`ConfirmDialog` の有効・無効と理由、`StateBlock`、`useBreadcrumbs`、ナビの抽出と並び。E2E `shell.spec.ts`(ナビ、840px 境のサイドバー、SPA 内 404、遷移後 `h1` フォーカスとタイトル、スキップリンク、外部リンク領域の表示・非表示)
  - 実装時確認: FMOD-U-4、FMOD-U-10、FARC-U-2・14 の一部、FARC-U-8
- **検証**: `npm run typecheck && npm run lint && npm run format:check && npm run test && npm run build && npm run test:e2e`
- **エージェント**: `code-implementer`
- **レビュー**: `code-reviewer`・`test-reviewer` 並列。`web-ui-reviewer` はフェーズ 4 の後にまとめる(画面がスタブのため)
- **完了条件**: 検証成功。全 route が開き 404 が描画される。

### フェーズ 4: D1 ダッシュボード・O1 OpenSearch ダッシュボード(読み取り専用)
- **依存**: フェーズ 3
- **作業**:
  - `features/dashboard`: ページ、`useDashboardPage`、`dashboardViewModel`(取得失敗時の降格)、`dashboardComponents.ts`、`dashboard-parts/`(`SummaryBand`・`ComponentTile`)、`auto-refresh-switch/`。30 秒ポーリングを手動更新・オン/オフで切替
  - `features/opensearch`: ページ、`useOpenSearchPage`、`opensearchParams`(`replace`)、`indexFilter`、`matrixModel`、`shard-matrix/`(`columnsPerPage` 含む)
  - テスト: 降格・フィルタ・行列モデル・列数の単体。E2E: D1(正常・異常・stale 降格・時計によるポーリング)、O1(絞り込み URL 同期・stale・`truncated`・未知の状態値)
  - 実装時確認: FMOD-U-6
- **検証**: フェーズ 3 と同じ一式
- **エージェント**: `code-implementer`
- **レビュー**: `code-reviewer`・`test-reviewer` 並列。**`web-ui-reviewer`(中間)**: シェル・テンプレート・テーマが DS とモック(`mockups/admin-dashboard-v0.1.html`・`admin-opensearch-v0.1.html`・`design-system-v0.1.html`)に合っているか早期確認。起動準備はメインエージェント: 5 章の専用 compose 環境を起動し `LORELEY_DEV_API_TARGET=http://127.0.0.1:<専用WEB_PORT> npm run dev`(「dev → web → api」確認を兼ねる)。対象 URL `http://localhost:5173/admin/`(D1・O1・シェル・404)。変更操作は不要。
- **完了条件**: 検証成功。中間 UI レビューの Critical・Important が解消。

### フェーズ 5: S1 一覧・S2 詳細と関連操作ダイアログ
- **依存**: フェーズ 4
- **作業**:
  - `features/sources`: S1(`SourcesTable`・`sourceRow`・`SourceRowActions`)、S2(`SourceSettingsCard`・`LockStateCard`・`LastJobCard`・`IndexCard`)、`sourceActions.ts`(`status=null` のとき操作を出さない)
  - ダイアログ: `dialogs/crawl-start/`(DLG-1。標準/警告つき、`refusal.ts`、`lock_held` variant、`canLinkToJob`)、`source-delete/`(DLG-2 要入力確認、削除の再実行含む)、`lock-release/`(DLG-5。S2 孤児ロック版と J2 リース切れ版の `variant`、`released=false` の扱い)
  - 各操作: 確認ダイアログ・操作可能条件・二重送信防止・結果表示(スナックバーとダイアログ内アラート)・invalidate 再取得・結果不明時の導線
  - テスト: `sourceActions` 全組合せ、`sourceRow`、`refusal`、`useOperationDialog`。E2E: S1 → DLG-1(受付・`lock_held` 拒否・指定が反映されなかった通知・メンテナンス中拒否)、DLG-2(入力確認・202 後 S2 のロック状態が `held_delete`)、削除の再実行、DLG-5(`released=true`/`false`)、書込の結果不明(HTML の 502・504・通信断で再試行を出さない)、ダイアログのフォーカス閉じ込めと復帰
  - 実装時確認: FMOD-U-5
- **検証**: フェーズ 3 と同じ一式
- **エージェント**: `code-implementer`
- **レビュー**: `code-reviewer`(**必須**。削除・ロック解放)と `test-reviewer` 並列
- **完了条件**: 検証成功。AF-3・6・7・16・19 の S1/S2 側を E2E で確認。

### フェーズ 6: S3 登録・S4 編集
- **依存**: フェーズ 5
- **作業**:
  - `features/sources/form/`: `connectors/fileSystem.ts`・`sourceFormModel`・`fromSettings`(TTL モード・丸め注意・`malformed`)・`toRequest`・`rules`・`fieldMap`・`serverErrors`・`useSourceForm`
  - `form-parts/`(`PatternListInput`・`SettingSwitch`・`FormDisclosure`)、`SourceForm`・`SourceFormAlerts`
  - S3・S4 ページ。S4 は `sourceId` で `:key`。取得できなければフォームを出さない。cron タイムゾーンは EP-14 の値(UC-19)
  - テスト: `toRequest`(使わない側 `ttl_*` がキーごと無い、日・秒両モード、S4 に `source_id`・`connector_type` を含めない、`connector_config` は 5 項目を常に送る)、`fromSettings`、`fieldMap`・`serverErrors` 全ケース、**S4 の ID 切替コンポーネントテスト**、`PatternListInput`。E2E: S3 `config_invalid` の項目別表示と上部アラート、S3 成功→S2 遷移、S4 取得失敗でフォームを出さない、保存系の結果不明で「もう一度保存」
  - 実装時確認: FARC-U-13
- **検証**: フェーズ 3 と同じ一式
- **エージェント**: `code-implementer`
- **レビュー**: `code-reviewer`・`test-reviewer` 並列(設定全置換の更新操作)
- **完了条件**: 検証成功。AF-1・2 を E2E で確認。
- **ユーザー確認点**: FARC-U-13 で設計にない表示・挙動を決める必要が出たとき。

### フェーズ 7: J1 一覧・J2 詳細と関連操作ダイアログ
- **依存**: フェーズ 5(DLG-5・削除再実行ダイアログ)
- **作業**:
  - `features/jobs`: J1(`FilterBar`・`JobsTable`(`AdminDataTableServer`・列はカード幅で省略)・`jobsParams`・`isPlaceholderData` の間は取消を無効)、J2(`JobSummaryCard`・`FailureAlert`・`WarningList`・`RegistrationCard`・`DeletionCard`・`LockCard`・10 秒ポーリングと終了時停止)、`jobActions.ts`、`catalogs/`、`JobStatusCell`
  - ダイアログ: `job-cancel/`(DLG-3。`job_already_finished` は成功扱い)、`job-rerun/`(DLG-4。null は false で送り「記録なし」と表示。成功したら新ジョブ J2 へ)
  - テスト: `jobActions` 全組合せ(`source_missing`・null フラグ含む)、`catalogs` 型ガード、J1 行の取消無効のコンポーネントテスト。E2E: J1 ページングと絞込 URL 同期・J2 ポーリング停止・DLG-3・DLG-4・J2 からの DLG-5(リース切れ版)と削除再実行・`stalled=true` かつ `lease_expires_at=null` の表示・`status=null` のジョブ
  - 実装時確認: FARC-U-2、FMOD-U-9 の E2E 側(`/jobs/.`・`/jobs/..` の正規化)
- **検証**: フェーズ 3 と同じ一式
- **エージェント**: `code-implementer`
- **レビュー**: `code-reviewer`(**必須**。取消・再実行・ロック解放)と `test-reviewer` 並列
- **完了条件**: 検証成功。AF-4・5・7・8・9・10 を E2E で確認。

### フェーズ 8: X1 文書確認ビュー
- **依存**: フェーズ 3(直列で実施。ファイル衝突回避)
- **作業**: `features/documents`(`documentsParams`・`documentTabs`(4 行型とアダプタ)・`columns`・`SourceSelect`(削除中は選べない)・`DocumentsTable`・`NoSourceState`)、`count-tabs/`。`tab_counts` の保持、タブごと独立エラー表示、`existence`、`document_count`(AF-15)。テスト: 行型アダプタ・kebab↔snake・タブ件数の単体、E2E(タブ URL 同期・未選択状態・1 タブのみ失敗・要約未生成タブ・タブ移動時スクロール)
- **検証**: フェーズ 3 と同じ一式
- **エージェント**: `code-implementer`
- **レビュー**: `code-reviewer`・`test-reviewer` 並列
- **完了条件**: 検証成功。AF-11〜15 を E2E で確認。

### フェーズ 9: 横断 E2E・テスト網羅点検・品質ゲート通し
- **依存**: フェーズ 4〜8
- **作業**: 横断 E2E(全画面で同一オリジン以外への要求 0 件 / 375・768・840・1024・1280px で横スクロールなし / a11y 振る舞い(`aria-sort`・ダイアログ・フォーカス)の漏れ確認)。E 10.1・10.2 と F 7.2 の表を 1 行ずつテストの所在に対応させた**網羅表**(AF 列も設ける)を作り作業記録に載せ、不足は追加。品質ゲート(E 11.2 の 0〜7)通し。ビルドサイズ測定(FMOD-U-11)。依存ルール最終確認(違反サンプルで lint 失敗を再確認)。FARC-U-20(`vite-plugin-vuetify` と Vite 8)。
- **検証**: `npm ci && npm run gen:api:check && npm run typecheck && npm run lint && npm run format:check && npm run test && npm run build && npm run test:e2e`
- **エージェント**: `code-implementer`(テスト追加。網羅表下書きも)
- **レビュー**: `test-reviewer`(網羅表・テスト全体)と `code-reviewer`(変更分)並列
- **完了条件**: 品質ゲート全成功。網羅表に空きなし(実装不可は理由記載)。
- **ユーザー確認点**: FMOD-U-11 の実測でルート遅延読み込みへ切替が必要なとき。

### フェーズ 10: Docker ビルド・実機確認・最終 UI レビュー
- **依存**: フェーズ 9
- **作業**(メインエージェントが環境用意・確認、不具合修正は `code-implementer`):
  1. `docker build` で web イメージのビルド確認(FARC-U-26 (1))
  2. 専用 compose 環境起動(5 章)。`http://127.0.0.1:<専用WEB_PORT>/admin/` で全画面表示、直開き・再読込で SPA が返ること
  3. 実 API で代表操作を通し: 登録(S3)→ 編集(S4)→ クロール起動(DLG-1。強制削除・再書込指定含む)→ J2 ポーリング → 取消(DLG-3)→ 失敗ジョブの再実行(DLG-4。作れた場合)→ ロック解放(DLG-5。孤児ロックかリース切れを作れた場合)→ X1 → O1 → D1 → 削除(DLG-2)・削除再実行
  4. dev サーバー(`LORELEY_DEV_API_TARGET`)から web 経由で API が使えること
  5. AF-20: 上書きファイルで `LORELEY_API_DASHBOARDS_URL` を与え外部リンク表示確認
  6. 実装時確認(結果表にまとめる): FARC-U-16(読 45 秒・書 90 秒の仮値と Nginx `proxy_read_timeout` の実測。測れなければ理由)、FARC-U-23、FARC-U-24(作れなければ未確認)、FARC-U-26 (2)(3)、FARC-U-15(Playwright の Firefox・WebKit で最小限。指定版で確認できなければ「未確認」)、FARC-U-14・FMOD-U-5(web-ui-reviewer と分担)
  7. **`web-ui-reviewer`(最終)**: 全画面・全ダイアログを UI 設計書・DS・モックと比較。幅 5 種のレスポンシブとアクセシビリティ。依頼に含める: 対象 URL(専用 web ポートの `/admin/`)、確認画面・フロー(全 9 画面・404・DLG-1〜5・削除再実行)、変更操作は**可**(専用環境、テストデータはこのプロジェクト名の環境内のデータソースすべて。Q1)。実データで出せない状態(要約未生成・部分失敗・結果不明)は E2E スクリーンショットかモック起動の dev サーバーで補う。
  8. 後始末(5 章)
- **レビュー**: `web-ui-reviewer`(最終)。修正が出たらその差分に `code-reviewer`・`test-reviewer`
- **完了条件**: 実機確認結果(手順・結果・スクリーンショット所在)記録。UI レビューの Critical・Important 解消。後始末完了。
- **ユーザー確認点**: Admin API・Nginx・compose の不具合修正が必要になったとき。

### フェーズ 11: ドキュメント整備と申し送り
- **依存**: フェーズ 10
- **作業**: `apps/web/README.md` 全面更新(開発・ビルド・`gen:api` と差分ゼロ検査・品質ゲート順・Vitest・Playwright(ブラウザ導入含む)・dev サーバー転送先・Docker ビルド・ディレクトリ構成概要)。`deploy/compose/README.md` 等の古くなった記述のみ修正。作業記録に「実装時確認事項の結果一覧(全 ID)」「設計との差異一覧」「設計書追従改訂の申し送り(別タスク起票用。FARC-U・FMOD-U の状態更新、I-n 追記候補、HO 追加)」をまとめる。
- **エージェント**: `document-writer`(README・運用文書)。差異・申し送りのまとめはメインエージェント。
- **レビュー**: `document-reviewer`
- **完了条件**: README の手順を実際に再実行(少なくとも `npm ci` から `test:e2e`、`gen:api:check`)。`document-reviewer` の Critical・Important 解消。

### フェーズ 12: タスクレビュー(8 章)

## 5. 実機確認の環境(フェーズ 4・10 共通)

- **プロジェクト名**: `loreley-adminview`(既存の `compose`・`loreley-it` とは別)
- **ホストポート**: 既存環境や IT(9200・8000・8001・8090・8080)と衝突しないよう上書き。例 `OPENSEARCH_HOST_PORT=19200`、`INDEXER_HOST_PORT=18000`、`WEB_HOST_PORT=18090`。事前に空きを確認し作業記録に記載。
- **データ**: `CRAWLER_DOCUMENTS_DIR` を scratchpad の専用ディレクトリ(テスト文書数件。抽出失敗・サイズ超過・スキップ用ファイル含む)に。Docker Desktop のファイル共有対象であることを確認。
- **起動例**: `docker compose -p loreley-adminview -f deploy/compose/compose.yaml [-f <scratchpad>/override.yaml] up -d --build`(上書きファイルは AF-20 用の `LORELEY_API_DASHBOARDS_URL` のみ。リポジトリには置かない)
- **後始末**: `docker compose -p loreley-adminview -f deploy/compose/compose.yaml down -v`。**プロジェクト名を必ず指定**。他プロジェクトのコンテナ・ボリュームには触れない。テスト文書ディレクトリを削除。
- **9200 衝突**: ポートを上書きするので通常は起きない。衝突しても他コンテナは止めず、ポート変更かユーザー報告。

## 6. レビューフェーズ(まとめ)

| フェーズ | code-reviewer | test-reviewer | web-ui-reviewer | document-reviewer |
| --- | --- | --- | --- | --- |
| 1 基盤 | ○ | ○ | 省略(画面なし) | — |
| 2 データ取得層 | ○(破壊的操作の mutation 含む) | ○ | 省略(UI なし) | — |
| 3 共通UI・シェル | ○ | ○ | フェーズ4後にまとめる(画面スタブ) | — |
| 4 D1・O1 | ○ | ○ | ○(中間) | — |
| 5 S1・S2・DLG-1/2/5 | ○(**必須**) | ○ | フェーズ10でまとめる | — |
| 6 S3・S4 | ○ | ○ | フェーズ10でまとめる | — |
| 7 J1・J2・DLG-3/4 | ○(**必須**) | ○ | フェーズ10でまとめる | — |
| 8 X1 | ○ | ○ | フェーズ10でまとめる | — |
| 9 横断テスト | ○(変更分) | ○(網羅表) | — | — |
| 10 実機確認 | 修正時 ○ | 修正時 ○ | ○(最終・全画面) | — |
| 11 文書 | — | — | — | ○ |

- フェーズ 5〜8 の UI レビューをフェーズ 10 にまとめる理由: 共通部品の DS 準拠はフェーズ 4 の中間レビューで固め、各画面は実データ・実操作でまとめて確認する方が環境コストに見合う。
- レビュー依頼に必ず含める: タスク名、対象ファイル一覧(そのフェーズの作業記録の変更ファイル一覧)、比較基準(フェーズ 1 開始時 SHA。差分は累積するので対象は一覧で絞る)、参照文書(`0000`・`0001`・本プラン・当該作業記録)と設計書の関係節。
- `code-reviewer` と `test-reviewer` は独立なので並列実行。

## 7. レビュー指摘への対応

- Critical・Important: `code-implementer` が修正し同じレビュアーで再レビュー。解消まで次フェーズに進まない。
- Suggestion・Nitpick: メインエージェントが判断し、判断と理由を作業記録へ。見送りは未対応事項に載せる。
- 指摘が設計書と食い違う場合: 設計書は変えない(Q2)。仕様変更・重要判断を伴うならユーザー確認し、作業記録と申し送りに記録。

## 8. タスクレビューフェーズ

- **実施する**。理由: 実装フェーズが 11 あり複数セッションにまたがる。削除・ロック解放など破壊的操作を含む。
- 順序: フェーズ 11 の `document-reviewer` 対応と作業記録作成後(作業記録も確認対象)。
- 担当: `task-reviewer`。渡す文脈はタスク名(`agent_tasks/20261127_implement_admin_view/` 配下すべて)と比較基準 SHA。要件定義・プラン・作業記録・実変更を突き合わせ、11 章の対応表が満たされているか確認。コード/テスト単体品質は前段で見るため重ねない。
- 指摘対応: Critical・Important は該当フェーズへ差し戻し修正(必要なら前段レビューもやり直し)、`task-reviewer` で再レビュー。解消までタスクを完了にしない。

## 9. ユーザー確認が必要になりうる箇所

| フェーズ | 内容 |
| --- | --- |
| 1 | jsdom→Browser Mode(FARC-U-9)/ 依存ルール検査ツール追加(FMOD-U-1)/ `npm audit` で版変更 |
| 2 | `withKey`→独自 Options(FARC-U-22 (6))/ タイムアウト・キャンセル方式が E 5.3 と変わる |
| 6 | FARC-U-13 で設計にない挙動を決める |
| 9 | FMOD-U-11 実測でルート遅延読込へ切替 |
| 10 | Admin API・Nginx・compose の不具合修正(スコープ外変更) |
| 全般 | 設計書間/設計と実 API の不整合で仕様判断が必要なとき。E 2.1 にない版・ライブラリが必要なとき |

ユーザー確認が要る間、メインエージェントは `STATUS.md` を `blocked` にし、質問を「ユーザー判断待ち」に書いて中断する。

## 10. テスト方針

- **Vitest**(jsdom 31): 純粋ロジック(エラー変換表の全 20 code、`toApiError` 全行、パス値、URL↔条件、polling、検証・単位・丸め、操作表、行モデル、`toRequest`・`fromSettings`・`fieldMap`)、composable、コンポーネントの props と状態出し分け。QueryClient はテストごとに作り直し、`fetch` だけ差替えて生成クライアントを通す。MSW は使わない。
- **契約テスト**: `errorTable` と OpenAPI description(16 code)、実際に送られる URL(エンコード・拒否・`.` を含むだけの値は通す)、EP-12・13・14 に query が付かないこと。
- **生成の一致**: `gen:api:check` で OpenAPI と生成コードが実 Admin API 実装と一致することを担保。
- **Playwright**(Chromium、API モック): フロー、全状態(読込中・空・エラー・stale・見つからない・部分失敗)、URL 同期、ポーリング(時計操作)、書込の結果不明、ダイアログ a11y、SPA 内 404、外部要求 0 件、幅 5 種。未モックの `/api/` は失敗。
- **異常系・境界値・状態遷移**: F 7.3 のフィクスチャ状態を全て用意し F 7.2 の各行に対応(フェーズ 9 の網羅表)。
- **実機確認**: フェーズ 10(手動、作業記録に残す)。

## 11. 0000 完了条件との対応表

| # | 完了条件 | フェーズ | 確認方法 |
| --- | --- | --- | --- |
| 1 | 実装基盤と共通 UI | 1・2・3 | 各フェーズ検証とレビュー |
| 2 | 全 9 画面 | 4(D1・O1)・5(S1・S2)・6(S3・S4)・7(J1・J2)・8(X1) | E2E と実機確認(10) |
| 3 | MVP 管理機能(AF-1〜20) | 5〜8、10 | AF ごとの E2E 対応(網羅表の AF 列)と実機通し操作 |
| 4 | 正常・異常・部分失敗が設計準拠 | 2・4〜8・9 | Vitest・E2E、`test-reviewer` |
| 5 | UI 設計・DS 準拠 | 3・4・10 | `web-ui-reviewer`(中間・最終) |
| 6 | レスポンシブ・a11y | 3・9・10 | E2E と `web-ui-reviewer` |
| 7 | モジュール構成・依存ルール | 1・全フェーズ(lint)・9 | `npm run lint`、違反サンプル、`code-reviewer` |
| 8 | 再生成で差分なし | 1・9 | `npm run gen:api:check` |
| 9 | 単体・契約・E2E 全成功 | 2〜9 | `npm run test`・`test:e2e`、網羅表 |
| 10 | 型検査・Lint・フォーマット・ビルド | 全フェーズ・9 | 品質ゲート通し |
| 11 | web Docker イメージビルド | 1・10 | `docker build` |
| 12 | compose で実 API 連携 | 10 | 実機確認記録 |
| 13 | dev サーバーで API 連携 | 4・10 | `LORELEY_DEV_API_TARGET` 確認 |
| 14 | コード・テスト・UI・タスクレビュー完了 | 1〜10・12 | 各レビュー結果の記録 |
| 15 | README と関連文書 | 11 | `document-reviewer` と手順再実行 |
| 16 | 実装時確認事項の結果・未対応の理由と方針 | 各フェーズ・11 | 12 章の全 ID に結果がある |

## 12. 実装時確認事項の割り当て

| ID | フェーズ | ID | フェーズ |
| --- | --- | --- | --- |
| FARC-U-25 | 1 | FARC-U-9・FMOD-U-1 | 1(スパイク) |
| FARC-U-22・FMOD-U-12 | 2 | FMOD-U-13・FARC-U-26 (4) | 2 |
| FMOD-U-9 | 2(純関数)・7(E2E) | FMOD-U-4・10、FARC-U-8 | 3 |
| FARC-U-2 | 3・7 | FARC-U-14・FMOD-U-5 | 3・5、最終 10 |
| FMOD-U-6 | 4 | FARC-U-13 | 6 |
| FMOD-U-11・FARC-U-20 | 9 | FARC-U-15・16・23・24、FARC-U-26 (1)〜(3) | 10 |

確認できなかったものは「未確認」と理由・今後の方針を書き、フェーズ 11 の申し送りに入れる。

## 13. リスクと対策

| リスク | 対策 |
| --- | --- |
| jsdom で Vuetify が動かない(FARC-U-9) | フェーズ 1 スパイクで早期検出。替えるならユーザー確認 |
| `withKey` が Hey API 内部実装に依存して壊れる(FARC-U-22) | フェーズ 2 で確認。切替案は設計にあるのでユーザー確認のうえ切替 |
| 依存ルールが ESLint で表せない(FMOD-U-1) | フェーズ 1 で確認。代替ツール追加はユーザー確認 |
| 差分が累積しレビュー範囲がぼやける(コミットしない) | 作業記録の変更ファイル一覧で範囲明示。必要なら途中コミットをユーザーに提案(実施は指示があったとき) |
| Docker ビルドの `COPY` 漏れ | フェーズ 1・10 で `docker build`。追加ファイルが出たら `Dockerfile:35-36` 更新 |
| 実データで出せない状態(要約未生成・`stalled=true`・`status=null`) | モックで検証、実機は「未確認」と記録 |
| 実機確認でポート衝突・他環境破壊 | プロジェクト名とホストポートを分離。`down -v` は必ず `-p loreley-adminview`。他コンテナは止めない |
| ローカル Node が範囲外 | `.nvmrc` に切替か `docker run node:24` |
| 規模が大きくセッションをまたぐ | フェーズごとに作業記録と `STATUS.md` を更新。各フェーズは単独検証可能 |
| Admin API・Nginx の不具合発見 | スコープ外のため影響範囲を整理してユーザー確認 |
| ロールバック | コミット前のため `git stash` または比較基準 SHA へ `git checkout -- apps/web` と新規ファイル削除。実機環境は `down -v` |

## 14. 未解決事項

- なし(方式に関わる未確認事項は 12 章の割り当てとユーザー確認点で扱う)。
