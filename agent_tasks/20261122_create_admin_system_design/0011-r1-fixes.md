# 0011 R1 指摘の修正(A・B)

日付: 2026-11-22
担当: document-writer(メインが記録)

## 変更ファイル

- `docs/v0.x/system-design/api/api-base-design-v0.1.md`(328 行)
- `docs/v0.x/system-design/api/admin/admin-api-v0.1.md`(1323 行)
- E・agent_tasks は変更なし。承認済みの EP 番号・パス・code 名・項目名は不変(例外は依頼どおり `read_only` の削除)。不採用項目の再導入なし。不対応にした指摘なし。

## Important の対応

- I-1 `job_id`: Crawler URL には `source_id`・`job_id` とも全文字をパーセントエンコード(`safe=''`)。検証規則は不変。B 2.12・9.1・A 5.3・11.10。crawler-api 3.3「パスの扱い」(TestClient の実測で契約外、実機未確認。`%2F`→404 `not_found`、`%3F`・`%25`・`%2e%2e`→400)。400・404 `not_found` は 502 `crawler_error`。新規 AAPI-U-12
- I-2 `config_invalid`: 前半が `connector_config` 自身なら `field="connector_config"`(プレフィックスなし。画面は上部アラート)。実物(`connectors/filesystem/config.py`、FS v0.3 2.2)で確認。`detail` は日本語固定文で完全一致照合(AAPI-U-2 に併記)。B 2.5・11.7 #4 に例を追加。画面仕様との食い違いは他になし
- I-3: `config_invalid` が先に返りうるのは 409 `source_deleting` に対してだけ。設定がなければ検証せず 404、種別が読めなければ 500(Admin では 502)。B 3.4・9.2.5 を訂正。crawler-api 4.4.3 の文言の曖昧さを申し送り候補に
- I-4: 「ゲート2の回答で採用が選ばれなかったため不採用として扱った(解釈。ゲート3で確認)」に統一(A 冒頭・2.3・BAPI-P-15・BAPI-U-8、B 冒頭・2.10・AAPI-P-15・11.7 #19・#23)。リスクは「受け入れてよいかはゲート3で確認」
- I-5(区分): AAPI-K-9 の出典を画面仕様 dashboard #26(ゲート C)・admin-view 3章(ゲート B)に訂正。時刻 ISO 8601 UTC は BAPI-K-6 を欠番にして **BAPI-P-20(承認済みの案。ユーザー確認はゲート3)** へ。AAPI-K-6 は欠番にして **AAPI-P-35(承認済みの案・ゲート1)** へ。AAPI-K-5 は K のまま「回答は明示。確定は方式のみ」と注記。BAPI-K-3 は「Indexer・Crawler と揃える」のみ K、個別選定は **BAPI-P-21(導出。出典 pyproject.toml)**。AF-19 は表示のみは **AAPI-P-36(承認済みの案・ゲート1)**。「Admin API が書かない」は AAPI-K-1(CAPI-K-5)に残す
- I-6: 本文が空なら Content-Type を問わず許し `{}` として扱う(B 2.12)。A 2.3 の BAPI-U-8 に、単純なリクエストで届きうる EP を列挙(本文なし POST・DELETE の EP-05 全文書削除・EP-06 `force_delete` 既定 false・EP-07 取消・EP-08 ロック解放。EP-03・04 は Content-Type 必須で対象外。DNS rebinding なら全 EP)。軽い緩和は足さず、ゲート3の確認事項として BAPI-U-8 に残す
- I-7: EP-02 の例を検索インデックス失敗のパターンに差し替え

## Suggestion / Nitpick の対応(要旨)

S-1 `unavailable` のキーを正式な項目パスに(`items[].last_crawl.stalled` など)/ S-2 `orphan`=取得から 60 秒超・`just_acquired`=60 秒以内で排他、`status`/`job_type` が読めなければ `unknown`、判定順はロック文書→ジョブ記録 / S-3 EP-13 トップ `checked_at`=全確認が終わった時刻、`id` の説明 / S-4 EP-12 例の整合 / S-5 十進数変換の明記、小数第 3 位以下の保存値を再保存すると `format` エラーの注意と画面で丸めさせる代替案=**AAPI-P-38(案。ゲート3)** / S-6 `ttl` 下限 1 は **AAPI-P-37(案。ゲート3)** / S-7 `reason=read_only` を Admin API から削除(B 2.6・9.2 の Crawler 由来の行は残す) / S-8 A 5.6 の 93 秒の出典・導出を訂正 / S-9 C への引き継ぎに順序・排他定義 / S-10 EP-02 `lock.job.lease_expires_at` は読めなければ `null`(番兵は Crawler 409 の `existing_job` のみ) / S-11 A 5.6 に D1 `opensearch` 確認 3 秒・再試行なし / S-12 確認先 URL は環境変数のみ、プローブはリダイレクトに従わず 3xx は `unexpected_status` / S-13 AF-5 との差を I-75 に / S-14 AF-U の状態表を B 11.6 に / S-15 J1「開始」列=`queued_at` / S-16 `source_id` の重なり解消 / S-17 A 10.3 にゲート3の対象表(BAPI-P-6〜8・11・13・15〜21、BAPI-U-8)、B 11.9 に AAPI-P-3 ほか / Nitpick 全件

## E に影響する点(E 側の追従が必要)

- `unavailable` のキーが正式パス(`items[].last_crawl.stalled` など)に変更 → E 5.7 付近(341〜347 行)の旧キー記述を更新
- `read_only` を Admin API の `reason` から削除(E は 430・721 行で既に「Crawler の `read_only` は 502」としており変更不要と見られる。確認)
- `lock_state`: `orphan`/`just_acquired` が排他、`unknown` の追加条件
- 本文が空なら Content-Type 不問、あれば `application/json` 必須
- `ttl` 下限 1(画面仕様と一致)、`ratio_threshold_percent` の小数第 3 位以下の注意(画面が注意を出し丸めを確認させる=AAPI-P-38)
- `config_invalid` で `field="connector_config"` のとき上部アラート
- EP-13 トップ `checked_at`、EP-02 `lock.job.lease_expires_at` の null

## 申し送り候補の増減

- 追加: crawler-api 4.4.3 の文言の曖昧さ、機能設計 AF-5 の追記(I-75)、Crawler の `job_id` 特殊文字の実機確認(AAPI-U-12)、機能設計 AF-18・20 と画面仕様 #26・admin-view 3章の出典整理
- 減少: なし

## ゲート3でユーザー確認(writer 集約)

1. #19・#23 の「不採用として扱った(解釈)」、BAPI-U-8 のリスク受容、軽い緩和を足すか
2. BAPI-P-20(時刻)・AAPI-K-9(更新間隔 30 秒・外部リンク)のユーザー確認の有無
3. AAPI-P-37(`ttl` 下限 1)
4. AAPI-P-38(再保存時の対応方針)
5. AAPI-P-3(EP 一覧)をゲート2の承認として扱った解釈
6. BAPI-P-21(個別技術選定を導出とすること)

## writer の自己検算

2.3 の code 表と各 EP の不一致 0、EP-01〜14 と見出し 1:1、ID 参照の未定義 0・未参照 0(欠番・不採用行は参照あり)、JSON 例 16 ブロックがパース可・状態の一貫、`-K-` の出典、不採用項目は記録以外に残存なし

## 次

- R1 再確認(reviewer が差分を確認)と、E を B の変更に追従させる作業を並行
- 解消後 C・D、F
