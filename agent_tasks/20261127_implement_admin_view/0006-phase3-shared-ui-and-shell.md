# 0006 フェーズ 3: テーマ・共通 UI・シェル・ルーティング・アプリの組み立て

作成日: 2026-11-27 / 工程: 実施(フェーズ 3 完了)
ブランチ: `feature/implement-admin-view` / 比較基準: `c76d491`(フェーズ 2 完了時)/ 終了時 HEAD: `fba9ca8`(本記録のコミットは含まない)

## 1. 実施した作業の概要

0002 フェーズ 3 に従い、テーマとデザイントークン、`shared/ui`、共通コンポーネント(`data-table`・`confirm-dialog`・`key-value-list`・`stat-list`・`warning-list`・`filter-bar`・`note-block`)、4 種のページテンプレート、アプリシェル(サイドナビ・モバイルのアプリバー・スキップリンク・外部リンク)、`useOperationDialog`、全 route(ページは最小スタブ)・SPA 内 404・タイトルとフォーカスのガード、`main.ts` の作り直しを実装した。各画面の本実装と、画面固有の部品は作っていない。`code-implementer` が実装し、`code-reviewer`・`test-reviewer` を初回 + 再レビュー 2 回で実施して、Critical・Important を解消した。ユーザー確認が必要な方式変更は発生しなかった。

## 2. コミット

| コミット | 内容 |
| --- | --- |
| `3373f46` | 実装 |
| `6251ace` | レビュー指摘の修正 1(ドロワーのフォーカス閉じ込め・reduced-motion・`useListParams` の競合・E2E の分割ほか) |
| `fba9ca8` | レビュー指摘の修正 2(`useListParams` の競合テスト・離脱後の `update` の無視・`a` の色の語頭一致 ほか) |

## 3. 変更ファイル(`apps/web/` 配下。累積 約 150 ファイル。単体テスト約 50 本・E2E `shell.spec.ts` を含む)

- `src/shared/theme/`: `tokens.ts`・`defaults.ts`・`display.ts`・`icons.ts`・`global.css`・`settings.scss`
- `src/shared/ui/`: `StatusTag`・`statusMaps`・`StateBlock`・`PageAlert`・`FormField`・`ErrorSummary`・`AppSnackbar`・`useSnackbar`・`TopProgress`・`IdText`・`TimeText`
- `src/admin/components/`: `data-table/`(`AdminDataTable`・`AdminDataTableServer`・`RowActions`・`columnPriority`・`tableModel`・`SkeletonRows`・`dataTable.css`)、`key-value-list/`・`stat-list/`・`warning-list/`・`filter-bar/`・`note-block/`、`confirm-dialog/`(`ConfirmDialog`・`ConfirmCheck`・`TypeToConfirm`・`dialogLevel`・`matchesIdentifier`)
- `src/admin/templates/`: `ListPage`・`DetailPage`・`FormPage`・`DashboardPage`・`PageHeader`・`PageBreadcrumbs`・`PageActions`・`ViewStateBody`・`types`
- `src/admin/composables/`: `useBreadcrumbs`・`useContainerWidth`・`routeTitle`・`useRouteTitle`、`useListParams`(競合の修正)
- `src/admin/shell/`: `AppShell`・`SideNav`・`MobileAppBar`・`SkipLink`・`ExternalLinks`・`externalLinks.ts`・`navItems.ts`
- `src/admin/dialogs/useOperationDialog.ts`
- `src/admin/router/`: `routes.ts`・`navGroups.ts`・`guards.ts`・`scroll.ts`・`meta.d.ts`・`NotFoundPage.vue`・`samePage.ts`・`index.ts`(`PlaceholderPage.vue` を削除)
- `src/admin/app/`: `setupVuetify`・`setupQuery`・`setupRouter`・`App.vue`、`src/main.ts`(作り直し)、`src/admin/features/{dashboard,sources,jobs,documents,opensearch}/pages/*Page.vue`(スタブ 9 本)、`src/admin/lib/viewState.ts`(`READY_VIEW_STATE`)
- テスト・設定: `tests/e2e/{shell.spec,smoke.spec,mockApi.spec,apiClient.spec,globalSetup}.ts`、`tests/support/{mount,setup,blankPage,browser,viewStates,e2eServer}.ts`(`viteReady.ts` を削除)、`playwright.config.ts`、`tsconfig.test.json`
- `eslint.config.js` は変更なし(新しい `.vue`・ディレクトリは既存ゾーンに入り、`dependencyRules.test.ts` に所属の期待値を追加)。生成コード・`openapi/`・Nginx・compose は変更なし。

## 4. 検証結果(メインエージェントが再実行。Node 24.22.3)

