# 0003 code-reviewer のレビューと対応

作成日: 2026-11-13

## レビュー結果(code-reviewer)

差分は小さく妥当で、`2.19` の古い記述の取りこぼしはなかった。指摘は次の4点。

| 重要度 | 指摘 | 対応 |
|---|---|---|
| Important | `start_period` 60s → 120s の原因説明(猶予不足)が、実測と整合しない | 60s に戻して結合テストを再実行したところ、**40 件成功**(`40 passed in 19.08s`)。初回の失敗は再現せず、原因は未特定。120s への変更を**取りやめ**、`start_period` は 60s のまま。compose.yaml のコメント、README、結果文書 8 章を「原因は未特定。猶予不足とは断定できない」に直した |
| Suggestion | `deploy/compose/README.md:63` の「約 20 秒」が版の注記なし | 「2.19.7 での値」と明記した |
| Suggestion | 「1〜2 分」が 1 回の測定の目安であることが、README に書かれていない | 「1 回の測定の目安」を足した |
| Nitpick | `test_40_source_deletion.py` のコメントの折り返し | 折り返しを直した(`py_compile` で確認) |

## 最終的な変更ファイル

apps/indexer/{pyproject.toml, uv.lock, README.md}、deploy/compose/{compose.yaml(版のみ), .env.example, README.md}、docs/v0.x/test-results/indexer-integration.md(8章を追記)、tests/integration/indexer/test_40_source_deletion.py(コメントのみ)

## 判断・設計上の理由

- `start_period` の延長は、必要だと実証できなかった(60s で 2 回中 1 回失敗、1 回成功ではなく、**120s で成功 1 回・60s で成功 1 回・初回の失敗 1 回**)。「要件にない変更を足さない」ため、取りやめた。ただし、起動が約 66〜121 秒で、猶予が 180 秒程度なので、遅い環境では余裕が小さい。
- 注意: 検証のために一時的に `compose.yaml` を書き換えた。復元の `cp` が対話の確認で止まったが、`start_period` は元の 60s のままで、不要なコメントだけを削除して復元した。差分は版の更新のみ。

## 未対応事項

- 初回の unhealthy の原因は未特定。再発する場合は、`start_period` を延ばすかを、ユーザーが判断する。
- 変更は未コミット。task-reviewer はプランどおり省略した(差分が小さいため)。
