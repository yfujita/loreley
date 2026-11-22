# 0002 OpenSearch / opensearch-py の更新(フェーズ1〜3)

作成日: 2026-11-13 / プラン 0001 は、ユーザーが「そのプランで進めて」と指示して承認済み。

## 実施内容

1. **依存の更新**: `apps/indexer/pyproject.toml` の `opensearch-py>=2.8,<4` を `>=3.2,<4` にした。`uv lock` で `uv.lock` の specifier だけが変わった(opensearch-py は更新前から 3.2.0 で、PyPI の最新)。Indexer の単体テスト 2119 件成功、ruff の指摘なし。
2. **compose の更新**: `OPENSEARCH_VERSION` の既定を `2.19.7` → `3.9.0`(`compose.yaml` 2か所、`.env.example`)。
3. **結合テスト**: `scripts/run-indexer-integration-test.sh`
   - 初回: 失敗(終了コード 10、`container for service "opensearch" is unhealthy`)。原因は、3.9.0 の起動が 1〜2 分かかり、ヘルスチェックの猶予(`start_period` 60s + 10s×12)に足りなかったこと。手動測定で、クラスタが応答するまで約 121 秒、ログの `started` まで約 66 秒。
   - 対応: `start_period` を 60s → 120s にした(プランにない変更。3.9.0 を動かすために必要な最小の変更と判断した)。
   - 2回目: **40 件すべて成功**(`40 passed in 18.78s`)。Indexer の実装修正は不要だった。
4. **ドキュメント**: `deploy/compose/README.md`(版、選定理由、実体のダイジェスト・build_hash・JDK、起動時間、start_period)、`apps/indexer/README.md`(309, 310行)、`docs/v0.x/test-results/indexer-integration.md`(8章を追記。1〜7章の 2.19.7 の記録は履歴として残した)、`tests/integration/indexer/test_40_source_deletion.py`(コメントのみ)。

## 実測した 3.9.0 の実体

- ダイジェスト `sha256:3b55f6b6249cfdb92b52ee59adc8a266203ba9ef9f5d82544fad6f1af2f3609e`
- build_hash `4ee42a94e87f66fbf1e62a9871b1b87f91e02472`、Lucene 10.5.1、JDK 25.0.4.1
- セキュリティプラグイン無効の起動(`DISABLE_SECURITY_PLUGIN` / `DISABLE_INSTALL_DEMO_CONFIG`)は 3.x でも動いた。

## 変更したファイル

apps/indexer/{pyproject.toml, uv.lock, README.md}、deploy/compose/{compose.yaml, .env.example, README.md}、docs/v0.x/test-results/indexer-integration.md、tests/integration/indexer/test_40_source_deletion.py

## 判断・設計上の理由

- opensearch-py は更新前から最新の 3.2.0 だったため、変更は指定範囲の下限を明示するだけにした。
- `start_period` の延長は、2.19.7 でも害がない(成功すれば即 healthy)。

## 未対応事項

- code-reviewer のレビュー結果の反映(レビュー中)。
- 変更は未コミット(ユーザーの指示があればコミットする)。
- 起動時間の測定は各 1 回のみ(目安)。U-31 の未実施項目は 3.9.0 でも未実施。