| コマンド | 結果 |
| --- | --- |
| `gen:api:check`・`typecheck`・`lint`(警告 0)・`format:check`・`build` | 成功。ビルドは JS 約 386KB・CSS 約 271KB(未圧縮)。外部 URL(CDN・外部フォント)は 0 件 |
| `npm run test` | 95 ファイル 1567 件成功(3 回連続で安定。`--sequence.shuffle` も成功) |
| `npm run test:e2e` | 83 件成功(専用ポート 15173)。CPU 高負荷下(vitest 並列)でも成功 |
| `docker build -t loreley-web-check apps/web` | 成功(`COPY` の追加は不要) |

## 5. 実装時確認事項の結果

| ID | 結果 |
| --- | --- |
| **FMOD-U-4**(DataTable の差の吸収) + FARC-U-2 の一部 | `VDataTableServer` の `@update:options` は初期に 1 回発火する。ラッパーはこれを使わず、変更時だけ発火する `update:page`・`update:itemsPerPage`・`update:sort-by` で受ける(マウント直後に通知 0 件をテストで固定)。単一ソート: `multi-sort` を使わず別の列で前の列が外れる。同じ列は「昇順→降順→解除(null)」、`must-sort` なら 2 状態を往復。`hover` は両方で効く(`v-table--hover`)。`aria-sort` は Vuetify が並んでいる列にしか付けないので、`headerProps` で並べ替えできる列に `aria-sort="none"` と `scope="col"` を付けた。キーボード: `<th tabindex="0">` で **Enter のみ。Space は効かない**(DS 4.3「Space は実装時に確認」の結果)。**`mobile` prop の既定が Vuetify 4.3.4 では `false`**(v3 は `null`)で、何も指定しないとカード積みにならない。`:mobile="null"` を明示するとグローバルの `display.mobileBreakpoint: 'md'` に従い、839px でカード積み・840px で通常の表。フッターは `ja` ロケールと `items-per-page-text`・`page-text`・`items-per-page-options=[25,50,100]` で DS 4.3 の形に |
| **FMOD-U-10**(動的 `meta.title` と `document.title`) | `meta.title` は `string \| (route) => string`。解決は `composables/routeTitle.ts` の `resolveRouteTitle` 1 か所(ページ見出し・パンくず・`afterEach` が共有)。パンくずは親の `meta.parent` を辿り、親の path に出てくる params だけを引き継ぐ(不要な params を渡すと vue-router が「Discarded invalid param」警告を出すため)。URL エンコードされた識別子(`a%2Fb%3F%20c`)が h1・タイトルに復号されて出ることを E2E で確認 |
| **FARC-U-14 の一部**(`mobileBreakpoint`・`permanent`) | `display.mobileBreakpoint: 'md'` で 839px が mobile、840px が非 mobile。**`permanent` は付けない**(`VNavigationDrawer` の既定で足りる)。840px 以上は常時表示(幅 232px)、840px 未満は temporary(閉じている間は `inert`+画面外)。**Esc では閉じない**(Vuetify はドロワーの Esc を扱わない)ので `AppShell` で `document` の `keydown` を受けて閉じ、メニューのボタンへフォーカスを戻す。**フォーカス閉じ込め**は `:retain-focus="mobile"`・`:capture-focus="mobile"`(`mobile` 条件が必須。条件なしだとデスクトップの Tab が奪われる)。開いた直後は `inert` が残るため、外れるまで最大 20 フレーム待って最初のナビ項目へフォーカスする。`VDialog`(FMOD-U-5 の先行確認): `role`・`aria-modal`・`aria-labelledby`・`data-testid` は同じ要素に付く。初期フォーカスは確認・標準が見出し、警告つき・要入力確認が最初の入力。Esc は標準だけ閉じ、`persistent` では閉じない。最終確認は `web-ui-reviewer`(フェーズ 6・10) |
| **FARC-U-8**(Playwright の相対 `goto`) | `goto('sources')` は `http://localhost:15173/admin/sources` に解決される。`goto('/sources')` は `/admin` を落として origin 直下になる。`request.get('相対')` も `/admin/` の下。3 点を `shell.spec.ts` に固定 |
| 実測した寸法(DS 2.3) | 入力欄は `density: comfortable` が 48px、`compact` が 40px。DS の 40px に合わせ入力系の `defaults` を **compact** にした(DS 3.2 は comfortable)。小型ボタン(既定 28px)・チップ(26px)は CSS で 32px・24px に、幅 600px 未満はボタン・入力欄とも 44px。FilterBar のセレクトは CSS で 36px |

## 6. 設計・DS との差異(設計書は改訂しない。Q2)

