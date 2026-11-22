# 0007 タスクレビューと完了 作業記録

## 概要
task-reviewer によるタスク全体のレビューを実施。Critical・未解決の Important はなし(軽微な修正で完了可)。要件の3種類の成果物(Indexer architecture、Indexer api、OpenSearch Schema)が v0.1・v0.2 で揃っていることを確認。

## 承認の記録(0001 の補足)
- 0001 の冒頭は「承認待ち」のままだが、ユーザーは 0001 の提示後に「承認」と回答済み(仮の前提 P1〜P3 を含むプランを承認)。既存記録は書き換えないルールのため、本記録で承認の事実を残す。
- 0005 の「Important 8件」は、一覧上は実質9項目(うち1件は別項の重複)。

## プランからの乖離
- v0.2 は未公開ドラフトのため、レビュー指摘(0005・0006)は新版を作らず v0.2 をその場で上書き修正した。プランの「版ごとに新ファイル」からの運用上の逸脱。v0.1 は不変。
- 0006 の修正後は document-reviewer の再々レビューを行わず、task-reviewer の確認(loreley-deletions と architecture の P25 区分の突き合わせ)で代替した。

## レビュー指摘への対応
- Suggestion(承認記録、Important 件数、上書き修正の明示、再レビュー代替の通知): 本記録とユーザー報告で対応。
- Nitpick(loreley-deletions L83 の `discarded` の細部が「確定は4点まで」の外側にある): 表全体が案(P25)のため矛盾なし。対応しない。

## 成果物(すべて新規作成)
- docs/v0.x/system-design/indexer/indexer-architecture-v0.{1,2}.md
- docs/v0.x/system-design/indexer/indexer-api-v0.{1,2}.md
- docs/v0.x/system-design/opensearch/schema/search-index-v0.{1,2}.md
- docs/v0.x/system-design/opensearch/schema/loreley-texts-v0.{1,2}.md
- docs/v0.x/system-design/opensearch/schema/loreley-deletions-v0.{1,2}.md

## 未対応事項(ユーザー判断待ち)
- `loreley-texts` を廃止するか(architecture U-21 ほか)
- `fetched_at` / `metadata` の保存先(architecture U-16)
- `url` / `path` を1項目にするか2項目にするか
- `summary_embedding` の位置づけ(MVP 未使用の予約項目として残すか、外すか)(architecture U-25)
- 原本サイズ超過を Crawler と Indexer のどちらが拒否するか(architecture U-5)
- 設定スナップショットの項目名(architecture U-14)
- API-U-13(バッチ途中でロックを失った場合の部分結果)、API-U-14(ソース削除ジョブのロック)
- 状態名の一覧(P25)ほか、案のまま確定していない項目(architecture 17.2、api 第7章、各 Schema 文書の確認状況表)
- api 5.2〜5.5 のエンドポイント名・キー名・`failure_type`、マッピング JSON の型・`offsets` 対象は「提案(案)」。
- 日本語アナライザ、BM25 重み、本文サイズ上限などの数値・設定は未決のまま。
- Crawler 設計書(`loreley-jobs` / `loreley-sources`)、Search API・MCP の設計は本タスクの対象外(別タスク)。
- SD v0.8 は修正していない(破棄予定のため反映不要)。
