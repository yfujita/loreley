# 0022 E・F を B の最新変更に追従(3回目)

日付: 2026-11-22
担当: document-writer(E/F 担当。メインが記録)

## 変更ファイル

E(`ui-admin-frontend-architecture-v0.1.md`)・F(`ui-admin-frontend-module-structure-v0.1.md`)のみ。A・B・C・D・agent_tasks は無変更。

## 変更

- E 1.2・5.7・5.9・6.7: `status=null`(ジョブ記録の値が読めない)のジョブにはステータスタグも操作も出さない。**5.9 に「`null` の 2 種類」**: (a) 取得失敗(`unavailable` にキーがある)=「—」+見える「取得できません」、(b) 値の読めない `null`(`unavailable` に載らない)=「—」+視覚的に隠した「読み取れません」。`JobBrief` の `status`・`job_type`・`trigger`・`queued_at`、`registration` の件数・`partial`・`phase` は値があるはずの項目。`started_at` などの `null` は従来どおり「—」+「なし」。画面仕様に定義がないため案
- E 6.7: `rerunnable=null` に設定の読み取り失敗を含む。`source_missing` は「再実行」を出さず「削除中」と表示しない案(専用文言は画面仕様に足すかゲート3の確認後)
- F 3.5・3.9: `admin/lib/unavailable.ts` に `cellState(response, path, value, {expected})`(表示状態 `value`・`unavailable`・`unreadable`・`none`)、`admin/lib/expectedFields.ts`(値があるはずの項目の表)を新設。`JobStatusCell` は `status=null` でタグを出さず「—」、`RegistrationCard` は件数・`partial`・`phase` が `null` なら「—」、`jobActions.ts` は `source_missing` を出さない・`status=null` のジョブに操作を出さない・`rerunnable=null` の条件を反映。F 5.4・7.2・7.3(テスト)にも反映

## 新規・変更 ID

- E: FARC-P-36(案。値の読めない `null` と取得失敗の表示、`status=null` のジョブにタグ・操作なし)、FARC-P-37(案。AAPI-P-41・ゲート3: `source_missing` は出さない)、I-120(画面仕様に値の読めない `null` の表示定義がない)、I-121(画面仕様に `source_missing` の理由文言がない)、FARC-P-27 更新。ID 体系の I 予約範囲を I-80〜89 と I-120〜129 に
- F: FMOD-P-31(`cellState`・`expectedFields`。案)、FMOD-P-32(`source_missing` は出さない。案。ゲート3)、FMOD-P-14 更新。I-130〜139 は未使用
- 区分の変更なし

## ゲート3の確認事項の増減

増: I-120(値の読めない `null` の表示)、I-121(`source_missing` の文言と「出さない」案)、FARC-P-36・P-37、FMOD-P-31・P-32。画面仕様への追記候補: 値の読めない `null` の表示、`source_missing` の理由文言

## 自己検算(writer)

ID 参照の未定義・未参照なし、表・フェンス整合、EP は EP-01〜14 のみ・code 名変更なし

## 次

R3 再確認(E・F)。D 執筆中(C 追従修正を含む)→ R2(C・D)、A・B の差分確認 → フェーズ5
