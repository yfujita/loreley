# 0001 要件確認

日付: 2026-11-12

## 実施内容

requirements-clarifier で要件定義(0000)の不明点を洗い出し、Q1〜Q3 をユーザーに確認して回答を得た。

## ユーザー確認の結果(確定)

| # | 質問 | 回答 |
|---|------|------|
| Q1 | インデックス/マッピングの作成主体・置き場所 | `infra/opensearch/schema/{search-index,deletions,jobs}.json` に定義を置き、compose の `opensearch-init` サービスが OpenSearch healthy 後に一度だけ作成。indexer は完了を `depends_on` で待つ。日本語プラグインは入れず公式イメージ使用。(要件の対象範囲に `infra/` を追加) |
| Q2 | 動作確認の範囲 | 主要フロー + 実機確認項目(U-31)の一部。テストが Crawler 役となり、ロック書込→開始通知→バッチ登録(txt/md/html/pdf、extract_failed、unchanged/updated、oversize、ロック不所有)→last-seen→終了通知→Status→TTL削除、ソース削除1〜3。U-31 のうち自然に通るもの(painless max 比較、search_after、delete_by_query、404 応答形、日時形式)を確認。409競合・_reindex・要約は対象外 |
| Q3 | テスト形態 | ルート `tests/integration/` に pytest、ホストから実行。`up --wait` → `pytest` → `down -v` を1スクリプト化。OpenSearch(127.0.0.1:9200)・Indexer(127.0.0.1:8000)はループバックのみ公開。専用 pyproject で依存分離。結果は作業記録と `docs/v0.x/test-results/indexer-integration.md` に記録 |

## 確定した要件(0000 + 回答 + 置いたデフォルト)

- 対象範囲: apps/indexer、deploy、tests、**infra/opensearch(追加)**、scripts(実行スクリプト)、docs/v0.x/test-results(結果記録)
- compose は `deploy/compose/`(`compose.yaml`、`.env.example`、`README.md`)。`compose.dev.yaml` は作らない
- OpenSearch: 公式イメージ、単一ノード、ヒープ小さめ、セキュリティプラグイン無効、バージョンは実装時に安定版を選び固定して結果に記録
- Indexer: 要約無効(外部LLM不要)、`http://opensearch:9200` で接続。認証・TLS 経路は対象外
- 手順書: `deploy/compose/README.md`(起動・停止)、`tests/integration/README.md`(実行・シナリオ一覧)
- テストは source_id / crawl_id をテストごとに一意にし、固定サンプル文書を `tests/integration/` に置く。コメントを充実させ何をテストしているかを明示する(0000 制約)
- 不具合・設計との食い違い: 軽微なものは `apps/indexer` で修正、設計に関わるものはユーザーに報告して判断を仰ぐ
- 完了条件: compose を利用したテストが成功

## 未対応事項・次にやること

- deletions / jobs のマッピング案(設計書は部分定義のみ)はプラン内で提示し、プラン承認時に確認する
- CI 組み込みは対象外
- 次: planner でプラン作成(0002)→ユーザー承認
