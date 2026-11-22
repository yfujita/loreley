# 0007 ハイライトのオフセット方針を公式ドキュメントで確認

## 実施した作業の概要

0006で「実装時に確認する」としていた点を、ユーザーから示されたOpenSearch公式ドキュメントで確認した（2026-11-06）。
https://docs.opensearch.org/latest/search-plugins/searching-data/highlight/

確認できた内容：

- オフセットかterm vectorsを付けて索引化したフィールドは、unifiedハイライタとfvhハイライタでは再解析されない。そのため解析上限は適用されない（"Fields indexed with offsets or term vectors are not reanalyzed by the `unified` and `fvh` highlighters, so the limit does not apply to them."）。
- plainハイライタは常に再解析する。
- `index.highlight.max_analyzed_offset`の既定は1000000である。再解析が必要なフィールドがこの上限を超えると、検索リクエスト全体が失敗する。
- unifiedハイライタは、オフセットを次の順で探す。`term_vector: with_positions_offsets`があればterm vectors、`index_options: offsets`があればポスティング、どちらもなければ再解析である。
- オフセットの保存にはディスクが追加で必要だが、term vectorsより少なくて済む。

## 変更したファイル

- `docs/product-design/product-design-v0.2.md` §3.3.2
  - unifiedハイライタ（既定）を使うことを明記した。
  - 上限の既定値（100万文字）を書いた。
  - plainハイライタを使わないことと、その理由（常に再解析し、上限を超えるとリクエスト全体が失敗する）を書いた。

## 判断・設計上の理由

- 0006の方針（`index_options: offsets`）が正しいことを確認できた。term vectorsよりディスク使用量が少ないので、引き続き`index_options: offsets`を採用する。
- 0006の未対応事項のうち、「公式ドキュメントでの確認」と「offsetsとterm vectorsのどちらを使うか」はこれで解消した。

## 未対応事項・次にやること

- オフセットの保存でインデックスサイズがどれだけ増えるかを、実装時に計測する。
- 0005の未対応事項は残っている（§3.1.1への`last_seen_at`の追加、TTLと削除率のしきい値の既定値）。
- 0005〜0007の変更は、文書レビューとタスクレビュー（task-reviewer）がまだである。
