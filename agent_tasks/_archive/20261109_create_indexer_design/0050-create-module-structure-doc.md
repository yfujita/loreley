# 0050 Indexer モジュール構成設計書の作成

プランは 0049。ユーザーの具体的な指示(2026-11-10)を承認として扱った。

## 実施した作業
1. document-writer が `indexer-module-structure-v0.1.md` を作成した(元資料は architecture / api v0.9 と、実装タスクのディレクトリ構成案)。
2. document-reviewer がレビューした(Critical 1、Important 8、Suggestion 7、Nitpick 6)。
3. document-writer が Critical / Important と Suggestion の全項目を反映した。直さなかった指摘はない。

メインが文書を直接直した箇所はない(Read と grep による構成の確認のみ)。

## 成果物
- docs/v0.x/system-design/indexer/indexer-module-structure-v0.1.md(500 行)
  - 構成: 1 概要 / 2 構成図 / 3 モジュール一覧 / 4 ディレクトリ構成 / 5 モジュール詳細 / 6 シナリオ別の流れ(6.1〜6.6) / 7 依存ルール(R1〜R12) / 8 確認状況(M-1〜M-13)

既存の設計書(v0.9 以前)、PD、0000 は変更していない。

## 主な判断(すべて案。ユーザー未確定)
- モジュールは実装タスクの構成案どおり 5 つ(M-1)。
- 構成案にない HTTP の受け口を `src/http/` として追加(M-2)。`apps/api` と紛らわしいので `api/` にしなかった。
- API の担当: バッチ登録と `last_seen_at` 部分更新は `indexing`、開始通知・終了通知・Status API・ソース削除 1〜3 は `deletion`(M-3、M-4)。
- 受理条件の判定は `deletion` が持ち、`indexing` が照会する(M-5)。
- 依存は上位から下位のみ。`deletion` / `summarization` / `extraction` は互いを呼ばない(R4、R5)。

## レビュー指摘の主な修正
- 1章の「OpenSearch への書き込みは Indexer だけ」は誤りだったので、検索インデックスと `loreley-deletions`(仮名)に限定した。
- R9(書き込みはすべて条件付き)に、ソース削除の `delete_by_query` を例外として明記した。
- 区分を arch の語彙(確定 K / 案 P / 未決 U / 導出)に揃えた。「既存」は廃止した。
- 重複と長い表のセルを解消した(依存先と元の節は 5 章に一本化、4 章の表はツリー図に置き換え)。
- 6.2 の図を、受付と非同期の判定・実行の 2 枚に分けた。

## 未対応事項
- **ユーザー判断待ち**: M-1〜M-13 は未確定。特に、`http/` の追加と名前(M-2)、受理条件の判定を `deletion` に置く案(M-5)、起動時の整理の順序(M-10)、依存の向き(R4〜R6)、起動処理の置き場(M-13)。
- **既存の未決のまま**: ソース削除 2・3 のロック所有確認の担当(arch U-4、api API-U-14)、メンテナンスフラグの確認(U-12)など。
- **Mermaid の描画は未確認**。Obsidian で崩れがないか確認が必要。
- **再レビュー・タスクレビューは未実施**: レビュー後の修正版は再レビューしていない。task-reviewer も実行していない(追加の文書 1 本のため省略。必要なら実施する)。
- 5.3 の `last_seen_at` 部分更新の項目と、変更なし文書の補完 Update の項目が一部重なる(内容は正しい。冗長なら削る)。
- 実装タスク(20261110_implement_indexer)が参照する設計書のパス(`opensearch/loreley-deletions-v0.9.md` など)は、実際の配置(`opensearch/schema/`)と異なる。本書の範囲外。
