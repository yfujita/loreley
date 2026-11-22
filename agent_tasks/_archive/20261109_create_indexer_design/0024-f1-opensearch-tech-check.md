# 0024 F1 技術確認(OpenSearch の条件付き更新・削除・reindex)

## 概要
tech-advisor が OpenSearch 公式ドキュメントと UpdateHelper.java / UpdateRequest.java(main)で確認した。スナップショットは対象外(0023)。OpenSearch の確定バージョンは設計書に記載がなく、`latest` 前提。実装時に確定バージョンで再確認する。

## 結論(設計への反映)
1. **全文書き込みは (b) スクリプト update(`scripted_upsert` + `retry_on_conflict`)を推奨**。判定が保存済み値との比較だけで、1往復で原子的に完結し、競合時に大きな `_source` を読み直さない。判断は 0022 の未決(GET+if_seq_no かスクリプトか)に対する決定: **全文・`last_seen_at`・要約はスクリプト update、削除だけ `if_seq_no`/`if_primary_term`**。
2. Update API の `if_seq_no` は最初の内部 GET にだけ使われ、`retry_on_conflict > 0` および upsert との併用は拒否される。アプリが持つ seq_no を使うのは Index API(GET+index)と Delete API のみ。
3. `last_seen_at` の max 更新と要約の条件付き更新(`content_hash` と `text_hash` の一致)はスクリプト部分更新でよい。条件外れはスクリプト内で `ctx.op = 'none'`(noop)にする。スクリプトでは `detect_noop` は効かず、`ctx.op='none'` 明示が必要(既定は再インデックスされ `updated` になる)。noop は「条件不一致」と「変化なし」を区別できないため、両者を「適用されなかった」として扱う。
4. GET は既定でリアルタイム(refresh 不要)。`_source_includes` で取得項目を絞れる(削除前の再判定では `last_seen_at` だけ読めば足りる)。
5. `_reindex` は `_source` 必須。移行先のマッピングは自動コピーされないので先に作成する。`dynamic: strict` では移行先に全フィールドの定義が必要(欠けると該当文書は失敗)。既定の `conflicts` は abort。
6. `_source` は除外不可(update / reindex / get_document の前提)。サイズ増は実測項目(15.4)。update は文書全体を再インデックスするため、変化がなければ `ctx.op='none'` で書き込みを省く。
7. `delete_by_query` は snapshot 後に更新された文書は競合して削除されない(再登録が勝つ=安全側)。ソース削除は `conflicts=proceed` とし、`version_conflicts` が 0 でなければ再実行する。
8. 条件付き削除の 409 は「TTL 再確認後に更新された」ことを意味し、読み直して再判定する方式は妥当。リトライ上限超過は削除せず次の期限削除に委ねる。

## 実機確認が必要(設計書では未決として扱う)
- `scripted_upsert` 時の `ctx.op` 初期値、`upsert` の挙動。
- Delete の `not_found` の HTTP ステータス、存在しない文書への `if_seq_no` 付き操作の応答。
- 存在しない文書への upsert なし update は 404 → 要約の書き込みでは握りつぶす想定(実機確認)。
- `retry_on_conflict` の値(例 3〜5)と削除競合の読み直し上限は設計側で決める。
- Painless のコンパイル数(params を使いスクリプト本体を固定すれば回避できる見込み。未調査)。
- `_reindex` で `_seq_no` が振り直されるため、切替前に取った token は無効(409 読み直し方式なら実害なし)。
- 日付の比較形式(UTC・ISO 8601 固定)。

## 出典
OpenSearch 公式: Update / Index / Delete / Get / Delete by query / Reindex の各 API ページ、`_source` メタデータフィールド(docs.opensearch.org/latest/...)、UpdateHelper.java・UpdateRequest.java(main)、Elasticsearch 7.10 の裏取り。

## 変更したファイル
なし(調査のみ)。

## 未対応事項・次にやること
- F2: architecture v0.6 の作成(上記の決定を 5章・9.8・9.14・11章・15.4 に反映)。
