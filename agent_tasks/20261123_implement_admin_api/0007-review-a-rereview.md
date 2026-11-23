# 0007 レビュー R-A 再レビューの結果

日付: 2026-11-24

## 結果

比較基準 `2c29b7e..aa88b9b`(指摘対応コミット)。同じレビュアー(`code-reviewer`・`test-reviewer`)で再レビューした。

- **code-reviewer: 指摘なし**(Critical 0 / Important 0 / Suggestion 1 / Nitpick 1)
  - 前回 Important(R-3・R-7 の `track_total_hits`)は解消。`queries.py` の本文、`parse_uncounted_search`、`jobs_reader.py` の切り替えを確認。総件数を使う側(R-1・R-6・R-9・R-10)の gte 検証は維持
  - mget ログ集約・docstring・`PageParams` 改名・`_declares_more_than`(先頭ゼロ・19 桁)・`ErrorCode` 全 16 件の固定文に退行なし
- **test-reviewer: 指摘なし**(Critical 0 / Important 0 / Suggestion 3 / Nitpick 2)
  - I-1〜I-4 は実質的に解消。ミューテーションで検出力を確認(`run` 同期化 → 20.18 秒で failed、ロガー緩和 → failed、本文上限の各ミューテーション → 検出)
  - pytest 1150 passed、ruff・format OK、concurrency 5 回連続 18 passed、逆順実行 1150 passed。新たな flake・グローバル状態汚染なし

## 判断(Suggestion・Nitpick)

P3 の実装時に一緒に取り込む(小さく安全なもの):
- `parse_uncounted_search` の docstring に「総件数を使わない本文(`track_total_hits: False`)専用」と 1 行追記(code Nitpick)
- `test_every_error_code_has_a_fixed_english_message`: B 2.5・2.7 が出典の `config_invalid`・`lock_held` は具体文言を `==` で固定し、連鎖比較 `assert ... == ... != ""` を 2 行に分ける(test S-A・Nitpick)
- `test_a_chunked_body_over_the_limit_is_a_400_without_details` の `range(1_000)` を意味のある値にするかコメントで意図を示す(test Nitpick)

据え置き:
- `search_index_reader.py`(`count_by_source`・`existing_ids`)を `parse_uncounted_search` に切り替える案(code Suggestion): 現状 `track_total_hits` が True/False で `eq` のため安全。本文を変更する場合に再検討
- `test_secret_output.py` の `.invalid` DNS 依存(test S-B): この環境では高速に失敗。CI で問題が出たら `127.0.0.1` の閉じたポートに切り替える
- `test_main.py` の秘密値テスト(S-C): P3 以降の EP 追加ごとに `assert_secret_absent` を使い回す(運用)

## 結論

R-A の Critical・Important はすべて解消。P3 に進む。

## 次にやること

- P3(EP-09・10・12・14 と導出)。上記の取り込み分を含める