1. `PageAlert` は `VAlert` を使わない自前 div(`VAlert` は `role="alert"` を固定で付け、role なしの info・注記を作れない)。DS 3.2 の `VAlert` defaults は削除。
2. `PageBreadcrumbs` は `VBreadcrumbs` を使わず自前の `nav>ol`(`VBreadcrumbs` は末尾に `aria-current` を付けない)。
3. `navGroups` は `App.vue` から `AppShell` へ props で渡す(F 3.5 は `router/navGroups.ts` に置くが、`shell`(層 4)は `router`(層 6)を import できない)。ナビの抽出・並びは構造型で受ける純関数 `shell/navItems.ts`。`featureFlag` は MVP の `/meta` にフラグがなく常に無効(安全側)。
4. `ActionSpec` は 5 項目のまま。「主操作は 1 つ」は `PageActions` の `primaryId`(省略可)。アイコンは持てず、ページ見出し・行の主操作にモックのようなアイコンが付かない(`RowActions` の iconOnly 用に `primaryIcon` prop のみ)。
5. F の一覧にない補助ファイル: `templates/ViewStateBody.vue`・`types.ts`、`data-table/tableModel.ts`・`SkeletonRows.vue`・`dataTable.css`、`confirm-dialog/matchesIdentifier.ts`、`composables/routeTitle.ts`・`useRouteTitle.ts`、`router/samePage.ts`、`shell/navItems.ts`、`tests/support/{blankPage,browser,viewStates,e2eServer}.ts`。
6. `main.ts`: `vuetify/styles` の後に `@/shared/theme/global.css` も import(Vuetify は `@layer` 内で、ここのレイヤーなしの規則が常に勝つ)。`admin/app/index.ts` は作らず組み立ては `main.ts` に置いた。`setupVuetify` に Vuetify の `ja` ロケールを追加。`tokens.ts` の variables に `high-emphasis-opacity: 1`(既定 0.87 だと本文色が薄くなるため)。
7. `ConfirmDialog` は、実行中(pending)は Esc でも閉じず、キャンセルも無効にする(DS 4.8 にない追加。結果不明のときに失敗アラートを見逃さないため)。`useOperationDialog`: 成功の後始末(`onSuccess`)の例外を操作の失敗にしない構造。`onAlreadyDone` は取消の 409 `job_already_finished`(成功扱い)をフェーズ 7 が扱うための口。
8. 直書き色 `#9cc9ee`・`#66727e` は `global.css` の `:root` に `--color-ink-link`・`--color-placeholder` として集約(`tokens.ts` の theme 色にはしていない: `on-*` の自動生成が増えるため)。
9. `useListParams.update` を、反映前の条件(`pending`)に積み上げる実装にした(全画面に効く)。Vuetify は並べ替え・件数変更の直後に同期的に `page = 1` にするため、画面が `update:sort` と `update:page(1)` を続けて流すと、2 回目が反映前の古い query を土台にして変更が消えていた(実 `useListParams` + 実 `AdminDataTableServer` の結合テストで再現)。`update()` は画面離脱後の呼び出しを無視する。
10. `globalSetup.ts`: `viteReady.ts` は不要になり削除したが、冷えた dev サーバー+並列負荷でウォームアップなしだと最初のテストが時間切れになるため、`./` を 1 回読んで見出しを待つだけに縮小して残した。アプリは起動時に `GET /meta` を取るため、アプリを起動したくないテストは `gotoBlankPage`(同一オリジンの `/admin/blank`)を使う。
11. スタブページに「(画面は後続のフェーズで実装します)」が出る(フェーズ 4 以降で差し替え)。

## 7. レビュー結果

- 初回: code-reviewer は Critical 0・Important 3(ドロワーのフォーカス閉じ込め、reduced-motion の詳細度、`AdminDataTableServer` と `useListParams` の競合)、test-reviewer は Critical 0・Important 3(E2E「全 route が開く」の時間切れ、`AdminDataTableServer` の FMOD-U-4 の検証欠落、ドロワーの Esc まわり)。変異約 140 件のうち生存はごく少数。
- 再レビュー(`6251ace`): code-reviewer は **Critical・Important なし**(Suggestion 2: `a` の色の語頭一致、`update()` の離脱 guard)、test-reviewer は Important 1(`useListParams` の pending 解除・競合ガードが未検証。変異 L3・L4・L8 が生存)。E2E は通常 3 回・CPU 高負荷下 2 回とも 81 件成功。
- 確認(`fba9ca8`): test-reviewer は **指摘なし**。変異 L3・L4・L8・guard・語頭一致・スクリム経路・TopProgress の構造がすべて検出される。

見送りの判断:

