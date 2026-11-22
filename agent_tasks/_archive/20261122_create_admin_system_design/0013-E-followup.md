# 0013 E を B の R1 修正に追従させる

日付: 2026-11-22
担当: document-writer(E 担当。メインが記録)

## 変更ファイル

- `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.1.md`(757 行。E のみ。A・B・agent_tasks は変更なし)
- 追従の基準は B(1323 行)・A の R1 修正版(0011)。**B は N-1〜N-5 の修正が進行中(0012)なので、完了後に差分の追従が再度必要**(特に EP-07 の `job_id` の 404 写像=AAPI-P-39、AAPI-K-9 の区分変更、`unavailable` キーの表記)。

## 修正内容(章)

- 0章・12.6: 改訂履歴(B・A の R1 追従 9 項目)
- 4.3: ルートの `:jobId` も URL エンコード(`job_id` は `%`・`?`・`#` を含みうる。B 2.12)。生成 SDK のエンコード挙動は FARC-U-18
- 5.7: `unavailable` のキーを正式パスに(S1: `items[].last_crawl`・`items[].last_crawl.stalled`・`items[].delete_job.stalled`・`items[].document_count`、S2: `last_crawl.stalled`・`delete_job.stalled`、J1: `items[].stalled`)。S2 の `lock.job.lease_expires_at` は読めなければ `null`(番兵は出ない)。D1 の行に `id` が `web` を含み compose のサービス名ではないこと、トップ `checked_at` は最終取得成功日時(`dataUpdatedAt`)と別であること
- 5.9: 番兵 `0001-01-01T00:00:00.000Z` は 409 の `details.existing_job.lease_expires_at` だけ。一覧の `unavailable` キーは「全件または 1 行でも失敗」を表し、キーがあり行が `null` なら「取得できません」(安全側)
- 6.3: `config_invalid` で `field="connector_config"`(プレフィックスなし)または `detail` が照合できないときは上部アラート。`lock_state` の排他定義を反映(`orphan`=60 秒超、`just_acquired`=60 秒以内、`unknown` はジョブの `status`・`job_type` が読めない場合も)。`just_acquired`・`unknown` ではロック解放へ導かず待って確認するよう案内(案)
- 6.4: `connector_config` 自身の `field` は上部アラート。`read_only` は 502 扱いで整合済み
- 7.2・7.5: `ttl` 下限 1(AAPI-P-37。案)、本文があるときは `Content-Type: application/json` を付け、空なら不問
- 7.7(新設): 保存値のしきい値が小数第 3 位以下を持つとき(FARC-P-29。案)。S4 は丸めた値(四捨五入案)を入れて注意を出し保存を確認とみなす。S2 は丸めず表示。文言は画面仕様に委ねる
- 12.1: B 11.1・11.2・11.6・11.7 の照合を完了(食い違いなし)

## ID の変更

- **FARC-K-2 を欠番にし FARC-P-30(承認済みの案。ゲート1)へ移動**: 技術スタックの構成要素 8 点は 0000 が「技術スタック案」と書いており、0001 の「確定した要件」はユーザーの個別回答ではないため(B の BAPI-K-3 の整理に合わせた)。2.1 の表の「確定(FARC-K-2)」は「承認済みの案(ゲート1。FARC-P-30)」へ
- FARC-K-7 はブラウザのローカル時刻表示(DS 4.9・ゲート C #36)のみに絞り、API の UTC ISO は BAPI-P-20(承認済みの案。ユーザー確認はゲート3)を参照。K-6 の出典は AAPI-K-9 と同じ整理(dashboard 4.1・admin-view #26・#8・#33)。K-1・3・4・5・8・9 は変更なし
- 新規: FARC-P-29(しきい値の丸め)、FARC-P-30、FARC-U-18(生成 SDK のパスエンコードと `job_id` の挙動)。更新: P-16(`ttl`≥1)、P-24、P-27、U-12。I-87 に S4 のしきい値の小数第 3 位以下を追加。新規 I-n なし

## F への引き継ぎの変更

- `job_id`・`source_id` のパスエンコードをどの層(生成 SDK かラッパー)で保証するか決める(FARC-U-18)
- `unavailable` を引く関数の置き場に、正式パス形式(`items[]` 付き)と「一覧でキーがあり行が `null` なら取得できません」の規則を持たせる
- 日時整形は、番兵を判定する 1 か所に置く(409 の `existing_job` 用)
- S4 のフォームモデルに、しきい値の丸め注意の状態を持たせる

## 申し送り候補の増減

- 追加: 画面仕様にしきい値の丸め注意の状態を追記(I-87 拡張)、DS 10.1 の技術スタック「案」のうち FARC-P-30 の 8 点がゲート1で承認済みになった旨の反映
- その他は 0009 のとおり

## 自己検算(writer)

ID 参照の未定義・未参照なし(欠番 BAPI-K-6・AAPI-K-6 は 12.6 の説明のみ)、EP-01〜14 のみ、B 2.3 の Admin 固有 14 種+共通 6 種が 6.3 に現れ EP 列が一致、全画面の方針が 5.7 にある

## 未対応・ゲート3

- R3(E・F)は F 完成後。推測として本文に明記した 3 点(Vue Query v5 の `isLoading`、Playwright の時計操作、compose の `additional_contexts` 対応版)
- ゲート3: FARC-P 全般(P-30 の区分変更を含む)、FARC-K-7 の整理、AAPI-P-37・38 に依存する P-16・P-29
- B の N-1〜N-5 修正の完了後に、E の追従差分を確認(特に AAPI-P-39=EP-07 の `job_id` 404 写像)
