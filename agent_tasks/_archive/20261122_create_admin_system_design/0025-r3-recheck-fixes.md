# 0025 R3 再確認の指摘の修正(E・F)

日付: 2026-11-22
担当: document-writer(E/F 担当。メインが記録)

## 変更ファイル

E(`ui-admin-frontend-architecture-v0.1.md`)・F(`ui-admin-frontend-module-structure-v0.1.md`)のみ。A・B・C・D・agent_tasks は無変更。

## 変更

- N-1: E 12.3 の FARC-P-3 の表崩れを散文に(Vitest 5 の要件 `^22.12`・`^24`・`>=26` のいずれか、かつ Hey API の `>=22.18` を満たす)。全表を厳しい方式(バッククォート内の `|` も区切りとして数える)で再チェックし崩れ 0
- N-2: `PageBreadcrumbs` を `admin/templates/` に移動(F の構成図・3.6 の 5.2 行・3.7 の `PageHeader` 行・FMOD-P-28)。R7 の規則文は変更不要(同じ `templates` 内の参照は同層 import に当たらない)
- N-3: E 5.9 の (a) を「表示は画面仕様に従う(表のセルは視覚的に隠した「取得できません」、S2 のカードは見える文言)」に。F の `cellState` の説明にも同文
- N-4: I-89 に「外部リンク項目を route `meta` でなく定義表 `shell/externalLinks.ts` に持つ(DS 5.3 の「定義は route `meta` にだけ」との差)」を追加(ゲート3でユーザー確認)。E 4.3 の `RouteMeta` から `nav.external` を外す。E 4.2 の「上の定義表」を「下の『外部リンク』の行の定義表」に
- S-1: F の R4 に例外(`admin/composables/useViewState.ts` は `import type` を許す。入力を構造的な型にしてもよい)
- S-2: F 5.4 手順 4 を手順 2 に合わせた(`rerunnable=true` で出す、`superseded`・`stalled` は無効+理由、それ以外は出さない)
- S-3: F 8.6 を R1〜R16、F 8.1 の「E(R3 前の版)」を更新、E 12.1 に R3 修正(0018)と 0020・0022 後の B 再照合を記録
- S-5: E・F の凡例の「承認済みの案」に「DS・画面仕様の「承認済み」の引用で、本タスクのユーザー確認がないものも承認済みの案とする」
- S-6: FARC-U-12 を「AAPI-P-16〜18・24〜34・37〜39・41」に更新。S-7: E 3.1 の出典を FARC-K-9(外部フォント・CDN)と DS 3.1・FARC-P-32(外部通信の禁止全般)に分けた
- S-4: E 5.9・F `expectedFields` は `registration.partial` を `null` 許容(安全側)のまま。B との照合は別途(下記)
- Nitpick: E 0 章の改訂履歴に R3 修正と 0020・0022 を追記、F 8.2 の FMOD-K-2 から FARC-K-8 を外す、F 8.6 のスペース、E 12.6 の D1・EP-14 を「B 側で解消済み(0017)」

## 新規・変更 ID

新規なし。変更: FARC-U-12、FMOD-P-28、FMOD-K-2、I-89(内容追加)。区分の変更なし

## 自己検算(writer)

ID 参照の未定義・未参照なし、E・F が引用する AAPI・BAPI の ID は A・B に定義あり、表崩れ 0・フェンス整合、EP は EP-01〜14 のみ

## ゲート3の確認事項の増減

I-89 の外部リンク定義表(DS 5.3 との差)、S-5 の凡例の運用(FARC-P-31〜33・FMOD-P-26)が増

## B への確認事項(未解決)

`registration.partial` の型: R3 再確認では「B は `partial` を boolean(`null` 不可)とし `phase` だけが `null` になりうる」とあるが、B 2.2 は「`registration` の件数・`partial`・`phase` などの型は `null` を許す」と書く。B 側で正を確認 → E 5.9・F `expectedFields` を合わせる

## レビュー計画の判断

R3 の3回目の再確認は実施しない。理由: 今回の修正は機械的(表崩れ、凡例の文言、構成の置き場の移動、参照の更新)で、writer が全表の列数・ID 参照を機械検算済み。E・F は R4(横断整合)でも対象にする。

## 次

- B の `partial` の確認、R2 の結果待ち → フェーズ5(統合)