| 指摘 | 判断 |
| --- | --- |
| ドロワーの A6・A10・A11・A12(冗長な分岐) | 見送り(`retain-focus` と最初のリンクへのフォーカスが代替) |
| `capture-focus` を外す変異(A2) | 等価に近い(`focusFirstNavItem` が代替)。属性の整理は任意 |
| `READY_VIEW_STATE` の `Object.freeze` | 任意のため見送り |
| `AppShell.test.ts` のアンマウントのテストの閾値(`<= 1`・150ms の実時間待ち) | 現状安定。rAF 実装依存だが対応不要 |
| ConfirmDialog の実ブラウザ E2E(初期フォーカス・focus trap・`persistent` の Esc・背面クリック) | フェーズ 5(jsdom では Vuetify が `isTrusted` でないイベントを無視するため背面クリックは検証できない) |
| メニュー項目(`RowActions` の `⋮`)から開いたダイアログのフォーカス復帰先、失敗時のダイアログ内アラートへのフォーカス移動 | フェーズ 5 |
| 表の見出しの Space キーでの並べ替え(Vuetify 標準は Enter のみ) | フェーズ 7(J1)で `header.<key>` スロットでボタン化する案を再検討。DS 4.3 の「Space は実装時に確認」の結果として記録 |
| `v-list-item` の `<a>` の実描画の色の確認 | フェーズ 4 以降の画面で |
| `ActionSpec` へのアイコン追加(ページ見出し・行の主操作) | 設計外の提案。フェーズ 4 以降で必要になれば検討(UI レビューの指摘次第) |

## 8. 後続フェーズへの申し送り

- **フェーズ 4**(D1・O1): スタブ(`features/dashboard`・`features/opensearch` の `pages/*Page.vue`)を本実装に差し替え。`useViewState`・`ListPage`/`DashboardPage` の `loading` スロット(表と同じ列構成のスケルトン)・`TopProgress` を使う。進行バー(再取得中)の実描画は、画面ができたら `animation-name`(reduced-motion)を実コンポーネントで確認する。外部リンク(AF-20)は `/meta` の URL から表示される(未設定なら領域ごと出ない)。`web-ui-reviewer`(中間 1)の対象にシェル・テンプレート・テーマ(density compact・実測寸法・自前 `PageAlert`/パンくず・`a` の色・外部リンクの 232px での折り返し)を含める。
- **フェーズ 5**: ConfirmDialog の実ブラウザ E2E(初期フォーカス・focus trap・`persistent` の Esc・背面クリック・キャンセルで戻り先へ復帰)、`RowActions` のメニュー項目から開いたダイアログのフォーカス復帰先(`⋮` ボタンへ戻す。`opener` を外から渡せるようにする案)、失敗時のダイアログ内アラートへのフォーカス移動、`lockRefusals`(`tests/support/apiErrors.ts`)の使用、`describeError` の `resendSafe`・`outcomeUnknown`・`lockState`・`crawlerMessage` の使用(0005)。
- **フェーズ 6**: `fieldMap` が `describeError` の `target:'field'` を再分類する(0005)。
- **フェーズ 7**: 表の見出しの Space 対応を再検討。`/jobs/%2e%2e` の Vue Router の復号を E2E で確認(FMOD-U-9)。
- **フェーズ 9**: ビルドサイズの最終測定(FMOD-U-11。現時点で JS 約 386KB・CSS 約 271KB 未圧縮)。
- **フェーズ 10**: DS 8 の a11y の最終確認(スクリーンリーダー・200% 拡大)、Firefox・Safari(FARC-U-15)。
- **フェーズ 11(README)**: `npm run test` は `apps/web` で実行する前提。
- **設計書の追従改訂の申し送り候補**(別タスク): `ViewStateBody` の追加、`PageAlert`・`PageBreadcrumbs` を自前にした理由、`VDataTable*` の `mobile` 既定、`aria-sort` の `none`、density(compact)と実測寸法、`VNavigationDrawer` の Esc とフォーカス(`retain-focus`・`capture-focus`・`inert`)、`main.ts` の `global.css`、`globalSetup` の縮小、`navGroups` を props で渡す理由、`useListParams` の積み上げ。

## 9. 未対応事項

- 上記 7・8 章のとおり。
- 作業ツリーには、停止した対話コマンド・dev サーバー・変異試験の復元漏れがないことを確認済み(5173・15173 は空き)。

## 10. 次のアクション

- フェーズ 4(D1・O1。読み取り専用)を `code-implementer` に依頼する。比較基準は本記録のコミットの SHA。レビューは `code-reviewer`・`test-reviewer` に加え、`web-ui-reviewer`(中間 1)。メインエージェントが専用 compose 環境(`loreley-adminview`)と dev サーバーを起動して依頼する(0003 3 章の事前確認・停止前確認を守る)。
