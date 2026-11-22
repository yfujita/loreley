# 0014 R1 再確認の新規指摘(N-1〜N-5)の修正

日付: 2026-11-22
担当: document-writer(メインが記録)

## 変更ファイル

A(`api-base-design-v0.1.md`)・B(`admin-api-v0.1.md`)のみ。agent_tasks・E は変更なし。承認済みの EP 番号・パス・code 名・項目名は不変。不採用項目の再導入なし。

## 修正内容

- **N-1**: ブラウザの単純なリクエストで届くのは本文なし POST の EP-05・06・07。EP-04(PUT)・EP-08(DELETE)は preflight が要り CORS 未許可なので届かない。EP-08 は DNS rebinding でのみ到達。DNS rebinding なら全 EP が対象。EP-03(POST)は Content-Type 必須で単純なリクエストでは書けない。A 2.3・BAPI-U-8、B 2.10 を統一
- **N-2**: `unavailable` キーを正式パスに(B 3.1 EP-01 表、6.1・AAPI-P-30 の `items[].existence`、AAPI-P-25、2.9 の `stalled`)。単一応答の EP のパスは不変。旧表記は grep で 0 件
- **N-3**: **AAPI-K-9 を欠番にして AAPI-P-40(承認済みの案。画面仕様ゲート B・C の承認事項の引用。ユーザー確認はゲート3)へ**。A の凡例に「既承認文書の承認済みの案の引用は確定にせず、出典を区分欄に書く」を追加(BAPI-P-20 に適用)。AAPI-P-7 に「`ttl` 下限を除く(P-37)、`min_delete_count` は 0 以上」と注記
- **N-4**: 「単一プロセス」は「Crawler・Indexer も単一プロセスであることによる導出」(A 技術スタック表、BAPI-P-21)
- **N-5**: Crawler がパスの `job_id` を理由に返す 400 `invalid_request`・404 `not_found` は、EP-07 では 502 でなく **404 `job_not_found` に写す**(新規 **AAPI-P-39**。案。ゲート3)。B 2.12・2.6(写像表に 1 行追加し 502 の行から `job_id` を除外)・9.2.2・4.2(EP-07 のエラー表)・AAPI-U-12。`source_id` は検証済みのため 502 のまま。EP-10 は直読みで 404 `job_not_found` と既に揃う
- Nitpick: 11.9 の AAPI-U-12 重複を AAPI-U-9〜12 の行にまとめた。A 5.6 の「約 93 秒」は crawler-architecture 10章の記述と 11章の値(クライアントのタイムアウト 30 秒・最大試行 3 回)からの導出と出典を訂正

## 新規・変更 ID

- 新規: AAPI-P-39(取消の `job_id` 起因の Crawler 応答を 404 に写す。案。ゲート3)、AAPI-P-40(更新間隔 30 秒と外部リンク。承認済みの案(引用)。ユーザー確認はゲート3)
- 欠番: AAPI-K-9(→P-40)
- 変更: AAPI-P-7・P-25・P-30・U-12、BAPI-P-21・U-8

## E・C に影響する点

- E: EP-07 の 404 `job_not_found` に「`%`・`?` を含む `job_id`」が加わった(表示は既存の 404 の扱いで足りる)。`unavailable` の正式パス(0011 の追従で対応済みか確認)。単純なリクエスト・Origin の記述が E にあれば N-1 に合わせる。AAPI-K-9 の参照は AAPI-P-40 に読み替え
- C: EP-07 だけ、パスの `job_id` を理由とする Crawler の 400・404 `not_found` を 404 に写す処理(AAPI-P-39)。`job_id` の全文字エンコード(I-1)。テスト観点に「CORS を許可しないこと」を足せる

## 自己検算(writer)

2.3 の code 表と各 EP の不一致 0(`crawler_*` 4 種は共通行で代表)、EP-01〜14 と見出し一致、ID 参照の未定義 0・未参照 0、不採用項目は記録以外に残存なし、`unavailable` の旧キー 0 件、JSON 例 16 ブロックがパース可

## 次

- C(admin-api-architecture)を作成(B の 11.10 と、0010〜0014 の引き継ぎを含める)。E の差分追従(AAPI-P-39・P-40 ほか)を並行。その後 D と F
