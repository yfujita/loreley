# 0015 レビュー指摘(0013・0014)への修正(web-ui-designer)

日付: 2026-11-22 / 実施: web-ui-designer(報告をメインが要約して保存)

## 変更ファイル(`docs/v0.x/ui-design/` 配下。同一 v0.1 内の更新。各冒頭の改訂の要点に記載)

- 仕様書: `design-system-v0.1.md`、`admin-view-v0.1.md`、`admin/{documents,opensearch,dashboard,jobs,sources}-v0.1.md`
- モック: `mockups/admin-{jobs,sources,sources-detail,documents,opensearch,dashboard}-v0.1.html`
- スクリーンショット(Git管理外): `.playwright-cli/g4-*.png`(約33枚。J1 通常・stale 375〜1440px、ダイアログ見本 375/768/1280px、X1 320/840/1145px、D1 375/1280px)
- 全7モック×7幅(320/375/768/840/1145/1280/1366px)でページ全体の横スクロール・表内スクロール・`.dframe` 重なりを自動検査し問題0件(X1 の 375px 以下のタブ列横スクロールは仕様どおり)

## 0013 の対応(指摘1〜11すべて対応)

1. DS 10 章の本文と 10.1(承認区分の列。Vuetify 4.3.4・TypeScript 6.x・`@mdi/js`・自前ナビは承認済み(ゲートB)、細目は案)
2. 「PD v0.19 §9.2 #5」の訂正(DS 10.2・14章、admin-view 10.3)。追従改訂の対象は SD §7.5・§7.2・§12.1 #5、PD §3・§7 は参照整合の確認のみ
3. 版の行・各章見出しに承認区分、混在章は節ごと。承認済みの根拠はゲートA・B(0003・0010)のみ
4. サイドバー 840px を全文書で「ユーザー指示。反映結果はゲートCで再承認(R-1)」に統一
5. route `meta` の `order` を admin-view 4.2(X1=0、O1=1)に統一
6. DLG-1 の開く場所を「S1行、S2」に、AF-3 から J2 を外した
7. #8 を「J2 の自動更新(AF-U-3(c) の準用。D1 は #26)」に訂正
8. DS 3.1 に `display.mobileBreakpoint: 'md'`、3.2 の `permanent` を `:permanent="mdAndUp"` か既定挙動に(公式ソース読解・実機4.3.4で要確認と注記)
9. #31〜#34 を追加: #31 J1 の絞り込みをデータソース・状態の2つに限る、#32 DLG-4 実行後は新しいジョブの J2 へ移動(一本化)、#33 S2 に手動更新ボタンを置かない、#34 J1 の URL クエリ(`source`・`status`・`page`・`size`・`sort`)
10. DS 5.3 にナビグループ定義表 `navGroups`(overview/operate/inspect)、8.1 に「新しいグループのときだけ1行」
11. 10.4 の Admin API 申し送りに5項目+時刻 UTC の根拠・409 `source_already_exists` が deleting でも返ること・J1 並び順を追記
- Suggestion・Nitpick: 「確定」→「仕様化済み」、拡張ガイド「5つ」に統一、AF-23 を `auth` 型の唯一の例外に、AF-21 の入力対象は後続設計、Connector 種別切替を拡張点 8.3.1 に追加、DS 4.17 `AutoRefreshSwitch`(#29 に含む)、404 キャッチオール route(4.2)、409 の追記、DLG-4 の水準説明、J1 タグ略記の明記、S4 の「要確認」注記、D1 コンテンツ幅 約984px、余白 24/16px の不一致、2.2 に 20px・15px

## 0014 の対応

- Important 1(J1 の操作列見切れ): 省略の閾値を viewport からコンテナクエリ(`.tablewrap` の幅)に変更。カード幅 1000px 未満で3列を補足行化、720px 未満で取消をアイコンのみ。1145px(カード797)〜1440px(カード1092)で内側スクロール0、全7列表示はカード 1018px(viewport 1366px)以上。J1 stale も同結果。DS 4.3・`jobs` 1.3 に「カード幅で決める」方針。モックの `.doc` 最大幅を 1500px に
- Important 2(`.dframe` の重なり): `height:100%` を除去し `.grid2>.state` を縦flexに(jobs・sources・sources-detail)。375/768/1280px で重なり0
- Suggestion: X1 の 840〜1144px の見出しを「直近」に切替、X1 理由列は `<wbr>` で `_` の後に折り返し、D1 取得失敗は前回構成と同じ全8タイル(必須5・任意3)を出し前回「正常」「異常」は「判定不能」に、前回「未設定」は未設定のまま、概況の合計を通常時と一致。新規5モックに `<noscript>`、`.app` の2列化は枠挿入後(`.shell-ready`)のみ
- Nitpick: タブ余白 10px の適用範囲を 840〜1144px に限定、D1 の見出し周りを全状態で揃える、本文内リンク 24px(WCAG 2.5.8)を DS 2.3 と各画面・モックに反映
- 対応しない: `:root` の未使用変数省略、375px の短い状態でのドロワー、`nav aria-label` の重複、favicon 404

## メインの検証

`git status` は `docs/v0.x/ui-design/` と `agent_tasks/20261121_create_admin_design/` のみ(`apps/`・PD・SD 無変更)。外部通信 grep 0件。`.bak` なし。`height:100%` が admin-jobs から除去されていること、`<noscript>`、`mobileBreakpoint` の記述、「PD §9.2 #5」が誤記として訂正されていること(残る言及は訂正の説明のみ)を確認。

## ゲートCの案の通し番号(更新後)

#1〜#34 と再承認 R-1。更新: #8(表記訂正)、#14(カード幅方針を追加)、#29(DS 4.17 を含む)、#30(ナビグループ定義表を含む)。#24(D1 の任意コンポーネントの扱い。UC-3 と UC-7 の解釈)は変更なしでユーザー確認待ち。

## 未解決事項

- **DS 2.2・2.3・2.6(タイポグラフィ・余白・フォーカス/動きの細則)**: ゲートBに個別提示した記録がないため designer は「案」とした。メインの判断: ゲートBで提示したのは美的方向性・色トークン・角丸・影・outlined 枠・ナビ等で、タイポ・余白・フォーカス細則は個別には提示していない。**案のままゲートCに載せる**(承認済みと扱わない)
- #24 のユーザー確認待ち
- 実機 Vuetify 4.3.4 で要確認: `mobileBreakpoint`/`permanent`、`VTabs`、`VDataTable` の `hover`、`VBreadcrumbs` の `divider`
- playwright は同一セッションが HTML をキャッシュするため、再検証は新規セッションで行う

## 次のアクション

1. 範囲限定の再レビュー: document-reviewer(指摘1・2・4・5・6・8・9、通し番号 #1〜#34 の整合)と web-ui-reviewer(J1 の 1145〜1366px、`#dlg-*` の重なり、D1 stale、X1 の見出しと理由列、`<noscript>`)
2. ゲートC(#1〜#34、R-1、DS 2.2・2.3・2.6 の細則)
3. task-reviewer
