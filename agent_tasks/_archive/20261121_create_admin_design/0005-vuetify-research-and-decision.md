# 0005 UI ライブラリ決定(PrimeVue 見送り→Vuetify)と Vuetify 調査

日付: 2026-11-21 / 実施: tech-advisor(報告をメインが要約して保存)

## ユーザー決定

0004 の PrimeVue ライセンス事実を受け、ユーザーが「**PrimeVue は見送って Vuetify を使う**」と回答。0001 の技術スタック(案)の PrimeVue / PrimeIcons / `@primeuix/themes` は Vuetify に読み替える。確定は引き続きゲートBで承認(案)。

## 調査結果(要約)

- ライセンス: `vuetify` 4.3.4 は MIT(依存は `@vuetify/v0` のみ、`vite-plugin-vuetify` 2.1.3 も MIT)。`@mdi/font`・`@mdi/js` は Apache-2.0。有償機能はパッケージ内に見当たらない。
- バージョン: `latest` = 4.3.4(2026-11-18、v4 初版 2026-02-23、週次リリース)、`v3-stable` = 3.13.8(LTS 2026-07-27〜2027-07-27)。peer: vue ^3.5、vite-plugin-vuetify >=2.1.0(Vite 8 は peer 上問題なし・実動未確認)。
- ブラウザ要件(v4): Chromium 119+ / Firefox 128+ / Safari 16.4+。
- v4 の主な破壊的変更: CSS レイヤ5分割、グローバル margin/padding リセット廃止、タイポグラフィクラスが MD3 名、ボタン非大文字化、ブレークポイント md/lg/xl/xxl = 840/1145/1545/2138px、エレベーション 0〜5、`defaultTheme` 既定が `system`(→ライトのみなら `'light'` を明示)、`defaults` のマージ規則変更。
- トークン: 色は `--v-theme-{名}: r,g,b`(RGB 三つ組。`rgb(var(--v-theme-primary))` で使う)、`variables` は `--v-{キー}`(`--v-border-color` 等)。既定 light: primary #1867C0、secondary #48A9A6、error #B00020、info #2196F3、success #4CAF50、warning #FB8C00。**角丸は SASS 定数(`$border-radius-root` 既定4px。sm=0.5x/md=1x/lg=2x/xl=6x)で CSS 変数にならない**ため、モックは独自 `--radius-*` を定義し、仕様書に SASS 変数との対応表を書く。
- 調整方法: `defaults`(全体/コンポーネント別/親子ネスト、aliases)+ SASS 変数(`vite-plugin-vuetify` の `styles.configFile`)。`md3` blueprint は開発中扱いのため依存せず、`defaults` で明示する方が再現性が高い(案)。フォントは `$body-font-family` をシステムフォントに上書き。
- 部品: `VDataTable` / `VDataTableServer`(`noDataText`、`loading`スロット+`VSkeletonLoader`)、`VEmptyState`、`VChip`、`VDialog`(role=dialog、aria-modal、retainFocus)、`VAlert`(role=alert)、`VSnackbar`(role=status)、`VTabs`、`VBreadcrumbs`、`VNavigationDrawer`(`<nav>`、rail/temporary)+`VList nav`、`VAppBar`、フォーム部品、`VCard` 等が実在。`source_id` 入力確認は標準部品なし(`VDialog`+`VTextField`+disabled な `VBtn` で構成)。キー・バリュー専用部品はなし(`<dl>` 自作等)。
- 外部通信: ランタイムの外部取得先なし(`lib/` 走査)。Roboto は同梱されない(システムフォント指定で外部フォント不要)。アイコンは `@mdi/js`+`vuetify/iconsets/mdi-svg`(推奨。公式 production 向け)。CDN `<link>` は使わない。フルビルド実測: CSS 538KB(gzip 73KB)、JS 735KB(gzip 218KB)。tree-shaking は `vite-plugin-vuetify`。
- Vue Router / Query: `to` prop で router-link 連携。route `meta` 駆動ナビは `VList`+`VListItem :to` で可。サーバー側テーブルは page/sortBy/itemsPerPage の ref を queryKey に含める設計提案(`keepPreviousData`、`@update:options` の初期発火による二重取得に注意、`isRefetchError` で前回データ+`VAlert`+`dataUpdatedAt`)。
- アクセシビリティ: VDialog はフォーカス閉じ込め・復帰あり(実装後に E2E で検証)。VDataTable は `aria-sort`・Enter ソート(Space 未確認、行間矢印移動の公式記載なし)。VChip は色のみに依存しない(アイコン+文言)。既定 warning #FB8C00・info #2196F3 は白背景でコントラスト不足の可能性(要実測)。VAlert/VSnackbar は通知を出し過ぎない。
- テスト: Vitest は `test.server.deps.inline: ['vuetify']`、`ResizeObserver` モック、`createVuetify()` と `VLayout` ラップが必要。公式は実ブラウザモード推奨。
- `typescript` 7 系は `vue-tsc` が動かない報告(2026-07)。6.x 固定が無難(案)。
- PrimeVue 4.5.5 との比較: Vuetify は保守が活発、レイアウト部品が揃いシェルを作りやすい、`defaults` で一括調整可。短所は Material 色が強い、角丸が変数にならない、v4 は新しく変更が頻繁、ブラウザ要件が高め。

## 未確認

`VDataTable` の行ホバー prop・Space ソート、tree-shaking 後サイズ、Vite 8/Vitest 5.1 の実動、`md3` blueprint の公式ステータス、`@mdi/*`(Apache-2.0)の社内ポリシー上の扱い、Query との併用は設計提案(公式例なし)。

## 技術スタック(案)の更新(designer に渡す案)

Vue 3 + TypeScript(6.x 固定)、Vite、**Vuetify**(4.3.4 exact pin。v3 LTS 3.13.8 は代替)、`vite-plugin-vuetify`、`@mdi/js`、Vue Router、TanStack Vue Query、Vitest + Vue Test Utils、Playwright、ESLint + Prettier。`defaultTheme: 'light'`、`defaults`+SASS 変数でトークン管理(blueprint 非依存)、システムフォント、自前の route `meta` 駆動ナビ(`VNavigationDrawer`+`VList`)、入力確認は `VDialog` 構成、stale 表示は `isRefetchError`。Pinia・Tailwind・vue-i18n は入れない。

## ユーザー回答(追記)

- Vuetify のバージョン: **v4.3.4 を exact pin(案)**
- ブラウザ要件: Chromium 119+ / Firefox 128+ / Safari 16.4+ を前提としてよい
- 技術スタック全体は引き続きゲートBで最終承認(案)。アイコン(`@mdi/js`)・`defaults`+SASS 方式・自前ナビ等の細目も案のまま

## 次のアクション

1. (完了)ユーザーに「v4.3.4 か v3.13.8 か」「社内ブラウザ要件」を確認し、結果を記録
2. web-ui-designer をフェーズ1.1で呼ぶ(0003 の承認範囲+本記録の事実と決定を添付)
3. SD §7.5・PD §9.2 #5 追従改訂タスクへ経緯(PrimeVue 5 のライセンス変更、Vuetify 採用)を引き継ぐ
