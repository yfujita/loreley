# 0015 E の再追従(R1 再確認 N-1〜N-5 分)

日付: 2026-11-22
担当: document-writer(E 担当。メインが記録)

## 変更ファイル

`docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.1.md`(766 行。E のみ。A・B・agent_tasks は変更なし)

## 修正内容

- 0章(凡例): 「承認済みの案」の行に、既承認文書(画面仕様など)の承認済みの案の引用は確定にせず出典を区分欄に書く旨と、不採用として扱った案の欠番の扱いを追記(A の凡例と同じ)
- 5.4・5.5: 更新間隔の参照を FARC-K-6 から FARC-P-31 に読み替え
- 5.7(X1): `unavailable` の EP-11 のキーを `items[].existence` に(S1・S2・J1・J2 の行と 5.9 は再照合し一致)
- 6.2・6.3: EP-07 の取消で、`job_id` に `%`・`?` などを含み Crawler が 400 `invalid_request`・404 `not_found` を返した場合も 404 `job_not_found` に写る旨を追記(AAPI-P-39。案。画面の表示は既存の 404 の扱い)
- 12.2・12.3・12.6: **FARC-K-6 を欠番にし FARC-P-31(承認済みの案。画面仕様ゲート B・C の承認事項の引用: dashboard 4.1・admin-view #26・#8・#33。ユーザー確認はゲート3)へ**。FARC-P-9 の区分欄を更新。R1 再確認への追従 5 項目を履歴に追記
- E に Origin 検査・書き込みの保護の記述はないため、N-1 の追記は不要

## FARC-K の現状

K-1・3・4・5・7・8・9 が残る(K-2・K-6 は欠番。それぞれ P-30・P-31 へ)。K-1・5・7・9 は DS(ゲート B・C 承認)の引用、K-3 はユーザー了承、K-4 は BAPI-K-2 の引用、K-8 は E2E を方針までとすること。writer の注記: K-5・K-7 は DS のゲート承認事項で境界に近く、R3 やゲート3で「承認済みの案」に寄せるべきとされるなら P に移せる

## 自己検算(writer)

ID 参照の未定義・未参照なし。欠番 ID(AAPI-K-9・AAPI-K-6・BAPI-K-6)は欠番経緯の説明のみ。EP は EP-01〜14、B 2.3 の code が E にすべて出て EP 列が 6.3 で B と一致。全画面の方針が 5.7 にある

## 未対応・ゲート3

- R3(E・F)は F 完成後
- ゲート3: FARC-P 全般(P-30・P-31 の区分移動を含む)、FARC-K-5・K-7 の区分、AAPI-P-37・38・39・40 に依存する P-16・P-29・P-31 と 6.3 の `job_not_found`
- 推測として明記した 3 点(Vue Query v5 `isLoading`、Playwright の時計操作、compose の `additional_contexts` 対応版)

## 次

- F(フロントエンドモジュール構成)を作成(同じ writer)。C は別 writer が執筆中
