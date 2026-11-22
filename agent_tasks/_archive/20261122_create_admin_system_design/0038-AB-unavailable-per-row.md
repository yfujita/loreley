# 0038 B・A の修正(一覧の `unavailable` を行単位にする)

日付: 2026-11-23
担当: document-writer(B 担当。メインが記録)

## 変更ファイル

A(`api-base-design-v0.1.md`)・B(`admin-api-v0.1.md`)のみ。C・D・E・F・agent_tasks は無変更。EP 番号・パス・承認済みの code 名・項目名は不変。`-K-` は増やしていない。

## 決めた規則(B 2.2。新規 AAPI-P-42)

- 一覧の EP(EP-01・09・11): 各 `items[i]` に `unavailable` を持たせる(常に存在。失敗がなければ `{}`)。キーは行の中の項目の相対パス(EP-01: `last_crawl`・`last_crawl.stalled`・`last_completed_at`・`delete_job`・`delete_job.stalled`・`document_count`、EP-09: `stalled`、EP-11: `existence`)、値は理由コード。最上位の `unavailable` は行に属さない項目(EP-11 の `tab_counts.<タブ>`・`document_count`)だけ。EP-01・09 では常に `{}`。`items[].…` 形式のキーは廃止
- 単一オブジェクトの応答(EP-02・10・12・13・14)は不変
- 読み方: 「`null` でキーあり」=取得できなかった、「`null` でキーなし」=値がない。行ごとに成否が分かれる読み取りは失敗した行だけにキー、一括検索の全体や主たる読み取りの一部が失敗したときは全行に同じキー
- 2.2 に、`source-a`(未実行でキーなし)と `source-b`(読み取り失敗でキーあり)を区別できる JSON 例を追加

## 変更章(B)

改訂履歴・凡例(承認済みの案(ゲート3)を後から修正した場合の区分表記を追記)/ 1.4 の検算表(行ごとの「取得できません」=`items[].unavailable`)/ 2.2 書き直し / 2.9(`stalled` のキー)/ 2.11(行 DTO として `SourceListItem`(EP-01)・`JobListItem`(EP-09 = `JobBrief` + `unavailable`)を追加。`JobBrief` 自体は `unavailable` を持たず、入れ子の行では相対パス `last_crawl.stalled`)/ 3.1(EP-01。行単位の `stalled=null`(ロック読み取りの失敗)はその行の `unavailable.last_crawl.stalled`(または `delete_job.stalled`)で、他の行に影響しない。JSON 例更新)/ 5.1(EP-09)/ 6.1(EP-11。`existence` の失敗は一括検索の全体=全行、文書単位=その行だけ。最上位のキー)/ 10.2 / 11 章(AAPI-P-16・25・27・30 の記述と区分を直し、11.9 に AAPI-P-42 の行、11.10 の (e) を更新)

A 5.2: `unavailable` は一覧の EP は各行、単一の応答は最上位に持つ旨を一句追加(正本は B 2.2)

## ID

- 新規 AAPI-P-42: 承認済みの案(ゲート3)の修正(PR #10 のレビュー指摘への対応。2026-11-23)
- 同じ区分に修正: AAPI-P-16・25・27・30

## C・D・E・F が追従すべき箇所

- C: 5.4・5.8・5.10(一覧の組み立てを行単位に。キーは相対パス。最上位は行に属さない項目だけ)、3.3 の R-3・R-9・R-11(サブ要求ごと・文書ごとの失敗は失敗した行だけにキー、全体の失敗は全行)、テスト観点 6(「`items[].…` の旧表記が出ないこと」→「行の `unavailable` の相対パス」)
- D: DTO に行の `unavailable`(`SourceListItem`・`JobListItem`・EP-11 の行)、`unavailable` の組み立て 1 か所(一覧の行単位と単一応答の最上位を区別)
- E: 5.7・5.9・6 章の `unavailable` の引き方(一覧は `items[i].unavailable`、最上位は行に属さない項目だけ)
- F: `unavailable.ts` の `cellState`・`expectedFields`(FMOD-P-14・P-31 とテスト)を行単位に。行ごとの「取得できません」は `null` かつ行の `unavailable` にキーがあるときだけ
- 型生成: OpenAPI の DTO に一覧の各行の `unavailable` が追加される

## 自己検算(writer)

2.3 の code 表と EP のエラー表の不一致 0、EP 14 本、ID 参照の未定義・未参照 0、JSON 例 17 ブロックがパース可、表の列数は A 23 表・B 61 表で崩れ 0(バッククォート内の `|` も区切りとして数える)、旧キー(`unavailable` と一緒に使う `items[].…` 形式)の残存 0、不採用項目は記録のみ

## 未対応事項

C・D・E・F の追従(担当 writer)。実機での `msearch`・`mget` の失敗の形は AAA-U-2 のまま
