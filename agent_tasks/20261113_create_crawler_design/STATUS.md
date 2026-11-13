# タスク状態

## 基本情報

- 状態: done
- 現在工程: 完了(v0.1 の6本+外部レビュー反映の v0.2 の6本と決定事項の文書を作成・レビュー済み。案・未決はユーザーの確認待ち)
- 最終更新: 2026-11-13
- 最新作業記録: 0013-make-connectors-independent-module.md

## 現在の状況

Crawler 設計書6本(`docs/v0.x/system-design/crawler/` 配下。v0.1 を作成後、外部レビューの反映で v0.2 を作成。v0.2 が最新)の作成とレビューが完了した。各文書のレビュー(R1・R2・R3・P4整合・R5)、最終レビュー(A・B)、タスクレビュー(task-reviewer)を通過し、0000 の完了条件7項目を満たしている。設計書はユーザー未承認の v0.1 で、設計書内の案・未決・既存設計との不整合(I-n)はユーザーの確認待ち。実装・Web Connector の詳細設計はスコープ外。

成果物(v0.2 が最新。v0.1 は変更していない。外部レビューの反映は 0011・0012):
- **2026-11-13 の追加指示(0013)**: `connectors` を `infrastructure` の外の独立したモジュール(アプリケーション機能の層)にした。反映先は `crawler/crawler-module-structure-v0.3.md`(module-structure だけ v0.3 が最新)と `crawler/crawler-design-decisions-v0.2.md`(decisions の最新)。確定は CM-K-10(独立したモジュールにすること、必要があれば `infrastructure` を使うこと)だけで、`opensearch`・`indexer_client` に依存しないことなどは案。ほかの設計書は変更不要
- `crawler/crawler-design-decisions-v0.1.md`(新規。実装着手のための決定事項の要約。0012)
- 以下 6 本は v0.2 が最新(`-v0.2.md`)。v0.1 の記載:
- `crawler/crawler-architecture-v0.1.md`(Indexer連携・課題の横断一覧 13.8 を含む)
- `crawler/crawler-api-v0.1.md`
- `crawler/crawler-module-structure-v0.1.md`
- `crawler/connector/connector-interface-v0.1.md`
- `crawler/connector/connector-file-system-v0.1.md`
- `crawler/connector/connector-web-v0.1.md`

## 次のアクション

0. (外部レビューの反映・0012)設計書は v0.2。新たな未決: CA-U-19(0 件列挙時の削除の保留)。ユーザーは 0010 の 2 点を確定済み
1. ユーザーが設計書をレビューし、0009 の「ユーザー判断事項の統合一覧」(優先度順)のうち残りを確認する。第1群(Q1「設定の削除」の解釈)と索引・マッピングの作成担当(CM-U-7 / CA-U-11 / I-6)は、2026-11-13 に案どおりで確定(0010)。次: 第2群の残り(source_id の文字種、glob と include_patterns の意味 など)
2. 判断・承認後の設計書変更は新版ファイル(v0.2 以降)を作る運用
3. 承認後に Crawler の実装タスクを新規作成(`scripts/new-task.sh`)

## 未解決事項

- ユーザー判断待ちの事項は 0009 の統合一覧を参照(第1群〜第4群)
- 設計書内の未決(v0.2): CA-U-1〜19(CA-U-11 は解消)、CI-U-1〜11、CAPI-U-1〜10(CAPI-U-1 は一部解消)、CFS-U-1〜7、CW-U-1〜20、CM-U-1〜9(CM-U-7 は解消)。既存設計との不整合: I-1〜I-8、I-10・I-11、I-20、I-30、I-40〜I-44(I-43 は解消済み)。I-9・I-50・I-51 は欠番(I-50・I-51 は他文書の修正で解消)
- 既知の限界: mermaid 未レンダリング、略称(「api」「arch」)の衝突、最終レビュー後の修正に対する独立した再レビューの省略(0009 の 2)

## ユーザー判断待ち

- 設計書の承認と、0009 の統合一覧の残りの判断(第2群: 実装前の判断 / 第3群: 実装時でよい / 第4群: Web 詳細設計の前)
- 回答済み(0010): 第1群 Q1「設定の削除」の解釈=案どおり、索引・マッピングの作成担当=推奨案どおり(opensearch-init に `loreley-sources` を追加し `loreley-jobs` を拡張)。設計書への反映は承認時に v0.2 でまとめて行う
- 未回答の判断は承認扱いにしない
