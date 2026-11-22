# 0018 再レビュー指摘(0016・0017)への修正(web-ui-designer)

日付: 2026-11-22 / 実施: web-ui-designer(報告をメインが要約して保存)

## 変更ファイル(`docs/v0.x/ui-design/` 配下)

- 仕様書: `design-system-v0.1.md`、`admin-view-v0.1.md`、`admin/{jobs,dashboard,sources}-v0.1.md`、`admin/{documents,opensearch}-v0.1.md`(更新日と改訂の要点のみ)。7本の更新日を 2026-11-22 に
- モック: `mockups/admin-jobs-v0.1.html`(列幅・省略の閾値・補足行のタグ)、`mockups/admin-dashboard-v0.1.html`(説明文の注記のみ)
- スクリーンショット(Git管理外): `.playwright-cli/g5-jobs-{1145,1200,1279,1280,1366,1440}-{j1-normal,j1-stale}.png`

## J1 の全列表示の閾値(実測。designer)

左右余白を 16px→12px にして全7列の最小幅を 972px→916px に縮めた。全列が収まる閾値はカード幅約 920px 以上(`@container` で 919px 以下は省略)。実アプリのカード幅は viewport−296px で、viewport 1280px で約 984px のため **1280px 基準で全列表示**(全列表示は viewport 約 1216px 以上。モックはカード幅が viewport−344px のため約 1264px 以上)。実測: 1145px(カード797)=4列、1200px(852)=4列、1279px(931)=7列、1280px(932)=7列、1366px(1018)=7列、1440px(1092)=7列。いずれも normal・stale とも表内スクロール 0、取消ボタンはカード内。起動時の指定タグ(強制削除・再書き込み)は全列表示では「種別・起動」列、省略表示では補足行に出る。最小幅はフォント依存のため実装時に再測定する旨を仕様書に記載。

## 対応

- 0016 Important 1〜4: J1 の列省略と 1280px 基準の整合(`jobs` 1.2・1.3、DS 7・4.3、admin-view #14。#14 と DS 7 の見出しは「列の省略規則(画面ごとのカード幅の閾値)」)、D1 取得失敗の記述統一(#25、dashboard 0・5・10章)、#35(DS 2.2・2.3・2.6 の細則。案)を admin-view 10.1 に追加し DS 2.2 冒頭に「フォントの選択方針は承認済み、寸法・ウェイトは案」、10.3 の承認済み範囲を「Vuetify 4.3.4・TypeScript 6.x・`@mdi/js`・自前ナビ。その他は案(DS 10.1)」に
- 0016 Suggestion 1〜6・Nitpick: 古い注記の整理、4.9 の日時タイムゾーン表示は案と注記、DS 4.3 に S1・X1 は viewport 基準のままでよいと1行・8.4 の確認幅に 1366px、#33 の参照節 1.10、AF-27 は DS 4.17 の流用または一般化、DS 5.3 の整理、404 キャッチオールの route 行、`jobs` 0章の表を番号順、DS 13 に R-1
- 0017 S-1(上記)、N-1(D1 モック冒頭コメントと dashboard の改訂の要点に「実装では全状態で説明文を出す」)、N-2(DS 2.3 を「表の識別子リンクは行全体の余白で確保(行48px以上。WCAG 2.5.8 の間隔の例外)、本文中のリンクは24px以上」に)
- 未対応: 0016 Nitpick「DS `:34` の重複」は designer が該当箇所を特定できず(後続の編集で解消した可能性)

## メインの検証

`git status` は `docs/v0.x/ui-design/` と `agent_tasks/20261121_create_admin_design/` のみ。外部通信 grep 0件、`.bak` なし。admin-view 10.1 に #34・#35 の行を確認。7本の更新日 2026-11-22 を確認(documents・opensearch・DS ほか)。

## 次のアクション

1. 差分の再確認(document-reviewer: J1・D1・10.1 の整合。web-ui-reviewer: J1 の 1145〜1440px)
2. ゲートC(#1〜#35、R-1、#24)
3. task-reviewer
