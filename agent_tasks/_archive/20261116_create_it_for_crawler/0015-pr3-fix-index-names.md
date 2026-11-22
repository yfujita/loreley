# 0015 PR #3 指摘 4(結合テストの索引名の固定)への対応

日付: 2026-11-18(ユーザーの指示: 指摘 4 も対応する)

## 確認結果

指摘は適切。compose は `LORELEY_JOBS_INDEX_NAME`・`LORELEY_SOURCES_INDEX_NAME` で索引名を変えられるが、`support.py` は `loreley-jobs`・`loreley-sources` に固定していた。検索インデックス(`loreley-documents`)と `loreley-deletions` は、compose で変えられる変数がないため、対象外(固定のまま)。

## 変更

- `tests/integration/crawler/support.py`: `JOBS_INDEX`・`SOURCES_INDEX` を、compose と同じ環境変数から読む(未指定は既定値)。
- `scripts/run-crawler-integration-test.sh`: 2 つの変数を既定値に export して固定する(シェルの環境変数が `deploy/compose/.env` より優先されるため、スタックとテストの食い違いを防ぐ。ポートの固定と同じ方針)。
- `tests/integration/crawler/README.md`: 前提の表に「索引名」の行を追加(手動起動で変えたときは、同じ変数を pytest にも渡す)。

## 検証

- 索引名を `it-custom-jobs`・`it-custom-sources` にして手動でスタックを起動し、同じ変数を渡した pytest: **14 passed(40.14s)**。`it-custom-*` の索引ができ、`loreley-jobs`・`loreley-sources` は無いことを確認。
- 一括スクリプトを `LORELEY_JOBS_INDEX_NAME=shell-override` を付けて実行: 固定されて **14 passed(39.48s)**、後始末後にコンテナ・ボリューム・`data/` なし。
- ruff check・format OK。

## 未対応事項

- 0014 の未対応事項のまま(Indexer 用スクリプトの残骸検出、Connector の許可ルートの制限)。
- 本記録の変更は未コミット・未 push。
