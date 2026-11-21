# タスク状態

## 基本情報

- 状態: done
- 現在工程: 完了(PR #9 へのユーザー改善依頼 4 件を反映済み: 1 件目=シャード配置の向き変更(0023)、2 件目=インデックス一覧の統合(0024)、3 件目=クラスタ状態カードの統合(0025)、4 件目=O1 の絞り込みフォーム追加(0026)。以降の改善依頼は 0027 以降に記録)
- 最終更新: 2026-11-22
- 最新作業記録: 0026-o1-index-filter-form.md

## 現在の状況

Admin View のデザインが完了した。
- 成果物(`docs/v0.x/ui-design/`、すべて新規・v0.1): 仕様書7本(`design-system-v0.1.md`、`admin-view-v0.1.md`(索引・トレーサビリティ・拡張ガイド・承認状況一覧)、`admin/{sources,jobs,documents,opensearch,dashboard}-v0.1.md`)、静的 HTML モック7本(`mockups/`)。AF-1〜20 の全画面(D1・S1〜S4・J1・J2・X1・O1)を網羅し、AF-21〜32 は画面を作らず拡張ガイドの型対応表のみ
- ユーザー承認: ゲートA(0003: プラン・前提(案))、ゲートB(0010: 方向性・トークン・ナビ・シェル・危険度・技術スタック等)、ゲートC(0020: #1〜#36 と R-1)。承認の根拠はこの3記録のみ
- UI ライブラリは PrimeVue 5.x が非MITのため見送り、**Vuetify 4.3.4(exact pin)に決定**(0004・0005)
- レビュー: document-reviewer・web-ui-reviewer(第1段階の軽量レビュー含む。指摘は解消済み)、task-reviewer(0022。Important 2件対応済み)。code-reviewer・test-reviewer は省略(コード・テストの変更なし。0002 第8章)
- 変更範囲は `docs/v0.x/ui-design/` と `agent_tasks/20261121_create_admin_design/` のみ(`apps/`・PD・SD 無変更。コミットなし。比較基準 SHA `a56b3ae`)
- HTTP サーバー(ポート 8765)は停止済み

## 次のアクション

1. 実装着手前に、案のまま残る DS 3・8・9・11 章と DS 10 章の細目(承認済みではない)を確認する
2. 別タスク: SD v0.8 §7.5・§7.2・§12.1 #5 と PD v0.19 §3・§7 の追従改訂(admin-view 10.3。Vuetify 採用の経緯を引き継ぐ)、Admin API 設計(10.4 の申し送り)、Web UI の配信方式、Search View のデザイン(design-system を再利用)
3. 実装時: 実機 Vuetify 4.3.4 での確認事項(下記)

## 未解決事項

- DS 3・8・9・11 章(`defaults`・SASS・テーマの設定方法/a11y の具体/`data-testid` の名前の細則/Search View での流用方針)と DS 10 章の細目(`vite-plugin-vuetify`・Vite・Vue Router・TanStack Query の `retry`・テスト・静的解析・入れないもの・API の型)は案のまま(方針はゲートA/B 承認済み)
- Admin API 未設計(登録文書数の数え方、リース切れ判定、cron タイムゾーン取得経路 AF-U-6/13、ダッシュボード取得経路 AF-U-1、ページング方式など。admin-view 10.4)
- 実機 Vuetify 4.3.4 での確認: `mobileBreakpoint`/`permanent`、`VTabs`、`VDataTable` の `hover`、`VBreadcrumbs` の `divider`、J1 の最小幅 916px のフォント依存、ダイアログのフォーカス管理
- `@mdi/js`(Apache-2.0)の社内ポリシー上の扱い
- 静的モックで未確認の挙動(フォーカストラップ、自動更新、スクリーンリーダー、Firefox/Safari)
- 上流設計(Crawler・Indexer)の案(失敗理由・警告・削除結果状態のコード名 CA-P-10・CA-P-73 等、CA-P-69 の固定文、`lock_held` の冪等扱い=SD §14.4 の案)
- SD/PD の追従改訂の出所の訂正: 技術スタックの「未決定」は SD v0.8 §7.5・§12.1 #5 が引く旧版の「PD v0.4 9.2 #5」である。PD v0.19 の §9.2 にその項目はなく、PD §3・§7 が SD §7.5 へ委ねるだけ(0001・0005 の「PD §9.2 #5」表記は誤り。0013 で訂正)

## ユーザー判断待ち

- 0000 の補足パス(`docs/v0.x/ui-admin/` → 実際は `docs/v0.x/system-design/ui-admin/`)と技術スタック案(PrimeVue → 実際の決定は Vuetify)を 0000 に追記するか(任意。0000 はユーザー記載のため agent は書き換えていない)
