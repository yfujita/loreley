# 0004 技術事前調査(tech-advisor)

日付: 2026-11-21 / 実施: tech-advisor(報告をメインが要約して保存。調査はWeb情報とnpmパッケージ実物に基づく。単一ソース・未確認の点は明記)

## 重大な発見: PrimeVue のライセンス

- npm `primevue` の `latest` は 5.0.5(2026-11-11)。`v4-stable` は 4.5.5(2026-04-08 が最終)。
- v5 系(primevue 5.x、`@primeuix/themes` 3.x、`primeicons` 8.x)は **PrimeUI License(Community/Commercial)**。ライセンスキーが必要で、無い・期限切れだとライセンス通知が表示されうる。検証はオフライン。
- Community 無償条件(全て満たす必要): 開発者5人未満、従業員10人未満、年間売上100万USD未満、外部資金300万USD未満、公共機関・大学・政府系でない。年次更新あり。該当しなければ商用(1開発者599USD、2027年から799USD)。
- v4 系(`primevue` 4.5.5 / `@primeuix/themes` 2.0.3 / `primeicons` 7.0.0)は MIT のまま。公式は既存 MIT 版は永久に MIT と明言。4.x は「Security fixes only」で実質最終版(最終版という明言は第三者 Issue のみ)。
- v5 は公開 API の破壊的変更なし(公式 migration)。v4 前提で作った画面は後から v5 へ上げやすい。v5 では PanelMenu、Button の label/icon/badge/loading prop、Tabs `scrollable` などが非推奨。

### 推奨(ユーザー判断待ち)
(A)4.5.5 / `@primeuix/themes` 2.0.3 / `primeicons` 7.0.0 を exact pin した MIT 構成を「案」とする(推奨)。(B)v5 採用(組織が Community 条件を満たすか商用購入かの判断が先に必要)。(C)MIT の別ライブラリ(比較調査が別途必要)。

## その他の主な事実(仕様書の案に反映)

- トークン: primitive / semantic / component の3層を `definePreset(Aura, {...})` で上書き。CSS 変数は `--p-*`(例: `--p-primary-500`、`--p-surface-0`、`--p-content-border-color`、`--p-form-field-border-radius`)。モックは `:root` に同名変数を定義し、その変数のみ参照すると実装へ1対1で移せる。
- フォントのトークンは無く、アプリ側 `body { font-family }` で指定(システムフォント方針と整合)。コンポーネントは rem 基準。
- ライトのみ(前提2)なら `darkModeSelector: false` を明示(既定 `'system'` だとOSダークで別配色になる)。`@primevue/themes` は deprecated、後継は `@primeuix/themes`。
- コンポーネント: DataTable(sortable/paginator/`#empty`/`loading`/Skeleton)、Tag(severity: primary/secondary/success/info/warn/danger/contrast。ARIA無しなので文言・アイコン併用)、Message(severity に `error`、`variant="simple"` が検証エラー定番、role=alert)、Toast、Dialog(モーダル時フォーカス循環・Escで閉じる)、Tabs、Breadcrumb、フォーム部品、Skeleton、Card はいずれも v4 に実在。Toast の severity 表記は要確認。
- ConfirmDialog に **入力確認(`source_id` 入力)の標準機能は無い**。Dialog + InputText + 一致時のみ有効なボタンで構成するのが素直。
- サイドバー: PanelMenu は v5 で非推奨、Menu は role=menu でサイトナビに不向き。**自前 `<nav aria-label>` + `<router-link>` + route `meta` 駆動(`router.getRoutes()` から `meta.nav` を抽出)**を推奨。
- PrimeIcons 7.0.0 はフォント・CSS同梱で外部通信不要(実物確認)。PrimeVue 4.5.5 本体に外部取得先は無い(ESM走査)。`primeicons` は **7.0.0 に固定**(8.x は非MIT)。
- TanStack Vue Query v5: 初回は `isPending`(Skeleton)、背景再取得は `isFetching`、`isLoadingError`(データ無しエラー)、`isRefetchError`(前回データ表示のまま警告+`dataUpdatedAt`)。定期更新 `refetchInterval`、手動更新 `refetch()`/`invalidateQueries`、併用可。既定リトライ3回(エラー表示まで約7秒)なので管理画面は `retry: 1` 程度を案とする。
- `typescript` 7 系は `vue-tsc` が動かない報告(2026-07、現状未確認)。`typescript` 6.x 固定が無難(案)。
- アクセシビリティ: カスタムパレットはコントラスト保証対象外で、primary 変更時は自前で比率確認。危険操作ダイアログは実装後に Playwright でフォーカス移動を検証。Message/Toast は role=alert のため、ポーリング失敗で Toast を連発しない。

## 未確認・未対応

- MIT 代替ライブラリ(Reka UI/Naive UI/Element Plus 等)の比較、v5 のキー設定手順と通知の実挙動、`@primevue/forms` の安定度、TS 7.1 の状況、DataTable `rowHover`。

## 次のアクション

1. ユーザーに PrimeVue 採用方針(A/B/C)を確認し、結果を記録
2. 決定を前提に designer 依頼へ反映(技術スタック案のバージョン固定・ライセンス注記、`darkModeSelector: false`、`typescript` 6.x 固定案、自前 `<nav>` 案、入力確認 Dialog 構成、`isRefetchError` による stale 表示)
3. SD §7.5・PD §9.2 #5 の追従改訂タスクへライセンス事実を引き継ぐ
