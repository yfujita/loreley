# 0006 再レビュー指摘(2回目)の修正 作業記録

## 概要
0005 の修正後に document-reviewer で再レビューした。Critical 0件、Important 1件、Suggestion 4件、Nitpick 4件。0005 の Important 8件は解消を確認(K8/P25、ID 体系、章番号参照、ロック確認の粒度、ソース削除のロック、K7/P16、マッピング JSON)。数値・状態値・API名・理由コード・リトライ既定値は SD v0.8 から変更なし。document-writer 1体が5文書をその場で修正した。

## 再レビューの指摘と対応
- [Important] `loreley-deletions` が状態名一覧の区分を示していない(P25 未反映)→ 第3章冒頭に「状態名の一覧と意味は案(architecture P25)。確定は4点まで」を追記、第9章に行を追加。
- [Suggestion] 未決に対応先がない → deletions に architecture U-14 の一部、U-20、API-U-10(+ architecture P1)を付与。
- [Suggestion] v0.1 への言及が本文冒頭に残る → 変更点の章に寄せた。18.4 の自己言及を削除。G-2・凡例の言い回しを「SD v0.8 に明示のない事項」に変更。
- [Suggestion] 行番号の扱いの自己矛盾 → 「行番号は変更点/18.1 に限った出典注記」と明記。
- [Suggestion] SD 依存の書き方 → api 0章に「SD に明記がない=出典 SD v0.8 にも明記がない」の定義を一度だけ置いた。api 5.4(389行目付近)は文言を変えず 0章の定義を適用。
- [Nitpick] texts 第7章見出しに「案を含む」、search-index の U-1/U-2 表記統一、architecture 1.3 の注記統一(Deletion Manager に K1、Status API は P1 参照)。

## 変更したファイル
- docs/v0.x/system-design/opensearch/schema/loreley-deletions-v0.2.md
- docs/v0.x/system-design/opensearch/schema/loreley-texts-v0.2.md
- docs/v0.x/system-design/opensearch/schema/search-index-v0.2.md
- docs/v0.x/system-design/indexer/indexer-architecture-v0.2.md
- docs/v0.x/system-design/indexer/indexer-api-v0.2.md
(各文書の変更点にも今回の修正を追記)

## 未対応事項・次にやること
- 今回の修正後の再読・再レビューは未実施(Important は1件で内容が追記のみのため、task-reviewer の確認で代替する)。
- 設計判断の未決はユーザー判断待ち: `loreley-texts` 廃止、`fetched_at`/`metadata` の所在、`url`/`path` の項目数、`summary_embedding`、原本サイズ超過の拒否主体、スナップショット項目名、API-U-13(ロック確認の部分結果)、API-U-14(ソース削除ロック)ほか。architecture 17.3、api 第7章、各 Schema 文書の未決表に集約済み。
- api 5.2〜5.5 のエンドポイント名・キー名・`failure_type` は提案(案)であり、確定ではない。
- 仮の前提 P1〜P3(Schema 範囲、版の付け方、改善の深さ)はユーザーが承認済み。
- 次: task-reviewer によるタスクレビュー。
