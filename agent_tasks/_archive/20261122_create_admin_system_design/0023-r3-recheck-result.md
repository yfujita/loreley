# 0023 R3 再確認の結果(E・F)

日付: 2026-11-22
レビュアー: document-reviewer(メインが記録)

## 結論

前回 Important 10 件は解消 8 件・ほぼ解消 2 件(6・7)。0022 の追従(`null` の 2 種類、`status=null`、`source_missing`、`cellState`・`expectedFields`)は B・画面仕様の範囲で大きな矛盾なし。新たな Important 4 件(N-1〜N-4)、Suggestion 7 件、Nitpick 2 件。他文書は無変更(`git diff --stat 2cb500fa` は空)。**N-1〜N-4 と S-2・S-3 を直してからフェーズ5へ**(メインの判断: S-1・S-4〜S-7・Nitpick も同時に直す)。

## 前回 Important の判定

1・2・3・4・5・8・9・10 は解消。6(`useViewState`・`PageBreadcrumbs` の provide/inject は解決したが同層 import の新規問題 N-2)・7(`featureFlag` の一本化は完了したが I-89 に外部リンクの定義表の差がない N-4)はほぼ解消。1 の残り: E 12.6 の「B 1.3 の D1 の行の EP-14 は B 側の確認事項」が古い

## 新規指摘

**Important**
- N-1: E 12.3 の FARC-P-3 の行(695 行)の表崩れ。`` `^22.12 || ^24 || >=26` `` のバッククォート内の `||` が列区切りになる(9 列、期待 5 列)。`\|\|` にするか散文にする
- N-2: F で `templates`(`PageHeader`)が `components/breadcrumbs/PageBreadcrumbs.vue` を描画するのが、同層禁止(R7・6章 515 行)に反する。`PageBreadcrumbs` を `templates` に移す(3.6 の 5.2 行も)、または R7 に例外を明記
- N-3: E 5.9 の「null の 2 種類」(a)取得失敗が「見える文言」と「見た目は「—」…視覚的に隠した」で自己矛盾。画面仕様は、表のセル(S1 の登録文書数、X1)は視覚的に隠した文言、S2 のインデックスカードは見える文言。(a)を「画面仕様に従う(表のセルは視覚的に隠した「取得できません」、カードは見える文言)」に。F の `cellState` の説明にも一文
- N-4: I-89 が `featureFlag` の差だけで、外部リンク項目を route `meta` でなく定義表(`shell/externalLinks.ts`)に持つこと(DS 5.3「定義は route `meta` にだけ」との差)を挙げていない。E 4.3 の `RouteMeta` に `nav.external?` が残っている(外部リンクは route でない)。4.2(176 行)の「上の定義表」は「下の」

**Suggestion**
- S-1: R4 の例外(`useViewState` が `@tanstack/vue-query` の型を要る。`import type` を許す、または入力を構造的な型に)
- S-2: F 5.4 手順4(479 行)を手順2に合わせる(`rerunnable=true`: 出す、`superseded`・`stalled`: 無効+理由、それ以外: 出さない)
- S-3: F 8.6 の「R1〜R15」→R1〜R16、F 8.1 の「E(R3 前の版)」更新、E 12.1 の「確認した事実」に R3 修正・0022 後の B 再照合を記録
- S-4: B の `registration.partial` は boolean(`null` 不可)で `phase` だけが `null` になりうる。E 5.9・F の `expectedFields` は `partial` も `null` 許容(安全側)。B のどちらが正かを確認
- S-5: 凡例の文言: 「承認済みの案」の定義が既承認文書の「承認済みの案」の引用だが、FARC-P-31〜33・FMOD-P-26 は DS・画面仕様の「承認済み(ゲート B・C)」の引用で字面の範囲外。「既承認文書の「承認済み」の引用で、本タスクのユーザー確認がないものも承認済みの案とする」と一文足す(E・F)
- S-6: FARC-U-12 の「B のゲート3前の案」に AAPI-P-39・P-41 が入っていない
- S-7: E 3.1(129 行)の「外部のフォント・CSS・スクリプトを読まない(DS 3.1。FARC-K-9)」は K-9 の範囲を超える。外部通信の禁止全般は FARC-P-32 に直す

**Nitpick**: E 0章・8 行の改訂履歴に R3 修正と 0022 が入っていない/F 8.2 の FMOD-K-2 に FARC-K-8 が混ざっている/F 8.6 の「生成と クライアント」のスペース

## 0022 の追従の確認

`JobBrief` と `registration` の `null` 許容、`status=null` のとき `stalled=false`・`cancellable=false`、`rerun_blocked_reason` 6 値と `rerunnable=null` の条件、「削除中」と表示しない理由は B 2.2・2.9・2.11・EP-10・AAPI-P-41 と一致。E 5.7 と F 4.1 の画面ごとの EP は一致(D1=EP-13、S1〜S4=EP-14 を含む、J1=EP-09+EP-01、J2=EP-10、X1=EP-11+EP-01、O1=EP-12、シェル=EP-14)。ID 参照は定義・使用が揃い、欠番は経緯説明のみ

## ユーザー確認(ゲート3に追加)

1. 外部リンク項目を route `meta` でなく定義表(`shell/externalLinks.ts`)に持つこと(DS 5.3 との差)。I-89 とあわせて
2. 凡例の扱い(S-5): DS・画面仕様の「承認済み(ゲート B・C)」の引用を本タスクで承認済みの案とする運用(FARC-P-31〜33・FMOD-P-26)
3. 値が読めない `null` の表示案(I-120)、`source_missing` の文言・「出さない」案(I-121、AAPI-P-41)
4. 継続: I-88、I-89、FMOD-P-17

## 次

E・F の修正(担当 writer)→ 差分確認。D 執筆中(C 追従修正を含む)→ R2(C・D)、A・B の差分確認(S-4 の B 側確認を含む)→ フェーズ5
