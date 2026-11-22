# 0026 B の `registration.partial` を `null` 許容に確定

日付: 2026-11-22
担当: document-writer(B 担当。メインが記録)

## 変更ファイル

B(`admin-api-v0.1.md`)のみ。A・C・D・E・F・agent_tasks は無変更。

## 決定(案。ゲート3で承認を取る。AAPI-P-25 に追記)

- `registration.partial` は boolean / null。保存値が読めないとき(欠落・真偽値でない)は `null`(2.2 の「保存値が読めないとき `null`」の原則に従う)
- `registration.phase` は `partial` が `null` のとき `null`。`partial=true` で `status` が `null`(読めない)のときも判定できないため `phase=null`。それ以外は従来どおり(`partial=false`→`final`、`partial=true` で実行待ち・実行中→`in_progress`、`partial=true` で終端→`incomplete`)
- 従来の B は 2.2 が「`partial` は `null` を許す」、EP-10 の応答表が boolean(`null` 不可)で食い違っていた → EP-10 の応答表(5.2)を boolean / null に直し、2.2 と AAPI-P-25(11.3)に追記。JSON 例は `partial: true`・`phase: "incomplete"` で変更不要

## 他文書への影響

- C: 影響なし(5.0・5.4 とすでに一致)
- E・F: `registration.partial` と `phase` が `null` になりうる。画面は `null` を「—」とし、「確定 / 集計の途中 / 途中までの値」のタグを出さない(E 5.9・F `expectedFields` は `partial` を `null` 許容にしており一致)。型生成の入力には boolean / null として反映が必要(実装時)

## 次

R2 の結果待ち → フェーズ5(統合)
