# 0028 R2 指摘のうち A・B 側の修正

日付: 2026-11-23
担当: document-writer(B 担当。メインが記録)

## 変更ファイル

A(`api-base-design-v0.1.md`)・B(`admin-api-v0.1.md`)のみ。C・D・E・F・agent_tasks は無変更。EP 番号・パス・承認済みの code 名・項目名は不変。新規・変更は案(ゲート3)で、承認済みの案の引用は確定にしていない。

## 修正内容

- **I-1(`job_id` の符号化)**: 「`quote(value, safe="")` の後に `.` を `%2E` に置換」(`.` を符号化せず urllib3 がドットセグメントを除去して `..` が `/cancel` に崩れるため。urllib3 2.8.0 で確認済み)。B 2.12・9.1・AAPI-P-24・AAPI-U-12・11.10、A 5.3。11.10 の C 向け期待値は「スタブが `%2E%2E` を受ける」。代案(`.`・`..` だけの `job_id` を検証で拒否)は採らず、ゲート3の確認事項として B 11.9 に 1 行(AAPI-P-24 関連、AAPI-U-12)
- **I-3(urllib3 の import)**: A 3章・7章に、HTTP のヘルスプローブ(urllib3)と OpenSearch の `cluster.health` プローブ(opensearchpy)を区別。例外として `urllib3.exceptions` の import を `infrastructure.opensearch`(`failure.py`・`health_probe.py`)に限って許す(新規 **BAPI-P-22**)
- **I-7(索引名の渡し方)**: 実物(`init-indices.sh`、`compose.yaml`、Indexer・Crawler の `config.py`、`LORELEY_INDEXER_SEARCH_INDEX_NAME`)で確認。A 4・A 8: `sources`・`jobs` は Crawler と同じ変数、`deletions` は Indexer と同じ変数、検索エイリアスは init の `SEARCH_INDEX_ALIAS`(既定 `loreley-documents`)と Indexer の `LORELEY_INDEXER_SEARCH_INDEX_NAME` と同じ変数から。init の `SEARCH_INDEX_NAME` は実体名(既定 `loreley-documents-000001`)で別物なので `api` に渡さないと明記。現在の compose は Indexer に検索・削除の索引名を渡していないため infra の前提作業で揃える(フェーズ5の申し送り候補)
- **I-9(タグと Repository)**: OpenAPI のタグは 6 種で、操作の対象のリソースで決める(EP-06・08=`sources`、EP-07=`jobs`)。B 1.1 の「領域」列の「クロール操作」は章立ての区分でタグではないと明記。A 5.4(**BAPI-P-23**)と B 1.1。A 7章・BAPI-P-18 の「Repository」→「Reader」
- **S-1**: A 4 に `CRAWLER_URL`・`INDEXER_URL` は MVP では http 限定(**BAPI-P-24**)。**S-8**: A 4 の `WEB_DIST_DIR` の既定を「C 7.2(案。固定パスは D・E で確定)」に参照変更。**S-12**: A 5.1 の `no-store` は API の応答だけ(静的アセットは対象外)。**N-2**: A・B の「作成予定」→「作成済み」

## 新規・変更 ID(いずれも案。ゲート3)

- 新規: BAPI-P-22(`urllib3.exceptions` の import の許可範囲)、BAPI-P-23(タグ 6 種の割り当て)、BAPI-P-24(Crawler・Indexer への接続を http 限定)
- 変更: AAPI-P-24(符号化方式)、AAPI-U-12(内容更新)、BAPI-P-18(Reader の語)
- A 10.3 のゲート3対象表に BAPI-P-22・23・24 を追加

## C・D・E・F への影響

- C: 4.8 と 11 の観点3 を「`quote(safe="")` + `.`→`%2E`」に、索引名の渡し方(10 章・7.2・I-90)を検索エイリアス変数の区別に合わせる(C・D の担当 writer が同時に修正中)
- D: タグ 6 種と `urllib3.exceptions` の許可は D の記述と同じ案
- E・F: 影響なし

## 自己検算(writer)

2.3 の code 表と EP のエラー表の不一致 0、EP 14 本、ID 参照の未定義・未参照 0、JSON 例パース可、表の列数は A 12 表・B 60 表で崩れ 0(バッククォート内の `|` も区切りとして数える方式)、不採用項目は記録・改訂履歴のみ、「作成予定」「Repository」の旧記述 0

## 次

C・D の修正(別 writer)の報告待ち → R2 再確認 → フェーズ5
