# 0001 作業プラン(OpenSearch / opensearch-py の更新)

作成日: 2026-11-13 / 状態: **ユーザー承認待ち**

## 事実確認(2026-11-13 に実測)

- opensearch-py: PyPI の最新は **3.2.0**。`apps/indexer/uv.lock` はすでに 3.2.0 を固定している。`apps/indexer/pyproject.toml` の指定が `>=2.8,<4` のままなので、実質の変更は指定範囲の引き上げだけ。
- OpenSearch: Docker Hub に `opensearchproject/opensearch:3.9.0` がある(2026-10-26 公開)。3.8.0 以前も存在し、3.9.0 が現時点の最新。
- 結合テスト(`tests/integration/indexer/`)は REST を直接呼び、opensearch-py を依存に持たない。opensearch-py は Indexer 側だけ。
- 現行 compose の「2.19 を選んだ理由」(opensearch-py 3.2.0 の CI が 2.19 系列を検証対象とする)は、3.9.0 では根拠が変わる。3.2.0 と 3.9.0 の組み合わせは未検証で、結合テストが最初の実機確認になる。
- compose はセキュリティプラグインを無効にしている(`DISABLE_SECURITY_PLUGIN` / `DISABLE_INSTALL_DEMO_CONFIG`)。3.x でもこの設定が効くかは、起動して確認する。

## 変更範囲

| 対象 | 変更 |
|---|---|
| `apps/indexer/pyproject.toml` | `opensearch-py>=2.8,<4` → `>=3.2,<4` |
| `apps/indexer/uv.lock` | `uv lock` で再生成(3.2.0 のまま、specifier のみ更新) |
| `deploy/compose/compose.yaml` | 既定の `2.19.7` → `3.9.0`(2か所)、コメント(2.19 の選定理由)を更新 |
| `deploy/compose/.env.example` | `OPENSEARCH_VERSION=3.9.0` |
| `deploy/compose/README.md` | 版・選定理由・確認した実体(ダイジェスト、build_hash、JDK)・「2.19 以外は未確認」を更新 |
| `docs/v0.x/test-results/indexer-integration.md` | 3.9.0 での結果を追記(既存の 2.19.7 の記録は履歴として残す) |
| `apps/indexer/README.md`(309, 310行) | 「2.19.7 で実機確認」の記述を、実測に合わせて更新 |
| `tests/integration/indexer/test_40_source_deletion.py:127` | コメント中の「2.19.7 で実測」を、3.9.0 での結果に合わせて更新 |

## フェーズ

1. **依存の更新**: `pyproject.toml` を更新し、`uv lock` と Indexer の単体テストを実行する。
2. **compose の更新と結合テスト**: compose の版を 3.9.0 にし、`scripts/run-indexer-integration-test.sh` で結合テストを通す。
   - 失敗した場合は、原因を切り分けて報告する。範囲は「OpenSearch 3.x の挙動差」か「opensearch-py 3.2.0 の非互換」かを区別する。Indexer の実装修正が要る場合は、要件の範囲(「結合テストを通す」)に含まれるかを、ユーザーに確認してから進める。
3. **ドキュメントの更新**: 上の表の文書を、実測した結果(ダイジェスト、build_hash、テスト結果)に合わせて更新する。実測していないことは書かない。
4. **レビュー**: code-reviewer(差分は設定・ドキュメント中心で小さいため、code-reviewer 1回。テストコードの変更はコメントのみで、test-reviewer は省略)。task-reviewer は、差分が小さいため省略する。
5. **記録**: 作業記録と `STATUS.md` を更新する。

## 判断が要る点

- 要件の「3.2?」は、すでに満たされている(現行のロックが 3.2.0 で、最新)。指定範囲を `>=3.2,<4` に上げて、下限を明示する。
- OpenSearch の版は、要件どおり `3.9.0` をパッチまで固定する(`latest` は使わない)。

## 完了条件

- [ ] 結合テストが OpenSearch 3.9.0 + opensearch-py 3.2.0 で通る
- [ ] Indexer の単体テストが通る
- [ ] ドキュメントが実測と一致している
