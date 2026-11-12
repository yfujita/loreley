# 0013 レビュー R3 の再レビューと対応

日付: 2026-11-12
再レビュー: document-reviewer(読み取りのみ)/ 対応: メインエージェント

## 再レビューの判定

R3 の Important 6 件(I1〜I6)と Suggestion の大半は指摘どおりに解消(出典の一貫性、uv 未導入・uv.lock 未生成、K48、数値、条件の明記など)。**Critical なし。新たな Important は 1 件**(503 の実機再現を入れたことによる文書間の矛盾)。作業記録 0009・0012 と突き合わせて、数値・経路の食い違いはなかった。

## 新規指摘と対応

| 重要度 | 指摘 | 対応 |
| --- | --- | --- |
| Important N-I1 | `index_not_found_exception` が、結果記録 5 章(実機で観測)と 4.3 (9)・tests README・apps/indexer README(未実施)で食い違う | **対応済み**: 4.3 (9)・tests README・apps/indexer README を「Status API の GET(`loreley-deletions` を削除した後)を手動で再現して観測した(結合テストには含めていない)。`update` 系・書き込み系の `index_not_found_exception` と `result:not_found` は未実施」に統一 |
| Suggestion S-A | 「実装担当も同じ結果を報告」の根拠が作業記録にない | **対応済み**: 該当の記述を削除し、「メインエージェントが手動で再現。結合テストには含めていない」に統一(実機再現の根拠はメインエージェントの再現のみ) |
| Suggestion S-B | 4.4 の「各項目の実行後に残りがないことを確認」は 0009 より広い | **対応済み**: 「成功経路の終了後と、全検証の終了後」に修正 |
| Suggestion S-C | 4.4 の失敗経路などは R2 修正前のスクリプトでの確認 | **対応済み**: 「失敗経路・シグナル・`--keep` は修正前の版で確認。修正後に再確認したのは成功経路(③)と空白だけの `LORELEY_IT_PYTEST_CMD`」と明記 |
| Nitpick N-A | 章番号の誤り(「4 章の発見事項 1」→ 5 章、「4.1 の所要時間」→ 3 章) | **対応済み**。tests README の「未生成」の説明は「依存は固定されない。uv が `uv run` 時にロックを自動生成するかは未確認」に修正 |
| Nitpick N4 | `--collect-only` をスクリプト経由で渡すとスタックを起動する | **対応済み**(README に一文追記。収集時に疎通確認が走らないかは未確認と明記) |
| Nitpick N5 | 外部事実(2.19 は maintenance 系列、opensearch-py の CI)の出典 | **対応済み**(「調査による。出典の再確認はしていない」を compose README に追記) |
| Nitpick N2(GB/GiB)、N3(「取得のたびに変わらない」) | 値が近い/ダイジェスト非固定の判断を明記済み | **見送り**(再レビューでも見送りでよいとの判断) |

## 状態

R3 完了(Critical なし、Important は対応済み)。再々レビューは不要と判断した(新規の Important は文書間の記述合わせのみで、修正内容は上表のとおり機械的)。

## 未対応事項・次にやること

- **uv の導入待ち**(`brew install uv` は Rust 等のソースビルド中。ユーザーは待つ方針)。導入後: `tests/integration` で `uv lock`、スクリプトを既定(uv 経由)で通す(2 回連続成功)、pytest の rootdir・設定の読み込みを確認、結果記録 3・4・6 章と README の uv の注記を更新。
- タスクレビュー(task-reviewer)→ 完了チェックリスト → 最終報告。
