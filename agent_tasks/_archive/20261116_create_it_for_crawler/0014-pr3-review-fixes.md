# 0014 PR #3 レビュー指摘 1〜3 への対応

日付: 2026-11-18(ユーザーの指示: PR レビューの指摘 1・2・3 を確認し、適切なら対応する。指摘 4 は対象外)

## 確認結果(3 件とも指摘は適切)

1. **P1 Crawler API の公開**: 適切。設計書 crawler-architecture 10 章は「ホストに公開しない」。FileSystem Connector の `root` はコンテナ内の任意のパスを受け付け、API は認証なしのため、ループバックでも防げない(0013 のユーザー判断事項 3 に当たる)。
2. **P1 既存ボリュームの `loreley-jobs`**: 適切。旧マッピングは `dynamic: false` の 4 項目で、`init-indices.sh` は既存を変更しない。旧マッピングの実 OpenSearch(3.9.0)で、修正前に `record_type`・`status` の検索が 0 件になることを再現した。
3. **P2 スクリプトが既存データを消す**: 適切。事前確認はコンテナだけで、ボリュームと `data/` を見ていなかった。

## 変更

- `deploy/compose/compose.yaml`: `crawler` の `ports` を削除。ヘッダーの公開範囲の説明を更新。
- `tests/integration/crawler/compose.test.yaml`: `crawler` を `127.0.0.1:${CRAWLER_HOST_PORT:-8001}:8001` に publish(結合テスト専用)。
- `deploy/compose/.env.example`: `CRAWLER_HOST_PORT` を削除。
- `infra/opensearch/init-indices.sh`: `extend_mapping` を追加し、`loreley-jobs` に不足項目を `PUT _mapping` で足す(jq なし。`"mappings"` を sed で取り出す。形式の前提はコメントに明記)。
- `scripts/run-crawler-integration-test.sh`: `check_no_leftover_data`(`loreley-it` のボリュームの残り、空でない `data/` で中止)。docker の失敗も止める。
- `tests/integration/crawler/test_01_startup.py`: `test_init_adds_the_missing_fields_to_an_existing_jobs_index` を追加(旧定義のテスト専用索引で、init を再実行して項目と検索を確認。本物の索引には触れない)。
- 文書: `deploy/compose/README.md`、`tests/integration/crawler/README.md`(14 テスト)、`apps/crawler/README.md`(レビューで指摘された公開の記述)、`docs/v0.x/test-results/crawler-integration.md`(8 章を追加、公開に関する記述を更新)。
- `apps/crawler` のコードは未変更。

## 検証

- 旧マッピングで修正前 0 件 → 修正後 1 件、再実行で同じ結果、型衝突は HTTP 400 で失敗(検証用に立てた OpenSearch コンテナは削除済み)。
- `docker compose config`: `compose.yaml` 単体は 8000・9200 のみ。`compose.test.yaml` を重ねると crawler の 8001(127.0.0.1)。
- 中止ケース: ボリュームだけ残した状態、`data/` に利用者のファイルがある状態で、終了コード 1 で中止し、何も消えない。
- 最終版のスクリプト: **14 passed(41.81s)**、後始末後にコンテナ・ボリューム・`data/` なし。Indexer の結合テスト: 40 passed(21.30s)。ruff check・format OK。
- code-reviewer: Critical なし。Important 1 件(`apps/crawler/README.md` の公開の記述)・Suggestion 2 件・Nitpick 1 件のうち、Important・結果記録の件数・Nitpick を反映。

## 未対応・判断事項

- `run-indexer-integration-test.sh` にも同じ残骸検出は入れていない(同じプロジェクト名・ボリュームで `down -v` する。Crawler 用だけ対応)。
- Connector が許可するルートディレクトリを制限する仕組みは将来の課題。
- 指摘 4(`support.py` の索引名の固定)は未対応(指示の対象外)。
- 設計書(arch 10 章の差、`loreley-sources` の `strict`)への反映は、従来どおりユーザー判断。
- 変更は未コミット。
